#!/usr/bin/env python3
"""
MacBookCam — console sender for macOS (no menu bar icon).

Usage:
    python3 mac_sender.py                # camera 0, port 5005
    python3 mac_sender.py --list         # list cameras
    python3 mac_sender.py --camera 1     # pick another camera
    python3 mac_sender.py --test-pattern # synthetic picture instead of a camera
"""

import argparse
import os
import sys
import time

# OpenCV (fallback capture) can't request camera access from a background thread — we do it ourselves
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

from macbookcam.i18n import set_language, tr  # noqa: E402
from macbookcam.protocol import DEFAULT_PORT, get_local_ips, log  # noqa: E402
from macbookcam.server import (StreamServer, camera_auth_status, camera_names,  # noqa: E402
                               probe_cameras, request_camera_access)


def main():
    p = argparse.ArgumentParser(description="MacBookCam: stream this Mac's camera over the network")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--camera", type=int, default=0, help="camera index (see --list)")
    p.add_argument("--list", action="store_true", help="list cameras and exit")
    p.add_argument("--quality", type=int, default=80, help="default JPEG quality, 1-100")
    p.add_argument("--test-pattern", action="store_true", help="synthetic picture instead of a camera")
    p.add_argument("--lang", default="auto", choices=["auto", "en", "ru"], help="message language")
    args = p.parse_args()
    set_language(args.lang)

    if sys.platform == "darwin" and not args.test_pattern:
        status = camera_auth_status()
        if status == "undetermined":
            log(tr("log_requesting_access"))
            request_camera_access()
        elif status == "denied":
            log(tr("log_access_denied"))

    if args.list:
        names = camera_names()
        cams = probe_cameras()
        if not cams:
            print(tr("log_no_cameras"))
        for i, w, h, fps in cams:
            name = names[i] if i < len(names) else ""
            print(tr("log_camera_entry", i=i, name=name, w=w, h=h, fps=round(fps)))
        return

    server = StreamServer(port=args.port, camera=args.camera,
                          test_pattern=args.test_pattern, default_quality=args.quality)
    server.start()
    log(tr("log_waiting", port=args.port))
    for ip in get_local_ips():
        log(tr("log_mac_ip", ip=ip))
    log(tr("log_quit_hint"))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log(tr("log_quit"))
    finally:
        server.stop()


if __name__ == "__main__":
    main()
