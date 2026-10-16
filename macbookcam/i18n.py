"""Перевод интерфейса: английский и русский, язык по умолчанию — по системе."""

import locale
import sys

LANGUAGES = {"en": "English", "ru": "Русский"}

STRINGS = {
    "en": {
        # общее
        "language": "Language",
        "language_auto": "System",
        # ошибки камеры (коды приходят с Mac)
        "err_camera_open_failed": "Can't open the camera. Check camera access: System Settings → "
                                  "Privacy & Security → Camera.",
        "err_camera_no_frames": "The camera opened but doesn't deliver frames.",
        "err_camera_not_found": "No camera found on the Mac.",
        "err_camera_no_formats": "The camera reports no video formats.",
        "err_paused": "Streaming is paused on the Mac.",
        "err_internal": "Internal error on the Mac, see the log.",
        # журнал
        "log_discovery_unavailable": "Auto-discovery is unavailable ({error}); enter the IP on the PC manually.",
        "log_client_connected": "Client connected: {ip}",
        "log_connection_closed": "Connection closed: {error}",
        "log_client_request": "Client {ip} requested {w}x{h}@{fps}, JPEG {q}",
        "log_stream_started": "Streaming {info} (capture: {backend}, camera max {max_fps} fps)",
        "log_camera_off": "Camera off",
        "log_found": "Found {name} ({host}:{port})",
        "log_mac_stream": "Mac sends {w}x{h}@{fps}",
        "log_waiting": "MacBookCam is waiting for a connection on port {port}",
        "log_mac_ip": "  This Mac's IP: {ip}",
        "log_quit_hint": "Press Ctrl+C to quit",
        "log_quit": "Quitting",
        "log_requesting_access": "Requesting camera access — confirm in the dialog.",
        "log_access_denied": "No camera access: System Settings → Privacy & Security → Camera → "
                             "enable Terminal and restart it.",
        "log_no_cameras": "No cameras found (check camera access for Terminal)",
        "log_camera_entry": "  camera {i}: {name} {w}x{h}, up to {fps} fps",
        "log_vcam_failed": "Can't start the virtual camera: {error}",
        "log_vcam_install": "Install OBS Studio (https://obsproject.com) or run with --no-vcam --preview.",
        "log_vcam_ready": "Virtual camera: {name}. Select it as the camera in any app.",
        "log_nothing_to_do": "Nothing to do: virtual camera disabled and no --preview.",
        "log_stats": "{fps} fps, {mbps} Mbit/s, network jitter ±{jitter} ms, buffer {buffer} ms",
        # статусы приёмника
        "status_connecting": "Connecting...",
        "status_searching": "Searching for the Mac on the network...",
        "status_not_found": "Mac not found. Start MacBookCam on the Mac or enter its IP.",
        "status_no_link": "No connection to {host}: {error}",
        "status_connecting_to": "Connecting to {host}...",
        "status_connected": "Connected to {host}: {w}x{h}@{fps}",
        "status_disconnected": "Disconnected",
        # окно на ПК
        "preview_idle": "Not connected",
        "mac_auto": "Auto-detect",
        "ip_placeholder": "or IP manually, e.g. 192.168.1.66",
        "quality": "Quality",
        "fps_value": "{fps} fps",
        "jpeg_quality": "JPEG quality: {q}%",
        "smoothing": "Smoothing",
        "smoothing_off": "Off",
        "smoothing_auto": "Auto",
        "smoothing_strong": "Strong",
        "options": "Options",
        "mirror": "Mirror horizontally",
        "autoconnect": "Connect on startup",
        "connect": "Connect",
        "disconnect": "Disconnect",
        "starting": "Starting...",
        "vcam_hint": "In any app (video calls, streaming, browser) choose the camera "
                     "“OBS Virtual Camera”",
        "scan_running": "Searching for the Mac on the network...",
        "scan_manual_ready": "Press “Connect” to connect to {ip}.",
        "scan_found": "Found: {names}. Press “Connect”.",
        "scan_not_found": "No Mac found automatically. Enter the IP shown in the MacBookCam menu "
                          "on the Mac and press “Connect”.",
        "vcam_error_title": "No virtual camera",
        "vcam_error_text": "Can't start the virtual camera:\n{error}\n\n"
                           "MacBookCam needs OBS Studio installed (it provides the “OBS Virtual Camera” "
                           "driver). If OBS is running with its virtual camera on, stop it.\n\n"
                           "Open the OBS download page?",
        "stats_line": "{fps} fps · {mbps} Mbit/s · network jitter ±{jitter} ms · buffer {buffer} ms · "
                      "frame pacing ±{pacing} ms",
        "camera_fps_limit": "The Mac camera supports at most {max_fps} fps.",
        "camera_fallback": "The Mac uses the fallback capture (30 fps max): {reason}",
        "vcam_name": "Virtual camera: {name}",
        "vcam_placeholder": "Virtual camera: {name} (showing a placeholder)",
        # меню на Mac
        "mac_streaming_enabled": "Streaming enabled",
        "mac_disconnect_pc": "Disconnect PC",
        "mac_camera": "Camera",
        "mac_default_camera": "Default camera",
        "mac_launch_at_login": "Launch at login",
        "mac_camera_permissions": "Open camera permission settings",
        "mac_github": "Project on GitHub",
        "mac_about": "About (version {version})",
        "mac_about_text": "Version {version}\n\nUse this Mac's camera as a webcam on your PC.\n"
                          "On the PC, run MacBookCam for Windows and press “Connect”.",
        "mac_quit": "Quit",
        "mac_status_paused": "⏸ Streaming paused",
        "mac_status_streaming": "● Streaming to {ip}",
        "mac_status_waiting": "Waiting for the PC to connect",
        "mac_stats": "{fps} fps, {mbps} Mbit/s",
        "mac_ip": "This Mac's IP: {ips}  (click to copy)",
        "mac_no_network": "no network",
        "mac_notify_title": "Camera is streaming",
        "mac_notify_text": "Connected: {ip}",
        "mac_port_busy": "Can't open port {port}: {error}\n\n"
                         "MacBookCam may already be running (in Terminal or a second copy).",
        "mac_camera_denied": "MacBookCam has no camera access.\n\nEnable it: System Settings → "
                             "Privacy & Security → Camera → MacBookCam, then restart the app.",
        "mac_open_settings": "Open Settings",
        "mac_later": "Later",
        "mac_login_only_app": "Launch at login is only available in the built MacBookCam.app.",
    },
    "ru": {
        "language": "Язык",
        "language_auto": "Системный",
        "err_camera_open_failed": "Не удалось открыть камеру. Проверьте доступ: Системные настройки → "
                                  "Конфиденциальность и безопасность → Камера.",
        "err_camera_no_frames": "Камера открылась, но не отдаёт кадры.",
        "err_camera_not_found": "На Mac не найдено ни одной камеры.",
        "err_camera_no_formats": "Камера не сообщает ни одного видеоформата.",
        "err_paused": "Трансляция на Mac приостановлена.",
        "err_internal": "Внутренняя ошибка на Mac, смотрите журнал.",
        "log_discovery_unavailable": "Автообнаружение недоступно ({error}); на ПК укажите IP вручную.",
        "log_client_connected": "Подключился {ip}",
        "log_connection_closed": "Соединение закрыто: {error}",
        "log_client_request": "Клиент {ip} запросил {w}x{h}@{fps}, JPEG {q}",
        "log_stream_started": "Стрим {info} (захват: {backend}, максимум камеры {max_fps} к/с)",
        "log_camera_off": "Камера выключена",
        "log_found": "Найден {name} ({host}:{port})",
        "log_mac_stream": "Mac отдаёт {w}x{h}@{fps}",
        "log_waiting": "MacBookCam ждёт подключения на порту {port}",
        "log_mac_ip": "  IP этого Mac: {ip}",
        "log_quit_hint": "Ctrl+C — выход",
        "log_quit": "Выход",
        "log_requesting_access": "Запрашиваю доступ к камере — подтвердите в появившемся окне.",
        "log_access_denied": "Нет доступа к камере: Системные настройки → Конфиденциальность и безопасность → "
                             "Камера → включите Терминал и перезапустите его.",
        "log_no_cameras": "Камеры не найдены (проверьте доступ к камере для Терминала)",
        "log_camera_entry": "  камера {i}: {name} {w}x{h}, до {fps} к/с",
        "log_vcam_failed": "Не удалось создать виртуальную камеру: {error}",
        "log_vcam_install": "Установите OBS Studio (https://obsproject.com) или запустите с --no-vcam --preview.",
        "log_vcam_ready": "Виртуальная камера: {name}. Выберите её как камеру в нужной программе.",
        "log_nothing_to_do": "Нечего делать: виртуальная камера отключена и нет --preview.",
        "log_stats": "{fps} к/с, {mbps} Мбит/с, неровность сети ±{jitter} мс, буфер {buffer} мс",
        "status_connecting": "Подключение...",
        "status_searching": "Поиск Mac в сети...",
        "status_not_found": "Mac не найден. Запустите MacBookCam на Mac или укажите IP.",
        "status_no_link": "Нет связи с {host}: {error}",
        "status_connecting_to": "Подключение к {host}...",
        "status_connected": "Подключено к {host}: {w}x{h}@{fps}",
        "status_disconnected": "Отключено",
        "preview_idle": "Не подключено",
        "mac_auto": "Автопоиск",
        "ip_placeholder": "или IP вручную, напр. 192.168.1.66",
        "quality": "Качество",
        "fps_value": "{fps} к/с",
        "jpeg_quality": "Качество JPEG: {q}%",
        "smoothing": "Сглаживание",
        "smoothing_off": "Выкл",
        "smoothing_auto": "Авто",
        "smoothing_strong": "Сильное",
        "options": "Параметры",
        "mirror": "Отразить по горизонтали",
        "autoconnect": "Подключаться при запуске",
        "connect": "Подключить",
        "disconnect": "Отключить",
        "starting": "Запуск...",
        "vcam_hint": "В любой программе (видеозвонки, стриминг, браузер) выберите камеру "
                     "«OBS Virtual Camera»",
        "scan_running": "Ищу Mac в сети...",
        "scan_manual_ready": "Нажмите «Подключить» — подключение к {ip}.",
        "scan_found": "Найден: {names}. Нажмите «Подключить».",
        "scan_not_found": "Mac не найден автопоиском. Впишите IP из меню MacBookCam на Mac "
                          "и нажмите «Подключить».",
        "vcam_error_title": "Нет виртуальной камеры",
        "vcam_error_text": "Не удалось запустить виртуальную камеру:\n{error}\n\n"
                           "Нужна установленная OBS Studio (она даёт драйвер «OBS Virtual Camera»). "
                           "Если OBS запущена и в ней включена виртуальная камера — остановите её.\n\n"
                           "Открыть страницу загрузки OBS?",
        "stats_line": "{fps} к/с · {mbps} Мбит/с · неровность сети ±{jitter} мс · буфер {buffer} мс · "
                      "ровность кадров ±{pacing} мс",
        "camera_fps_limit": "Камера Mac выдаёт максимум {max_fps} к/с.",
        "camera_fallback": "Mac использует запасной захват (до 30 к/с): {reason}",
        "vcam_name": "Виртуальная камера: {name}",
        "vcam_placeholder": "Виртуальная камера: {name} (показывает заглушку)",
        "mac_streaming_enabled": "Трансляция включена",
        "mac_disconnect_pc": "Отключить ПК",
        "mac_camera": "Камера",
        "mac_default_camera": "Камера по умолчанию",
        "mac_launch_at_login": "Запускать при входе в систему",
        "mac_camera_permissions": "Открыть настройки доступа к камере",
        "mac_github": "Проект на GitHub",
        "mac_about": "О программе (версия {version})",
        "mac_about_text": "Версия {version}\n\nКамера этого Mac как веб-камера на ПК.\n"
                          "На ПК запустите MacBookCam для Windows и нажмите «Подключить».",
        "mac_quit": "Выход",
        "mac_status_paused": "⏸ Трансляция приостановлена",
        "mac_status_streaming": "● Камера передаётся на {ip}",
        "mac_status_waiting": "Ожидание подключения ПК",
        "mac_stats": "{fps} к/с, {mbps} Мбит/с",
        "mac_ip": "IP этого Mac: {ips}  (нажмите, чтобы скопировать)",
        "mac_no_network": "нет сети",
        "mac_notify_title": "Камера передаётся",
        "mac_notify_text": "Подключился {ip}",
        "mac_port_busy": "Не удалось открыть порт {port}: {error}\n\n"
                         "Возможно, MacBookCam уже запущен (в Терминале или вторая копия).",
        "mac_camera_denied": "У MacBookCam нет доступа к камере.\n\nВключите его: Системные настройки → "
                             "Конфиденциальность и безопасность → Камера → MacBookCam, затем перезапустите "
                             "приложение.",
        "mac_open_settings": "Открыть настройки",
        "mac_later": "Позже",
        "mac_login_only_app": "Автозапуск доступен только для собранного MacBookCam.app.",
    },
}

RUSSIAN_LIKE = ("ru", "uk", "be")


def system_language():
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = langid & 0x3FF
            code = {0x19: "ru", 0x22: "uk", 0x23: "be"}.get(primary, "en")
        elif sys.platform == "darwin":
            from Foundation import NSLocale
            langs = NSLocale.preferredLanguages()
            code = str(langs[0]) if langs else ""
        else:
            code = (locale.getlocale()[0] or "")
    except Exception:  # noqa: BLE001
        code = ""
    return "ru" if code.lower().startswith(RUSSIAN_LIKE) else "en"


class _Translator:
    def __init__(self):
        self.lang = system_language()

    def set(self, code):
        self.lang = code if code in STRINGS else system_language()

    def has(self, key):
        return key in STRINGS["en"]

    def __call__(self, key, **kwargs):
        text = STRINGS[self.lang].get(key) or STRINGS["en"].get(key) or key
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text


tr = _Translator()


def set_language(code):
    """code: 'auto' | 'en' | 'ru'."""
    tr.set(code)
