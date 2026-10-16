#!/usr/bin/env python3
"""
MacBookCam — консольный сервер на Mac (без интерфейса).

Запуск:
    python3 mac_sender.py                # камера 0, порт 5005
    python3 mac_sender.py --list         # показать доступные камеры
    python3 mac_sender.py --camera 1     # выбрать другую камеру
    python3 mac_sender.py --test-pattern # без камеры, тестовая картинка
"""

import argparse
import os
import sys
import time

# OpenCV не может запросить доступ к камере из фонового потока — делаем это сами
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

from macbookcam.protocol import DEFAULT_PORT, get_local_ips, log  # noqa: E402
from macbookcam.server import (StreamServer, camera_auth_status, camera_names,  # noqa: E402
                               probe_cameras, request_camera_access)


def main():
    p = argparse.ArgumentParser(description="MacBookCam: отдаёт камеру Mac по сети")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--camera", type=int, default=0, help="индекс камеры (см. --list)")
    p.add_argument("--list", action="store_true", help="показать камеры и выйти")
    p.add_argument("--quality", type=int, default=80, help="качество JPEG по умолчанию, 1-100")
    p.add_argument("--test-pattern", action="store_true", help="тестовая картинка вместо камеры")
    args = p.parse_args()

    if sys.platform == "darwin" and not args.test_pattern:
        status = camera_auth_status()
        if status == "undetermined":
            log("Запрашиваю доступ к камере — подтвердите в появившемся окне.")
            request_camera_access()
        elif status == "denied":
            log("Нет доступа к камере: Системные настройки → Конфиденциальность и безопасность → "
                "Камера → включите Терминал и перезапустите его.")

    if args.list:
        names = camera_names()
        cams = probe_cameras()
        if not cams:
            print("Камеры не найдены (проверьте разрешение на доступ к камере для Терминала)")
        for i, w, h in cams:
            name = names[i] if i < len(names) else ""
            print(f"  камера {i}: {name} {w}x{h}")
        return

    server = StreamServer(port=args.port, camera=args.camera,
                          test_pattern=args.test_pattern, default_quality=args.quality)
    server.start()
    log(f"MacBookCam ждёт подключения на порту {args.port}")
    for ip in get_local_ips():
        log(f"  IP этого Mac: {ip}")
    log("Ctrl+C — выход")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Выход")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
