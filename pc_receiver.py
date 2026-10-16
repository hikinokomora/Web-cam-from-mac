#!/usr/bin/env python3
"""
MacBookCam — console receiver for Windows (the window app is pc_app.py).

Usage:
    python pc_receiver.py                      # find the Mac automatically
    python pc_receiver.py --host 192.168.1.5   # or give its IP
    python pc_receiver.py --fps 60 --smoothing off
    python pc_receiver.py --no-vcam --preview  # preview window only, no virtual camera
"""

import argparse
import time

from macbookcam.client import SMOOTHING, Bridge
from macbookcam.i18n import set_language, tr
from macbookcam.protocol import DEFAULT_PORT, log


def main():
    p = argparse.ArgumentParser(description="MacBookCam: Mac camera as a virtual webcam on the PC")
    p.add_argument("--host", help="Mac IP address (default: auto-detect)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--quality", type=int, default=80, help="JPEG quality on the Mac, 1-100")
    p.add_argument("--smoothing", default="auto", choices=list(SMOOTHING), help="jitter buffer mode")
    p.add_argument("--mirror", action="store_true", help="mirror horizontally")
    p.add_argument("--preview", action="store_true", help="show a preview window")
    p.add_argument("--no-vcam", action="store_true", help="don't create a virtual camera")
    p.add_argument("--backend", default=None, help="pyvirtualcam backend: obs or unitycapture")
    p.add_argument("--lang", default="auto", choices=["auto", "en", "ru"], help="message language")
    args = p.parse_args()
    set_language(args.lang)

    if args.no_vcam and not args.preview:
        log(tr("log_nothing_to_do"))
        return

    try:
        bridge = Bridge(args.host, args.port, args.width, args.height, args.fps, args.quality,
                        args.mirror, vcam=not args.no_vcam, backend=args.backend, smoothing=args.smoothing)
    except Exception as e:  # noqa: BLE001
        log(tr("log_vcam_failed", error=e))
        log(tr("log_vcam_install"))
        return
    if bridge.vcam_name:
        log(tr("log_vcam_ready", name=bridge.vcam_name))

    if args.preview:
        import cv2  # только для окна предпросмотра
        import numpy as np

    last_stats = time.time()
    try:
        while True:
            if args.preview:
                if bridge.output is not None:
                    cv2.imshow("MacBookCam (Esc)", np.asarray(bridge.output)[:, :, ::-1])
                if cv2.waitKey(15) & 0xFF == 27:
                    break
            else:
                time.sleep(0.2)
            if time.time() - last_stats >= 5 and bridge.connected:
                log(tr("log_stats", fps=f"{bridge.rx.stats_fps:.1f}", mbps=f"{bridge.rx.stats_mbps:.1f}",
                       jitter=f"{bridge.jitter_ms:.0f}", buffer=f"{bridge.buffer_ms:.0f}"))
                last_stats = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        log(tr("log_quit"))
        bridge.stop()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
