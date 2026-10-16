"""
Smoke test for CI: sender with a test pattern → receiver over loopback, no virtual camera.
On macOS also checks that the AVFoundation capture module loads and enumerates devices.
"""

import os
import sys
import time
import traceback

sys.path.insert(0, ".")

from macbookcam.client import Bridge  # noqa: E402
from macbookcam.i18n import STRINGS, set_language, tr  # noqa: E402
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
        assert got > fps * 0.8, f"too few frames: {got:.1f}"
    finally:
        server.stop()
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        check_i18n()
        check_avfoundation()
        check_stream(30)
        check_stream(60)
    except BaseException:
        report(traceback.format_exc(), "error")
        sys.exit(1)
    print("OK")
