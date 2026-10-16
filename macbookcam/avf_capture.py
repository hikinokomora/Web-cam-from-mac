"""
Захват камеры на macOS напрямую через AVFoundation (pyobjc).

В отличие от OpenCV умеет выбирать формат камеры по частоте кадров (например, 60 к/с,
если камера это поддерживает) и даёт ровные метки времени по часам камеры.
"""

import threading
import time
import traceback

import cv2
import numpy as np
import objc
from Foundation import NSObject

import AVFoundation as AVF
import CoreMedia
import libdispatch
import Quartz


def list_devices():
    """Видеоустройства в стабильном порядке: встроенная камера, iPhone, внешние."""
    types = []
    for name in ("AVCaptureDeviceTypeBuiltInWideAngleCamera", "AVCaptureDeviceTypeContinuityCamera",
                 "AVCaptureDeviceTypeExternal", "AVCaptureDeviceTypeExternalUnknown",
                 "AVCaptureDeviceTypeDeskViewCamera"):
        t = getattr(AVF, name, None)
        if t is not None and t not in types:
            types.append(t)
    try:
        session = AVF.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
            types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
        devices = list(session.devices())
        if devices:
            return devices
    except Exception:  # noqa: BLE001
        pass
    return list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo))


def _format_info(fmt):
    desc = fmt.formatDescription()
    dims = CoreMedia.CMVideoFormatDescriptionGetDimensions(desc)
    max_fps = max((r.maxFrameRate() for r in fmt.videoSupportedFrameRateRanges()), default=0)
    return int(dims.width), int(dims.height), float(max_fps)


def device_max_fps(device):
    return max((_format_info(f)[2] for f in device.formats()), default=0.0)


def describe_formats(device):
    """Короткий список режимов камеры для диагностики: ['1920x1080@30', '1280x720@60', ...]."""
    seen = {}
    for f in device.formats():
        w, h, fps = _format_info(f)
        seen[(w, h)] = max(seen.get((w, h), 0), fps)
    return [f"{w}x{h}@{fps:g}" for (w, h), fps in sorted(seen.items(), reverse=True)]


def choose_format(device, width, height, fps):
    """
    Подбирает формат: сначала тот, что даёт нужную частоту, затем по разрешению —
    наименьший, не меньше запрошенного (иначе самый большой из доступных).
    """
    best, best_key = None, None
    for f in device.formats():
        w, h, max_fps = _format_info(f)
        fps_ok = max_fps >= fps - 0.5
        big_enough = w >= width and h >= height
        key = (0 if fps_ok else 1,
               0 if big_enough else 1,
               w * h if big_enough else -(w * h),
               -max_fps)
        if best_key is None or key < best_key:
            best, best_key = f, key
    return best


class _Delegate(NSObject, protocols=[objc.protocolNamed("AVCaptureVideoDataOutputSampleBufferDelegate")]):
    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample, connection):
        cb = getattr(self, "callback", None)
        if cb is not None:
            cb(sample)


class AVFoundationSource:
    """Источник кадров с тем же интерфейсом, что и CameraSource в server.py."""

    def __init__(self, index, width, height, fps):
        self._session = None
        self.callback_error = ""
        devices = list_devices()
        if not devices:
            raise RuntimeError("camera_not_found")
        self.device = devices[min(index, len(devices) - 1)]
        self.max_fps = device_max_fps(self.device)
        self.formats = describe_formats(self.device)

        self._fmt = choose_format(self.device, width, height, fps)
        if self._fmt is None:
            raise RuntimeError("camera_no_formats")
        fw, fh, fmax = _format_info(self._fmt)
        self.fps = int(round(min(fps, fmax))) or 30
        # уменьшаем до запрошенного размера с сохранением пропорций (никогда не увеличиваем)
        scale = min(1.0, width / fw, height / fh)
        self.width, self.height = int(fw * scale) // 2 * 2, int(fh * scale) // 2 * 2

        self._cond = threading.Condition()
        self._frame = None
        self._ts = 0.0
        self._seq = 0
        self._anchor = None  # (pts в секундах, time.time()) — для ровных меток времени
        self._running = True

        session = AVF.AVCaptureSession.alloc().init()
        session.beginConfiguration()
        inp, _err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(self.device, None)
        if inp is None or not session.canAddInput_(inp):
            raise RuntimeError("camera_open_failed")
        session.addInput_(inp)

        output = AVF.AVCaptureVideoDataOutput.alloc().init()
        # только формат пикселей: размер в настройках вывода заставил бы macOS сменить режим камеры
        output.setVideoSettings_({Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA})
        output.setAlwaysDiscardsLateVideoFrames_(True)
        self._delegate = _Delegate.alloc().init()
        self._delegate.callback = self._on_sample
        self._queue = libdispatch.dispatch_queue_create(b"macbookcam.capture", None)
        output.setSampleBufferDelegate_queue_(self._delegate, self._queue)
        if not session.canAddOutput_(output):
            raise RuntimeError("camera_open_failed")
        session.addOutput_(output)
        self._apply_format()
        session.commitConfiguration()

        self._session = session
        self._output = output
        session.startRunning()
        # macOS может выставить свой формат при старте сессии — применяем наш ещё раз
        self._apply_format()
        self.fps = self._active_fps() or self.fps

        with self._cond:
            if not self._cond.wait_for(lambda: self._frame is not None or self.callback_error, timeout=5):
                self.close()
                raise RuntimeError("camera_no_frames")
        if self._frame is None:
            err = self.callback_error
            self.close()
            raise RuntimeError("frame conversion failed: " + err)

    def _apply_format(self):
        ok, _err = self.device.lockForConfiguration_(None)
        if not ok:
            return
        try:
            self.device.setActiveFormat_(self._fmt)
            duration = CoreMedia.CMTimeMake(1, int(self.fps))
            self.device.setActiveVideoMinFrameDuration_(duration)
            self.device.setActiveVideoMaxFrameDuration_(duration)
        except Exception:  # noqa: BLE001  (камера может отказаться — останется её частота)
            pass
        finally:
            self.device.unlockForConfiguration()

    def _active_fps(self):
        try:
            d = self.device.activeVideoMinFrameDuration()
            return int(round(d.timescale / d.value)) if d.value else 0
        except Exception:  # noqa: BLE001
            return 0

    def _on_sample(self, sample):
        try:
            self._handle_sample(sample)
        except Exception:  # noqa: BLE001
            if not self.callback_error:
                self.callback_error = traceback.format_exc(limit=3)
                with self._cond:
                    self._cond.notify_all()

    def _handle_sample(self, sample):
        pb = CoreMedia.CMSampleBufferGetImageBuffer(sample)
        if pb is None:
            return
        pts = CoreMedia.CMSampleBufferGetPresentationTimeStamp(sample)
        now = time.time()
        Quartz.CVPixelBufferLockBaseAddress(pb, Quartz.kCVPixelBufferLock_ReadOnly)
        try:
            w = Quartz.CVPixelBufferGetWidth(pb)
            h = Quartz.CVPixelBufferGetHeight(pb)
            bpr = Quartz.CVPixelBufferGetBytesPerRow(pb)
            base = Quartz.CVPixelBufferGetBaseAddress(pb)
            buf = base.as_buffer(bpr * h)
            arr = np.frombuffer(buf, np.uint8).reshape(h, bpr)[:, :w * 4].reshape(h, w, 4)
            if (w, h) != (self.width, self.height):
                frame = cv2.resize(arr[:, :, :3], (self.width, self.height), interpolation=cv2.INTER_AREA)
            else:
                frame = np.ascontiguousarray(arr[:, :, :3])  # BGRA → BGR (копия)
        finally:
            Quartz.CVPixelBufferUnlockBaseAddress(pb, Quartz.kCVPixelBufferLock_ReadOnly)

        # метка времени: по часам камеры (ровный шаг), привязанная к системным часам
        ts = now
        if pts.timescale:
            sec = pts.value / pts.timescale
            if self._anchor is None or abs((now - self._anchor[1]) - (sec - self._anchor[0])) > 0.5:
                self._anchor = (sec, now)
            ts = self._anchor[1] + (sec - self._anchor[0])

        with self._cond:
            self._frame = frame
            self._ts = ts
            self._seq += 1
            self._cond.notify_all()

    def wait_frame(self, last_seq, timeout=1.0):
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq or not self._running, timeout)
            return self._seq, self._frame, self._ts

    def close(self):
        self._running = False
        if self._session is not None:
            try:
                self._session.stopRunning()
            except Exception:  # noqa: BLE001
                pass
        with self._cond:
            self._cond.notify_all()
