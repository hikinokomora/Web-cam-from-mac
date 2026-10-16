"""Сторона Mac: захват камеры и раздача кадров по TCP."""

import json
import socket
import struct
import sys
import threading
import time

import cv2
import numpy as np

from .i18n import tr
from .protocol import (DEFAULT_PORT, DISCOVERY_MAGIC, DISCOVERY_PORT, FRAME_HEADER,
                       PROTOCOL_VERSION, log, recv_line, send_json_line)


class CameraError(RuntimeError):
    """Ошибка камеры с кодом; текст переводится на стороне, которая его показывает."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def open_camera(index):
    if sys.platform == "darwin":
        return cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(index)


def camera_names():
    """Названия камер в порядке индексов (только macOS, иначе пустой список)."""
    if sys.platform != "darwin":
        return []
    try:
        from .avf_capture import list_devices
        return [str(d.localizedName()) for d in list_devices()]
    except Exception:  # noqa: BLE001
        return []


def camera_auth_status():
    """'authorized' | 'denied' | 'undetermined' | 'unknown'."""
    try:
        import AVFoundation
        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeVideo)
        return {0: "undetermined", 1: "denied", 2: "denied", 3: "authorized"}.get(int(status), "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def request_camera_access():
    try:
        import AVFoundation
        AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVFoundation.AVMediaTypeVideo, lambda granted: None)
    except Exception:  # noqa: BLE001
        pass


def probe_cameras(max_index=6):
    """Индексы, разрешения и максимальная частота доступных камер."""
    if sys.platform == "darwin":
        try:
            from .avf_capture import device_max_fps, list_devices
            result = []
            for i, d in enumerate(list_devices()):
                fmt = d.activeFormat()
                import CoreMedia
                dims = CoreMedia.CMVideoFormatDescriptionGetDimensions(fmt.formatDescription())
                result.append((i, int(dims.width), int(dims.height), device_max_fps(d)))
            return result
        except Exception:  # noqa: BLE001
            pass
    result = []
    for i in range(max_index):
        cap = open_camera(i)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                result.append((i, w, h, cap.get(cv2.CAP_PROP_FPS)))
        cap.release()
    return result


class CameraSource:
    """Захват через OpenCV (запасной вариант). Хранит только последний кадр."""

    def __init__(self, index, width, height, fps):
        self.cap = open_camera(index)
        if not self.cap.isOpened():
            raise CameraError("camera_open_failed")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        frame = None
        for _ in range(20):  # камере нужно немного времени на старт
            ok, frame = self.cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.05)
        if frame is None:
            self.cap.release()
            raise CameraError("camera_no_frames")
        self.height, self.width = frame.shape[:2]
        reported_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = int(round(reported_fps)) if 1 <= reported_fps <= 240 else fps
        self.max_fps = self.fps
        self.backend = "opencv"
        self._frame = frame
        self._ts = time.time()
        self._seq = 1
        self._cond = threading.Condition()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            with self._cond:
                self._frame = frame
                self._ts = time.time()
                self._seq += 1
                self._cond.notify_all()

    def wait_frame(self, last_seq, timeout=1.0):
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq or not self._running, timeout)
            return self._seq, self._frame, self._ts

    def close(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=2)
        self.cap.release()


class TestPatternSource:
    """Синтетическая картинка — для проверки без камеры."""

    def __init__(self, width, height, fps):
        self.width, self.height, self.fps = width, height, fps
        self.max_fps = 240
        self.backend = "test"
        self._start = time.time()
        self._seq = 0
        self._next = time.time()
        self._x = np.linspace(0, 255, width, dtype=np.uint8)

    def wait_frame(self, last_seq, timeout=1.0):
        now = time.time()
        if self._next > now:
            time.sleep(self._next - now)
        ts = self._next
        self._next = max(self._next + 1.0 / self.fps, time.time() - 0.5)
        t = ts - self._start
        frame = np.empty((self.height, self.width, 3), np.uint8)
        frame[:, :, 0] = self._x
        frame[:, :, 1] = int(127 + 127 * np.sin(t))
        frame[:, :, 2] = self._x[::-1]
        cx = int((np.sin(t * 1.3) * 0.4 + 0.5) * self.width)
        cv2.circle(frame, (cx, self.height // 2), self.height // 8, (255, 255, 255), -1)
        cv2.putText(frame, f"MacBookCam test {self.fps} fps  #{self._seq}", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5 * self.height / 720, (0, 0, 0), 3)
        self._seq += 1
        return self._seq, frame, ts

    def close(self):
        pass


def open_source(camera, width, height, fps, test_pattern=False):
    if test_pattern:
        return TestPatternSource(width, height, fps)
    if sys.platform == "darwin":
        try:
            from .avf_capture import AVFoundationSource
            src = AVFoundationSource(camera, width, height, fps)
            src.backend = "avfoundation"
            return src
        except Exception as e:  # noqa: BLE001
            log(f"AVFoundation capture failed ({e!r}), falling back to OpenCV")
    return CameraSource(camera, width, height, fps)


class StreamServer:
    """
    TCP-сервер камеры. Работает в фоновых потоках; одновременно обслуживает
    одного клиента. Камера открывается только на время подключения.
    """

    def __init__(self, port=DEFAULT_PORT, camera=0, test_pattern=False,
                 default_quality=80, on_change=None):
        self.port = port
        self.camera = camera
        self.test_pattern = test_pattern
        self.default_quality = default_quality
        self.on_change = on_change  # вызывается из фоновых потоков при смене состояния
        self.enabled = True
        self.client = None          # IP подключённого клиента
        self.stream_info = ""       # «1280x720@30»
        self.error_code = ""        # код последней ошибки камеры
        self.stats_fps = 0.0
        self.stats_mbps = 0.0
        self._srv = None
        self._conn = None
        self._udp = None
        self._running = False

    # --- управление ---

    def start(self):
        self._running = True
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("", self.port))
        self._srv.listen(1)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._discovery_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self.kick()
        for s in (self._srv, self._udp):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    def kick(self):
        """Отключить текущего клиента (камера выключится)."""
        conn = self._conn
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.kick()
        self._notify()

    def set_camera(self, index):
        self.camera = index
        self.kick()  # клиент переподключится уже к новой камере

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                pass

    # --- потоки ---

    def _discovery_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError as e:
            log(tr("log_discovery_unavailable", error=e))
            return
        self._udp = sock
        name = socket.gethostname().removesuffix(".local")
        reply = json.dumps({"name": name, "port": self.port}).encode()
        while self._running:
            try:
                data, addr = sock.recvfrom(1024)
                if data.startswith(DISCOVERY_MAGIC) and self.enabled:
                    sock.sendto(reply, addr)
            except OSError:
                if not self._running:
                    break
                time.sleep(0.5)

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._srv.accept()
            except OSError:
                break
            if not self.enabled:
                try:
                    send_json_line(conn, {"error": tr("err_paused"), "code": "paused"})
                except OSError:
                    pass
                conn.close()
                continue
            self._conn = conn
            self.client = addr[0]
            self.error_code = ""
            log(tr("log_client_connected", ip=addr[0]))
            self._notify()
            try:
                self._serve(conn, addr)
            except (ConnectionError, OSError) as e:
                log(tr("log_connection_closed", error=e))
            except Exception as e:  # noqa: BLE001
                self.error_code = "internal"
                log(f"Error: {e!r}")
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                self._conn = None
                self.client = None
                self.stream_info = ""
                self.stats_fps = self.stats_mbps = 0.0
                self._notify()

    def _serve(self, conn, addr):
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(10)
        req = json.loads(recv_line(conn).decode("utf-8"))
        width = int(req.get("width", 1280))
        height = int(req.get("height", 720))
        fps = max(1, min(120, int(req.get("fps", 30))))
        quality = max(10, min(100, int(req.get("quality", self.default_quality))))
        log(tr("log_client_request", ip=addr[0], w=width, h=height, fps=fps, q=quality))

        try:
            source = open_source(self.camera, width, height, fps, self.test_pattern)
        except CameraError as e:
            self.error_code = e.code
            send_json_line(conn, {"error": tr("err_" + e.code), "code": e.code})
            log(tr("err_" + e.code))
            return

        try:
            send_json_line(conn, {"version": PROTOCOL_VERSION, "width": source.width,
                                  "height": source.height, "fps": source.fps,
                                  "max_fps": round(source.max_fps), "backend": source.backend})
            self.stream_info = f"{source.width}x{source.height}@{source.fps}"
            log(tr("log_stream_started", info=self.stream_info, backend=source.backend,
                   max_fps=round(source.max_fps)))
            self._notify()
            conn.settimeout(10)

            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            seq = sent = bytes_sent = 0
            t0 = time.time()
            while self._running and self.enabled:
                new_seq, frame, ts = source.wait_frame(seq)
                if new_seq == seq:
                    continue  # нового кадра не было — повторно не шлём
                seq = new_seq
                ok, jpg = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue
                data = jpg.tobytes()
                # метка времени — момент съёмки кадра, по ней ПК выравнивает показ
                conn.sendall(struct.pack(FRAME_HEADER, len(data), int(ts * 1000)) + data)
                sent += 1
                bytes_sent += len(data)
                dt = time.time() - t0
                if dt >= 2:
                    self.stats_fps = sent / dt
                    self.stats_mbps = bytes_sent * 8 / dt / 1e6
                    self._notify()
                    sent = bytes_sent = 0
                    t0 = time.time()
        finally:
            source.close()
            log(tr("log_camera_off"))
