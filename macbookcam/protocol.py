"""Общий протокол MacBookCam: порты, автообнаружение, чтение из сокета."""

import json
import socket
import sys
import time

PROTOCOL_VERSION = 1
DISCOVERY_MAGIC = b"MACBOOKCAM_DISCOVER"
DEFAULT_PORT = 5005
DISCOVERY_PORT = 5006
# Заголовок кадра: длина JPEG (4 байта) + время захвата в мс (8 байт)
FRAME_HEADER = "!IQ"
FRAME_HEADER_SIZE = 12
MAX_FRAME_SIZE = 20_000_000


def log(msg):
    # В оконном .exe/.app нет консоли: sys.stdout там None
    if sys.stdout is None:
        return
    try:
        print(time.strftime("[%H:%M:%S] ") + msg, flush=True)
    except (OSError, ValueError, UnicodeEncodeError):
        pass


def recv_exact(sock, n):
    buf = bytearray(n)
    view = memoryview(buf)
    got = 0
    while got < n:
        r = sock.recv_into(view[got:], n - got)
        if r == 0:
            raise ConnectionError("соединение закрыто")
        got += r
    return bytes(buf)


def recv_line(sock, limit=8192):
    buf = b""
    while not buf.endswith(b"\n"):
        c = sock.recv(1)
        if not c:
            raise ConnectionError("соединение закрыто")
        buf += c
        if len(buf) > limit:
            raise ValueError("слишком длинный заголовок")
    return buf


def send_json_line(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def get_local_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips)


def discover(timeout=3.0, first_only=True):
    """
    Ищет отправителей MacBookCam широковещательным UDP-запросом.
    Возвращает список (host, port, name). При first_only — после первого ответа.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.3)
    found = {}
    deadline = time.time() + timeout
    next_ping = 0.0
    try:
        while time.time() < deadline:
            if time.time() >= next_ping:
                for target in ("255.255.255.255", "<broadcast>"):
                    try:
                        sock.sendto(DISCOVERY_MAGIC, (target, DISCOVERY_PORT))
                    except OSError:
                        pass
                next_ping = time.time() + 1.0
            try:
                data, addr = sock.recvfrom(1024)
                info = json.loads(data.decode("utf-8"))
                found[addr[0]] = (addr[0], int(info.get("port", DEFAULT_PORT)), str(info.get("name", "?")))
                if first_only:
                    break
            except (socket.timeout, ValueError, OSError):
                continue
    finally:
        sock.close()
    return list(found.values())
