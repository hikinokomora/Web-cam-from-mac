"""Общий протокол MacBookCam: порты, автообнаружение, чтение из сокета."""

import ipaddress
import json
import select
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


def broadcast_targets():
    """
    Пары (локальный IP, широковещательный адрес его сети) для всех IPv4-адаптеров.
    Нужны, чтобы поиск шёл через Wi-Fi, даже если маршрут по умолчанию у VPN/TUN.
    """
    pairs = []
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family != socket.AF_INET or not a.netmask:
                    continue
                try:
                    net = ipaddress.IPv4Network(f"{a.address}/{a.netmask}", strict=False)
                except ValueError:
                    continue
                pairs.append((a.address, str(net.broadcast_address)))
    except ImportError:
        pairs = [(ip, str(ipaddress.IPv4Network(f"{ip}/24", strict=False).broadcast_address))
                 for ip in get_local_ips()]
    return [(ip, b) for ip, b in pairs
            if not ip.startswith(("127.", "169.254.")) and ip != b]


def discover(timeout=3.0, first_only=True):
    """
    Ищет отправителей MacBookCam широковещательным UDP-запросом через каждый адаптер.
    Возвращает список (host, port, name). При first_only — после первого ответа.
    """
    socks = []
    for ip, bcast in broadcast_targets():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            s.setblocking(False)
            socks.append((s, [bcast, "255.255.255.255"]))
        except OSError:
            continue
    # запасной вариант: сокет без привязки, по маршруту по умолчанию
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setblocking(False)
    socks.append((s, ["255.255.255.255"]))

    found = {}
    deadline = time.time() + timeout
    next_ping = 0.0
    try:
        while time.time() < deadline:
            if time.time() >= next_ping:
                for s, targets in socks:
                    for target in targets:
                        try:
                            s.sendto(DISCOVERY_MAGIC, (target, DISCOVERY_PORT))
                        except OSError:
                            pass
                next_ping = time.time() + 1.0
            ready, _, _ = select.select([s for s, _ in socks], [], [], 0.2)
            for s in ready:
                try:
                    data, addr = s.recvfrom(1024)
                    info = json.loads(data.decode("utf-8"))
                except (OSError, ValueError):
                    continue
                found[addr[0]] = (addr[0], int(info.get("port", DEFAULT_PORT)), str(info.get("name", "?")))
            if found and first_only:
                break
    finally:
        for s, _ in socks:
            s.close()
    # реальные адреса Wi-Fi/Ethernet — вперёд, VPN-подсети (198.18.x, 10.x и т.п.) — в конец
    return sorted(found.values(), key=lambda f: (not f[0].startswith("192.168."), f[0]))
