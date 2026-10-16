"""
MacBookCam — приложение для macOS: значок в строке меню.

Раздаёт камеру Mac по сети приёмнику на ПК. Камера включается только пока ПК подключён.
"""

import os
import plistlib
import subprocess
import sys

# OpenCV не может сам запросить доступ к камере из фонового потока —
# запрашиваем его сами в главном потоке (см. ensure_camera_access).
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import rumps  # noqa: E402

from macbookcam import __version__  # noqa: E402
from macbookcam.protocol import DEFAULT_PORT, get_local_ips  # noqa: E402
from macbookcam.server import (StreamServer, camera_auth_status, camera_names,  # noqa: E402
                               request_camera_access)

APP_NAME = "MacBookCam"
BUNDLE_ID = "com.hikinokomora.macbookcam"
LAUNCH_AGENT = os.path.expanduser(f"~/Library/LaunchAgents/{BUNDLE_ID}.plist")
CAMERA_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def app_bundle_path():
    """Путь к MacBookCam.app, если запущены из собранного приложения."""
    exe = os.path.abspath(sys.executable)
    marker = ".app/Contents/MacOS/"
    if getattr(sys, "frozen", False) and marker in exe:
        return exe[:exe.index(marker) + 4]
    return None


class MacBookCamApp(rumps.App):
    def __init__(self):
        super().__init__(APP_NAME, icon=resource_path("assets/menubar.png"), template=True,
                         quit_button=None)
        self.server = StreamServer(port=DEFAULT_PORT)
        self._last_client = None

        self.status_item = rumps.MenuItem("Запуск...")
        self.stats_item = rumps.MenuItem("")
        self.ip_item = rumps.MenuItem("", callback=self.copy_ip)
        self.enabled_item = rumps.MenuItem("Трансляция включена", callback=self.toggle_enabled)
        self.enabled_item.state = 1
        self.kick_item = rumps.MenuItem("Отключить ПК", callback=self.kick)
        self.camera_menu = rumps.MenuItem("Камера")
        self.login_item = rumps.MenuItem("Запускать при входе в систему", callback=self.toggle_login)
        self.login_item.state = int(os.path.exists(LAUNCH_AGENT))

        self.menu = [
            self.status_item,
            self.stats_item,
            self.ip_item,
            None,
            self.enabled_item,
            self.camera_menu,
            self.kick_item,
            None,
            self.login_item,
            rumps.MenuItem("Открыть настройки доступа к камере", callback=self.open_camera_settings),
            None,
            rumps.MenuItem(f"О программе (версия {__version__})", callback=self.about),
            rumps.MenuItem("Выход", callback=self.quit, key="q"),
        ]
        self._fill_cameras()
        self.refresh(None)
        self.timer = rumps.Timer(self.refresh, 1)
        self.timer.start()
        rumps.Timer(self.startup, 0.3).start()

    # --- старт ---

    def startup(self, sender):
        sender.stop()
        status = camera_auth_status()
        if status == "undetermined":
            request_camera_access()
        elif status == "denied":
            self.camera_denied_alert()
        try:
            self.server.start()
        except OSError as e:
            rumps.alert(APP_NAME, f"Не удалось открыть порт {DEFAULT_PORT}: {e}\n\n"
                                  "Возможно, MacBookCam уже запущен (в Терминале или вторая копия).")
            rumps.quit_application()

    def camera_denied_alert(self):
        if rumps.alert(APP_NAME, "У MacBookCam нет доступа к камере.\n\n"
                                 "Включите его: Системные настройки → Конфиденциальность и безопасность → "
                                 "Камера → MacBookCam, затем перезапустите приложение.",
                       ok="Открыть настройки", cancel="Позже"):
            self.open_camera_settings(None)

    # --- меню ---

    def _fill_cameras(self):
        names = camera_names() or ["Камера по умолчанию"]
        for i, name in enumerate(names):
            item = rumps.MenuItem(name, callback=self.select_camera)
            item.camera_index = i
            item.state = int(i == self.server.camera)
            self.camera_menu.add(item)

    def select_camera(self, sender):
        for item in self.camera_menu.values():
            item.state = int(item is sender)
        self.server.set_camera(sender.camera_index)

    def toggle_enabled(self, sender):
        sender.state = int(not sender.state)
        self.server.set_enabled(bool(sender.state))
        self.refresh(None)

    def kick(self, _sender):
        self.server.kick()

    def copy_ip(self, _sender):
        ips = get_local_ips()
        if ips:
            subprocess.run(["pbcopy"], input=ips[0].encode(), check=False)

    def open_camera_settings(self, _sender):
        subprocess.run(["open", CAMERA_SETTINGS_URL], check=False)

    def toggle_login(self, sender):
        if sender.state:
            try:
                os.remove(LAUNCH_AGENT)
            except OSError:
                pass
            sender.state = 0
            return
        bundle = app_bundle_path()
        if not bundle:
            rumps.alert(APP_NAME, "Автозапуск доступен только для собранного MacBookCam.app.")
            return
        os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump({"Label": BUNDLE_ID,
                           "ProgramArguments": ["/usr/bin/open", "-a", bundle],
                           "RunAtLoad": True}, f)
        sender.state = 1

    def about(self, _sender):
        rumps.alert(APP_NAME, f"Версия {__version__}\n\nКамера этого Mac как веб-камера на ПК.\n"
                              "На ПК запустите MacBookCam для Windows и нажмите «Подключить».")

    def quit(self, _sender):
        self.server.stop()
        rumps.quit_application()

    # --- обновление статуса (главный поток) ---

    def refresh(self, _sender):
        s = self.server
        if not s.enabled:
            status = "⏸ Трансляция приостановлена"
        elif s.client:
            status = f"● Камера передаётся на {s.client}" + (f" ({s.stream_info})" if s.stream_info else "")
        elif s.last_error:
            status = "⚠ " + s.last_error
        else:
            status = "Ожидание подключения ПК"
        self.status_item.title = status
        self.stats_item.title = s.stats if s.client else ""
        ips = get_local_ips()
        self.ip_item.title = f"IP этого Mac: {', '.join(ips) if ips else 'нет сети'}  (нажмите, чтобы скопировать)"
        self.kick_item.set_callback(self.kick if s.client else None)

        if s.client != self._last_client:
            if s.client:
                self._notify("Камера передаётся", f"Подключился {s.client}")
            self._last_client = s.client
        if "доступ" in s.last_error.lower() or "открыть камеру" in s.last_error.lower():
            if camera_auth_status() == "denied":
                s.last_error = ""
                self.camera_denied_alert()

    def _notify(self, title, text):
        try:
            rumps.notification(APP_NAME, title, text, sound=False)
        except Exception:  # noqa: BLE001
            pass


def main():
    try:
        import AppKit
        # Без значка в Dock — только в строке меню
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:  # noqa: BLE001
        pass
    MacBookCamApp().run()


if __name__ == "__main__":
    main()
