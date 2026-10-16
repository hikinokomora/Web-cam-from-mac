#!/usr/bin/env python3
"""
MacBookCam — консольный приёмник на ПК (без интерфейса; окно — pc_app.py).

Запуск:
    python pc_receiver.py                    # найти Mac в сети автоматически
    python pc_receiver.py --host 192.168.1.5 # указать IP Mac вручную
    python pc_receiver.py --preview          # дополнительно показать окно предпросмотра
    python pc_receiver.py --no-vcam --preview  # только окно, без виртуальной камеры
"""

import argparse
import time

import cv2

from macbookcam.client import Bridge
from macbookcam.protocol import DEFAULT_PORT, log


def main():
    p = argparse.ArgumentParser(description="MacBookCam: камера Mac как виртуальная камера на ПК")
    p.add_argument("--host", help="IP-адрес Mac (по умолчанию — автопоиск)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--quality", type=int, default=80, help="качество JPEG на Mac, 1-100")
    p.add_argument("--mirror", action="store_true", help="отразить по горизонтали")
    p.add_argument("--preview", action="store_true", help="показать окно предпросмотра")
    p.add_argument("--no-vcam", action="store_true", help="не создавать виртуальную камеру")
    p.add_argument("--backend", default=None, help="бэкенд pyvirtualcam: obs или unitycapture")
    args = p.parse_args()

    if args.no_vcam and not args.preview:
        log("Нечего делать: виртуальная камера отключена и нет --preview.")
        return

    try:
        bridge = Bridge(args.host, args.port, args.width, args.height, args.fps,
                        args.quality, args.mirror, vcam=not args.no_vcam, backend=args.backend)
    except Exception as e:  # noqa: BLE001
        log(f"Не удалось создать виртуальную камеру: {e}")
        log("Установите OBS Studio (https://obsproject.com) или запустите с --no-vcam --preview.")
        return
    if bridge.vcam_name:
        log(f"Виртуальная камера: {bridge.vcam_name}. В Zoom выберите её в настройках видео.")

    last_stats = time.time()
    try:
        while True:
            if args.preview:
                if bridge.output is not None:
                    cv2.imshow("MacBookCam (Esc - exit)", bridge.output)
                if cv2.waitKey(30) & 0xFF == 27:
                    break
            else:
                time.sleep(0.2)
            if time.time() - last_stats >= 5 and bridge.connected:
                age = bridge.frame_age_ms() or 0
                log(f"{bridge.rx.stats_fps:.1f} к/с, {bridge.rx.stats_mbps:.1f} Мбит/с, "
                    f"возраст кадра {age:.0f} мс")
                last_stats = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        log("Выход")
        bridge.stop()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
