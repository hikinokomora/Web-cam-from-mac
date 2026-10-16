"""
Захват камеры на macOS напрямую через AVFoundation (pyobjc).

В отличие от OpenCV умеет выбирать формат камеры по частоте кадров (например, 60 к/с,
если камера это поддерживает), масштабирует кадр аппаратно и даёт ровные метки времени.
"""

import threading
import time

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
        area = w * h
        # меньше ключ — лучше
        key = (0 if fps_ok else 1,
               0 if big_enough else 1,
               area if big_enough else -area,
               -max_fps)
        if best_key is None or key < best_key:
            best, best_key = f, key
    return best


class _Delegate(NSObject, protocols=[objc.protocolNamed("AVCaptureVideoDataOutputSampleBufferDelegate")]):
    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample, connection):
        cb = getattr(self, "callback", None)
        if cb is not None:
            try:
                cb(sample)
            except Exception:  # noqa: BLE001
                pass


class AVFoundationSource:
    """Источник кадров с тем же интерфейсом, что и CameraSource в server.py."""

    def __init__(self, index, width, height, fps):
        self._session = None
        devices = list_devices()
        if not devices:
            raise RuntimeError("camera_not_found")
        self.device = devices[min(index, len(devices) - 1)]
        self.max_fps = device_max_fps(self.device)

        fmt = choose_format(self.device, width, height, fps)
        if fmt is None:
            raise RuntimeError("camera_no_formats")
        fw, fh, fmax = _format_info(fmt)
        self.fps = int(round(min(fps, fmax))) or 30
        # кадр масштабируется аппаратно до запрошенного размера (с сохранением пропорций формата)
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
        session.setSessionPreset_(AVF.AVCaptureSessionPresetInputPriority)
        inp, err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(self.device, None)
        if inp is None or not session.canAddInput_(inp):
            raise RuntimeError("camera_open_failed")
        session.addInput_(inp)

        output = AVF.AVCaptureVideoDataOutput.alloc().init()
        output.setVideoSettings_({
            Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA,
            Quartz.kCVPixelBufferWidthKey: self.width,
            Quartz.kCVPixelBufferHeightKey: self.height,
        })
        output.setAlwaysDiscardsLateVideoFrames_(True)
        self._delegate = _Delegate.alloc().init()
        self._delegate.callback = self._on_sample
        self._queue = libdispatch.dispatch_queue_create(b"macbookcam.capture", None)
        output.setSampleBufferDelegate_queue_(self._delegate, self._queue)
        if not session.canAddOutput_(output):
            raise RuntimeError("camera_open_failed")
        session.addOutput_(output)
        session.commitConfiguration()

        ok, err = self.device.lockForConfiguration_(None)
        if ok:
            try:
                self.device.setActiveFormat_(fmt)
                duration = CoreMedia.CMTimeMake(1, self.fps)
                self.device.setActiveVideoMinFrameDuration_(duration)
                self.device.setActiveVideoMaxFrameDuration_(duration)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self.device.unlockForConfiguration()

        self._session = session
        self._output = output
        session.startRunning()

        # ждём первый кадр
        with self._cond:
            if not self._cond.wait_for(lambda: self._frame is not None, timeout=5):
                self.close()
                raise RuntimeError("camera_no_frames")

    def _on_sample(self, sample):
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
