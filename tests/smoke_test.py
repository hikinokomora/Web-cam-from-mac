"""
Smoke test for CI: sender with a test pattern → receiver over loopback, no virtual camera.
On macOS also checks that the AVFoundation capture module loads and enumerates devices.
"""

import json
import os
import socket
import struct
import subprocess
import sys
import time
import traceback

sys.path.insert(0, ".")

from macbookcam.client import Bridge  # noqa: E402
from macbookcam.i18n import STRINGS, set_language, tr  # noqa: E402
from macbookcam.power import KeepAwake  # noqa: E402
from macbookcam.protocol import recv_exact, recv_line  # noqa: E402
from macbookcam.server import StreamServer  # noqa: E402

IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"


def report(msg, level="notice"):
    """In GitHub Actions also emit an annotation (readable through the public API)."""
    print(msg, flush=True)
    if IN_CI:
        text = f"{sys.platform}: {msg}".replace(chr(10), "%0A")
        print(f"::{level}::{text}", flush=True)


def check_i18n():
    assert set(STRINGS["en"]) == set(STRINGS["ru"]), "translation keys differ"
    for code in ("en", "ru"):
        set_language(code)
        assert tr("connect") != "connect"
    set_language("auto")


def check_avfoundation():
    if sys.platform != "darwin":
        return
    from macbookcam import avf_capture
    devices = avf_capture.list_devices()
    report(f"AVFoundation devices: {[str(d.localizedName()) for d in devices]}")
    try:
        avf_capture.AVFoundationSource(0, 1280, 720, 30).close()
        report("AVFoundation capture opened a camera")
    except RuntimeError as e:
        report(f"AVFoundation capture without a camera: {e}")


def check_stream(fps):
    server = StreamServer(port=5099, test_pattern=True)
    server.start()
    try:
        bridge = Bridge("127.0.0.1", 5099, 1280, 720, fps, 80, vcam=False, smoothing="auto")
        time.sleep(6)
        got = bridge.rx.stats_fps
        report(f"requested {fps} fps, received {got:.1f} fps, pacing {bridge.pacing_ms:.2f} ms, status: {bridge.status}")
        bridge.stop()
        assert got > fps * 0.6, f"too few frames: {got:.1f}"  # CI runners are slow and noisy
    finally:
        server.stop()
        time.sleep(0.5)


def check_takeover():
    """
    A new client must take over at once when the previous one vanished silently (Wi-Fi blip):
    before 1.2.1 the Mac kept serving the dead connection and the new client waited 10+ seconds.
    """
    port = 5097
    server = StreamServer(port=port, test_pattern=True)
    server.start()
    time.sleep(0.3)
    request = (json.dumps({"width": 640, "height": 360, "fps": 30, "quality": 70}) + "\n").encode()
    a = b = None
    try:
        a = socket.create_connection(("127.0.0.1", port), timeout=5)
        a.sendall(request)
        a.settimeout(5)
        recv_line(a)
        for _ in range(3):
            size, _ts = struct.unpack("!IQ", recv_exact(a, 12))
            recv_exact(a, size)
        # A now stops reading but keeps the socket open, like a PC that vanished from Wi-Fi
        started = time.time()
        b = socket.create_connection(("127.0.0.1", port), timeout=5)
        b.sendall(request)
        b.settimeout(10)
        info = json.loads(recv_line(b))
        size, _ts = struct.unpack("!IQ", recv_exact(b, 12))
        recv_exact(b, size)
        took = time.time() - started
        report(f"takeover: new client got its first frame after {took:.2f} s (Mac {info.get('app_version')})")
        assert took < 5, f"new client waited {took:.1f} s"
        assert info.get("app_version"), "Mac does not report its version"
    finally:
        for sock in (a, b):
            if sock is not None:
                sock.close()
        server.stop()
        time.sleep(0.5)


def check_keep_awake():
    keep = KeepAwake()
    keep.acquire()
    try:
        if sys.platform == "darwin":
            assert keep.active, "macOS activity (keep-awake) was not created"
            out = subprocess.run(["pmset", "-g", "assertions"], capture_output=True, text=True).stdout
            lines = [ln.strip() for ln in out.splitlines() if "MacBookCam" in ln or "python" in ln.lower()]
            report(f"keep-awake active; visible in pmset assertions: {bool(lines)} {lines[:2]}")
        else:
            assert not keep.active
    finally:
        keep.release()
    assert not keep.active


if __name__ == "__main__":
    try:
        check_i18n()
        check_avfoundation()
        check_keep_awake()
        check_takeover()
        check_stream(30)
        check_stream(60)
    except BaseException:
        report(traceback.format_exc(), "error")
        sys.exit(1)
    print("OK")
