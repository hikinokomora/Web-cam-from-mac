"""Сторона ПК: приём кадров с Mac и вывод в виртуальную камеру."""

import json
import socket
import struct
import threading
import time

import cv2
import numpy as np

from .protocol import (DEFAULT_PORT, FRAME_HEADER, FRAME_HEADER_SIZE, MAX_FRAME_SIZE,
                       discover, log, recv_exact, recv_line, send_json_line)


class StreamReceiver:
    """Фоновый поток: держит соединение с Mac, переподключается, хранит последний кадр."""

    def __init__(self, host, port, width, height, fps, quality):
        self.host, self.port = host, port
        self.request = {"width": width, "height": height, "fps": fps, "quality": quality}
        self.frame = None
        self.frame_time = 0.0
        self.connected = False
        self.peer = ""
        self.status = "Подключение..."
        self.stats_fps = 0.0
        self.stats_mbps = 0.0
        self._lock = threading.Lock()
        self._sock = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _resolve_host(self):
        if self.host:
            return self.host, self.port
        self.status = "Поиск Mac в сети..."
        log(self.status)
        found = discover()
        if not found:
            self.status = "Mac не найден. Запустите MacBookCam на Mac или укажите IP."
            log(self.status)
            return None
        host, port, name = found[0]
        log(f"Найден {name} ({host}:{port})")
        return host, port

    def _loop(self):
        while self._running:
            target = self._resolve_host()
            if not target:
                self._wait(2)
                continue
            host, port = target
            try:
                self._session(host, port)
            except (OSError, ConnectionError, ValueError) as e:
                if self._running:
                    self.status = f"Нет связи с {host}: {e}"
                    log(self.status)
            finally:
                self.connected = False
            self._wait(1.5)

    def _wait(self, seconds):
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(0.1)

    def _session(self, host, port):
        self.status = f"Подключение к {host}..."
        sock = socket.create_connection((host, port), timeout=5)
        self._sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            send_json_line(sock, self.request)
            info = json.loads(recv_line(sock).decode("utf-8"))
            if "error" in info:
                raise ConnectionError(info["error"])
            log(f"Mac отдаёт {info['width']}x{info['height']}@{info['fps']}")
            self.connected = True
            self.peer = host
            self.status = f"Подключено к {host}: {info['width']}x{info['height']}@{info['fps']}"
            sock.settimeout(5)

            n = nbytes = 0
            t0 = time.time()
            while self._running:
                size, _ts = struct.unpack(FRAME_HEADER, recv_exact(sock, FRAME_HEADER_SIZE))
                if size > MAX_FRAME_SIZE:
                    raise ValueError("некорректный размер кадра")
                data = recv_exact(sock, size)
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                with self._lock:
                    self.frame = frame
                    self.frame_time = time.time()
                n += 1
                nbytes += size + FRAME_HEADER_SIZE
                dt = time.time() - t0
                if dt >= 2:
                    self.stats_fps = n / dt
                    self.stats_mbps = nbytes * 8 / dt / 1e6
                    n = nbytes = 0
                    t0 = time.time()
        finally:
            self._sock = None
            sock.close()

    def latest(self):
        with self._lock:
            return self.frame, self.frame_time

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def fit_frame(frame, width, height):
    """Вписывает кадр в нужный размер с сохранением пропорций (чёрные поля)."""
    h, w = frame.shape[:2]
    if (w, h) == (width, height):
        return frame
    scale = min(width / w, height / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    out = np.zeros((height, width, 3), np.uint8)
    x, y = (width - nw) // 2, (height - nh) // 2
    out[y:y + nh, x:x + nw] = resized
    return out


def placeholder(width, height, text):
    img = np.full((height, width, 3), 30, np.uint8)
    scale = height / 720
    cv2.putText(img, "MacBookCam", (int(40 * scale), height // 2 - int(30 * scale)),
                cv2.FONT_HERSHEY_SIMPLEX, 2 * scale, (200, 200, 200), max(1, int(3 * scale)))
    # OpenCV не рисует кириллицу, поэтому на заглушке — только латиница
    cv2.putText(img, text, (int(40 * scale), height // 2 + int(40 * scale)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (150, 150, 150), max(1, int(2 * scale)))
    return img


def open_virtual_camera(width, height, fps, backend=None):
    import pyvirtualcam
    kwargs = {"width": width, "height": height, "fps": fps,
              "fmt": pyvirtualcam.PixelFormat.BGR, "print_fps": False}
    if backend:
        kwargs["backend"] = backend
    return pyvirtualcam.Camera(**kwargs)


class Bridge:
    """
    Связка «приёмник → виртуальная камера» в фоновом потоке.
    Пока Mac недоступен, в камеру идёт заглушка, чтобы Zoom не терял устройство.
    """

    def __init__(self, host=None, port=DEFAULT_PORT, width=1280, height=720, fps=30,
                 quality=80, mirror=False, vcam=True, backend=None):
        self.width, self.height, self.fps = width, height, fps
        self.mirror = mirror
        self.output = None  # последний отправленный кадр (для предпросмотра)
        self.vcam_name = ""
        self.cam = None
        if vcam:
            self.cam = open_virtual_camera(width, height, fps, backend)  # может бросить исключение
            self.vcam_name = self.cam.device
        self.rx = StreamReceiver(host, port, width, height, fps, quality)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @property
    def status(self):
        return self.rx.status

    @property
    def connected(self):
        return self.rx.connected

    def frame_age_ms(self):
        _, ft = self.rx.latest()
        return (time.time() - ft) * 1000 if ft else None

    def _loop(self):
        last_frame_time = 0.0
        out = placeholder(self.width, self.height, "Connecting...")
        interval = 1.0 / self.fps
        next_tick = time.perf_counter()
        try:
            while self._running:
                frame, ft = self.rx.latest()
                if frame is not None and ft != last_frame_time:
                    last_frame_time = ft
                    out = fit_frame(frame, self.width, self.height)
                    if self.mirror:
                        out = cv2.flip(out, 1)
                elif time.time() - last_frame_time > 3:
                    out = placeholder(self.width, self.height, "Waiting for MacBook camera...")
                self.output = out
                if self.cam is not None:
                    self.cam.send(out)
                    self.cam.sleep_until_next_frame()
                else:
                    next_tick += interval
                    delay = next_tick - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        next_tick = time.perf_counter()
        finally:
            if self.cam is not None:
                self.cam.close()

    def stop(self):
        self._running = False
        self.rx.stop()
        self._thread.join(timeout=2)
