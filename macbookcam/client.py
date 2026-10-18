"""
Сторона ПК: приём кадров с Mac, сглаживание и вывод в виртуальную камеру.

Без OpenCV: JPEG распаковывает Pillow (libjpeg-turbo), поэтому приложение на ПК
легче на ~20 МБ. В очереди лежат сжатые кадры, распаковка — прямо перед показом.
"""

import collections
import io
import json
import os
import socket
import struct
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .i18n import tr
from .protocol import (DEFAULT_PORT, FRAME_HEADER, FRAME_HEADER_SIZE, MAX_FRAME_SIZE,
                       discover, enable_keepalive, log, recv_exact, recv_line, send_json_line)

# Режимы буфера сглаживания: доля «запаса» к измеренной неровности сети
# (перцентиль опозданий, множитель, запас в мс, предел буфера в мс)
SMOOTHING = {"off": None, "auto": (99, 1.0, 12, 200), "strong": (99.5, 1.3, 25, 300)}
WINDOW_S = 8.0  # окно статистики сети, секунд


class NetStats:
    """
    Оценка задержки по меткам времени Mac. Часы Mac и ПК не синхронизированы, поэтому
    считаем d = (время прихода − время съёмки) и берём минимум за окно как «базу»:
    разница d − база — это то, насколько кадр опоздал из-за сети (джиттер).
    """

    def __init__(self):
        self.samples = collections.deque()  # (время прихода, d)

    def add(self, now, d):
        self.samples.append((now, d))
        while self.samples and now - self.samples[0][0] > WINDOW_S:
            self.samples.popleft()

    def base(self):
        return min(d for _, d in self.samples) if self.samples else 0.0

    def jitter_percentile(self, pct):
        if len(self.samples) < 5:
            return 0.0
        base = self.base()
        late = sorted(d - base for _, d in self.samples)
        return late[min(len(late) - 1, int(len(late) * pct / 100))]


class StreamReceiver:
    """Фоновый поток: держит соединение с Mac, переподключается, складывает кадры в очередь."""

    def __init__(self, host, port, width, height, fps, quality, drop_late=False):
        self.host, self.port = host, port
        self.request = {"width": width, "height": height, "fps": fps, "quality": quality,
                        "drop_late": drop_late}
        self.connected = False
        self.peer = ""
        self.info = {}
        self._status = ("status_connecting", {})
        self.stats_fps = 0.0
        self.stats_mbps = 0.0
        self.net = NetStats()
        self.queue = collections.deque(maxlen=30)  # (метка съёмки, время прихода, JPEG)
        self.last_arrival = 0.0
        self._session_started = 0.0
        self._cv = threading.Condition()
        self._sock = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @property
    def status(self):
        key, kw = self._status
        return tr(key, **kw)

    def _set_status(self, key, **kw):
        self._status = (key, kw)

    def _resolve_host(self):
        if self.host:
            return self.host, self.port
        self._set_status("status_searching")
        found = discover()
        if not found:
            self._set_status("status_not_found")
            return None
        host, port, name = found[0]
        log(tr("log_found", name=name, host=host, port=port))
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
                    self._set_status("status_no_link", host=host, error=e)
                    secs = int(time.time() - self._session_started) if self._session_started else 0
                    log(tr("log_session_lost", host=host, secs=secs, error=e) if secs
                        else tr("status_no_link", host=host, error=e))
            finally:
                self.connected = False
                self._session_started = 0.0
            self._wait(1.5)

    def _wait(self, seconds):
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(0.1)

    def _session(self, host, port):
        self._set_status("status_connecting_to", host=host)
        sock = socket.create_connection((host, port), timeout=5)
        self._sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 21)
            enable_keepalive(sock)
            send_json_line(sock, self.request)
            info = json.loads(recv_line(sock).decode("utf-8"))
            if "error" in info:
                code = info.get("code")
                raise ConnectionError(tr("err_" + code) if code and tr.has("err_" + code) else info["error"])
            self.info = info
            log(tr("log_mac_stream", w=info["width"], h=info["height"], fps=info["fps"],
                   version=info.get("app_version", "?")))
            self.connected = True
            self._session_started = time.time()
            self.peer = host
            self.net = NetStats()
            self._set_status("status_connected", host=host, w=info["width"], h=info["height"], fps=info["fps"])
            sock.settimeout(5)

            n = nbytes = 0
            t0 = time.time()
            while self._running:
                size, ts_ms = struct.unpack(FRAME_HEADER, recv_exact(sock, FRAME_HEADER_SIZE))
                if size > MAX_FRAME_SIZE:
                    raise ValueError("bad frame size")
                data = recv_exact(sock, size)
                arrived = time.time()
                ts = ts_ms / 1000.0
                self.net.add(arrived, arrived - ts)
                with self._cv:
                    self.queue.append((ts, arrived, data))
                    self.last_arrival = arrived
                    self._cv.notify_all()
                n += 1
                nbytes += size + FRAME_HEADER_SIZE
                dt = arrived - t0
                if dt >= 2:
                    self.stats_fps = n / dt
                    self.stats_mbps = nbytes * 8 / dt / 1e6
                    n = nbytes = 0
                    t0 = arrived
        finally:
            self._sock = None
            sock.close()

    def wait_new(self, timeout):
        with self._cv:
            if not self.queue:
                self._cv.wait(timeout)

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        with self._cv:
            self._cv.notify_all()


def decode_frame(data, width, height, mirror=False):
    """
    JPEG → RGB-картинка нужного размера. Если кадр больше нужного, Pillow уменьшает его
    прямо при распаковке (draft), это и быстрее, и экономнее по памяти.
    Пропорции сохраняются, лишнее заполняется чёрным.
    """
    img = Image.open(io.BytesIO(data))
    img.draft("RGB", (width, height))
    img = img.convert("RGB")
    if img.size != (width, height):
        scale = min(width / img.width, height / img.height)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(size, Image.Resampling.BILINEAR, reducing_gap=2.0)
        if img.size != (width, height):
            canvas = Image.new("RGB", (width, height))
            canvas.paste(img, ((width - img.width) // 2, (height - img.height) // 2))
            img = canvas
    if mirror:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return img


def _font(size, bold=False):
    windir = os.environ.get("WINDIR", r"C:\Windows")
    names = ["segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(os.path.join(windir, "Fonts", name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def placeholder(width, height, text):
    """Заглушка для виртуальной камеры, пока нет кадров с Mac."""
    img = Image.new("RGB", (width, height), (24, 25, 28))
    d = ImageDraw.Draw(img)
    s = height / 720
    title, sub = _font(int(44 * s), bold=True), _font(int(24 * s))
    d.text((width / 2, height / 2 - 22 * s), "MacBookCam", font=title, fill=(235, 236, 240), anchor="ms")
    d.text((width / 2, height / 2 + 26 * s), text, font=sub, fill=(140, 143, 150), anchor="ms")
    return img


def open_virtual_camera(width, height, fps, backend=None):
    import pyvirtualcam
    kwargs = {"width": width, "height": height, "fps": fps,
              "fmt": pyvirtualcam.PixelFormat.RGB, "print_fps": False}
    if backend:
        kwargs["backend"] = backend
    return pyvirtualcam.Camera(**kwargs)


class Bridge:
    """
    Связка «приёмник → виртуальная камера» в фоновом потоке.

    С буфером сглаживания кадр показывается в момент «время съёмки + база + буфер»,
    поэтому интервалы между кадрами на выходе повторяют интервалы съёмки на Mac,
    а не рывки Wi-Fi. Без буфера кадр выводится сразу по приходу (минимальная задержка).
    Пока Mac недоступен, в камеру идёт заглушка, чтобы программы не теряли устройство.
    """

    def __init__(self, host=None, port=DEFAULT_PORT, width=1280, height=720, fps=30,
                 quality=80, mirror=False, vcam=True, backend=None, smoothing="auto"):
        self.width, self.height, self.fps = width, height, fps
        self.mirror = mirror
        self.smoothing = smoothing
        self.output = None      # последний отправленный кадр, PIL.Image (для предпросмотра)
        self.output_seq = 0     # растёт с каждым новым кадром на выходе
        self.backend = backend
        self.buffer_ms = 0.0    # текущий буфер сглаживания
        self.jitter_ms = 0.0    # неровность сети (95-й перцентиль)
        self.pacing_ms = 0.0    # разброс интервалов между кадрами на выходе
        self.vcam_name = ""
        self.cam = None
        self._want_vcam = vcam
        self._vcam_retry_at = 0.0
        if vcam:
            self.cam = open_virtual_camera(width, height, fps, backend)  # может бросить исключение
            self.vcam_name = self.cam.device
        self.rx = StreamReceiver(host, port, width, height, fps, quality,
                                 drop_late=SMOOTHING.get(smoothing) is None)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @property
    def status(self):
        return self.rx.status

    @property
    def connected(self):
        return self.rx.connected

    def _emit(self, data):
        try:
            img = decode_frame(data, self.width, self.height, self.mirror)
        except Exception:  # noqa: BLE001  (битый кадр — пропускаем)
            return
        self._send(img)

    def _send(self, img):
        self.output = img
        self.output_seq += 1
        self._send_vcam(img)

    def _send_vcam(self, img):
        """
        Отправка кадра в виртуальную камеру. Если она сломалась (например, перезапустили OBS),
        открываем её заново не чаще раза в секунду; приём кадров при этом не останавливается.
        Исправную камеру никогда не переоткрываем: программа, которая её читает (Zoom), теряет устройство.
        """
        if not self._want_vcam:
            return
        if self.cam is not None:
            try:
                self.cam.send(np.asarray(img))
                return
            except Exception as e:  # noqa: BLE001
                log(tr("log_vcam_send_failed", error=e))
                try:
                    self.cam.close()
                except Exception:  # noqa: BLE001
                    pass
                self.cam = None
        now = time.time()
        if now - self._vcam_retry_at < 1.0:
            return
        self._vcam_retry_at = now
        try:
            self.cam = open_virtual_camera(self.width, self.height, self.fps, self.backend)
            self.vcam_name = self.cam.device
            log(tr("log_vcam_reopened", name=self.vcam_name))
        except Exception as e:  # noqa: BLE001
            log(tr("log_vcam_reopen_failed", error=e))

    def _target_buffer(self):
        mode = SMOOTHING.get(self.smoothing)
        if mode is None:
            return 0.0
        pct, factor, extra_ms, cap_ms = mode
        return min(cap_ms / 1000, self.rx.net.jitter_percentile(pct) * factor + extra_ms / 1000)

    def _loop(self):
        rx = self.rx
        out_times = collections.deque(maxlen=90)
        buffer_s = 0.0
        last_placeholder = 0.0
        last_log = last_error_log = time.time()
        ph, ph_text = None, None
        try:
            while self._running:
                try:
                    # заглушка, если кадров давно нет
                    if time.time() - rx.last_arrival > 3:
                        if time.time() - last_placeholder > 1 / max(1, self.fps):
                            text = "Waiting for MacBook camera..." if rx.last_arrival else "Connecting..."
                            if ph_text != text:
                                ph, ph_text = placeholder(self.width, self.height, text), text
                            self.output = ph
                            self.output_seq += 1
                            self._send_vcam(ph)
                            last_placeholder = time.time()
                        rx.wait_new(0.05)
                        continue

                    # плавно подстраиваем буфер к измеренной неровности сети
                    target = self._target_buffer()
                    buffer_s += (target - buffer_s) * (0.2 if target > buffer_s else 0.02)
                    if target == 0.0:
                        buffer_s = 0.0
                    self.buffer_ms = buffer_s * 1000
                    self.jitter_ms = rx.net.jitter_percentile(95) * 1000

                    with rx._cv:
                        if not rx.queue:
                            rx._cv.wait(0.05)
                            continue
                        ts, arrived, frame = rx.queue[0]

                    if buffer_s > 0:
                        due = ts + rx.net.base() + buffer_s
                        delay = due - time.time()
                        if delay > 0:
                            time.sleep(min(delay, 0.02))
                            continue
                    with rx._cv:
                        # если очередь распухла (буфер уменьшился) — пропускаем старые кадры
                        while len(rx.queue) > 1 and (buffer_s == 0 or
                                                     rx.queue[1][0] + rx.net.base() + buffer_s <= time.time()):
                            rx.queue.popleft()
                        ts, arrived, frame = rx.queue.popleft()
                    self._emit(frame)

                    now = time.time()
                    out_times.append(now)
                    if len(out_times) > 10:
                        iv = np.diff(np.array(out_times))
                        self.pacing_ms = float(np.std(iv) * 1000)
                    if now - last_log >= 30 and rx.connected:
                        log(tr("log_stats", fps=f"{rx.stats_fps:.1f}", mbps=f"{rx.stats_mbps:.1f}",
                               jitter=f"{self.jitter_ms:.0f}", buffer=f"{self.buffer_ms:.0f}"))
                        last_log = now
                except Exception as e:  # noqa: BLE001  (одна ошибка не должна останавливать вывод видео)
                    if time.time() - last_error_log >= 5:
                        log(tr("log_bridge_error", error=repr(e)))
                        last_error_log = time.time()
                    time.sleep(0.1)
        finally:
            if self.cam is not None:
                try:
                    self.cam.close()
                except Exception:  # noqa: BLE001
                    pass

    def stop(self):
        self._running = False
        self.rx.stop()
        self._thread.join(timeout=2)
