"""
MacBookCam — приложение для macOS: значок в строке меню.

Раздаёт камеру Mac по сети приёмнику на ПК. Камера включается только пока ПК подключён.
"""

import json
import os
import plistlib
import subprocess
import sys

# OpenCV (запасной захват) не может сам запросить доступ к камере из фонового потока —
# запрашиваем его сами в главном потоке.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import rumps  # noqa: E402

from macbookcam import __version__  # noqa: E402
from macbookcam.i18n import LANGUAGES, set_language, tr  # noqa: E402
from macbookcam.protocol import DEFAULT_PORT, get_local_ips, set_log_file  # noqa: E402
from macbookcam.server import (StreamServer, camera_auth_status, camera_names,  # noqa: E402
                               request_camera_access)

APP_NAME = "MacBookCam"
BUNDLE_ID = "com.hikinokomora.macbookcam"
LAUNCH_AGENT = os.path.expanduser(f"~/Library/LaunchAgents/{BUNDLE_ID}.plist")
SETTINGS_PATH = os.path.expanduser("~/Library/Application Support/MacBookCam/settings.json")
CAMERA_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
REPO_URL = "https://github.com/hikinokomora/Web-cam-from-mac"


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


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return {"language": "auto", "camera": 0, **json.load(f)}
    except (OSError, ValueError):
        return {"language": "auto", "camera": 0}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class MacBookCamApp(rumps.App):
    def __init__(self):
        super().__init__(APP_NAME, icon=resource_path("assets/menubar.png"), template=True,
                         quit_button=None)
        self.settings = load_settings()
        set_language(self.settings["language"])
        self.server = StreamServer(port=DEFAULT_PORT, camera=int(self.settings["camera"]))
        self._last_client = None

        self.status_item = rumps.MenuItem("")
        self.stats_item = rumps.MenuItem("")
        self.ip_item = rumps.MenuItem("", callback=self.copy_ip)
        self.enabled_item = rumps.MenuItem("", callback=self.toggle_enabled)
        self.enabled_item.state = 1
        self.kick_item = rumps.MenuItem("", callback=self.kick)
        self.camera_menu = rumps.MenuItem("camera")
        self.language_menu = rumps.MenuItem("language")
        self.login_item = rumps.MenuItem("", callback=self.toggle_login)
        self.login_item.state = int(os.path.exists(LAUNCH_AGENT))
        self.permissions_item = rumps.MenuItem("", callback=self.open_camera_settings)
        self.github_item = rumps.MenuItem("", callback=self.open_github)
        self.about_item = rumps.MenuItem("", callback=self.about)
        self.quit_item = rumps.MenuItem("", callback=self.quit, key="q")

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
            self.language_menu,
            self.permissions_item,
            None,
            self.github_item,
            self.about_item,
            self.quit_item,
        ]
        self._fill_cameras()
        self._fill_languages()
        self._apply_texts()
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
            rumps.alert(APP_NAME, tr("mac_port_busy", port=DEFAULT_PORT, error=e))
            rumps.quit_application()

    def camera_denied_alert(self):
        if rumps.alert(APP_NAME, tr("mac_camera_denied"), ok=tr("mac_open_settings"), cancel=tr("mac_later")):
            self.open_camera_settings(None)

    # --- меню ---

    def _apply_texts(self):
        self.enabled_item.title = tr("mac_streaming_enabled")
        self.kick_item.title = tr("mac_disconnect_pc")
        self.camera_menu.title = tr("mac_camera")
        self.language_menu.title = tr("language")
        self.login_item.title = tr("mac_launch_at_login")
        self.permissions_item.title = tr("mac_camera_permissions")
        self.github_item.title = tr("mac_github")
        self.about_item.title = tr("mac_about", version=__version__)
        self.quit_item.title = tr("mac_quit")
        for code, item in self.language_menu.items():
            if code == "auto":
                item.title = tr("language_auto")

    def _fill_cameras(self):
        names = camera_names() or [tr("mac_default_camera")]
        if self.server.camera >= len(names):
            self.server.camera = 0
        for i, name in enumerate(names):
            item = rumps.MenuItem(name, callback=self.select_camera)
            item.camera_index = i
            item.state = int(i == self.server.camera)
            self.camera_menu.add(item)

    def _fill_languages(self):
        for code in ["auto"] + list(LANGUAGES):
            item = rumps.MenuItem(LANGUAGES.get(code, code), callback=self.select_language)
            item.language_code = code
            item.state = int(code == self.settings["language"])
            self.language_menu[code] = item

    def select_camera(self, sender):
        for item in self.camera_menu.values():
            item.state = int(item is sender)
        self.server.set_camera(sender.camera_index)
        self.settings["camera"] = sender.camera_index
        save_settings(self.settings)

    def select_language(self, sender):
        for item in self.language_menu.values():
            item.state = int(item is sender)
        self.settings["language"] = sender.language_code
        save_settings(self.settings)
        set_language(sender.language_code)
        self._apply_texts()
        self.refresh(None)

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

    def open_github(self, _sender):
        subprocess.run(["open", REPO_URL], check=False)

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
            rumps.alert(APP_NAME, tr("mac_login_only_app"))
            return
        os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as f:
            plistlib.dump({"Label": BUNDLE_ID,
                           "ProgramArguments": ["/usr/bin/open", "-a", bundle],
                           "RunAtLoad": True}, f)
        sender.state = 1

    def about(self, _sender):
        rumps.alert(APP_NAME, tr("mac_about_text", version=__version__))

    def quit(self, _sender):
        self.server.stop()
        rumps.quit_application()

    # --- обновление статуса (главный поток) ---

    def refresh(self, _sender):
        s = self.server
        if not s.enabled:
            status = tr("mac_status_paused")
        elif s.client:
            status = tr("mac_status_streaming", ip=s.client) + (f" ({s.stream_info})" if s.stream_info else "")
        elif s.error_code:
            status = "⚠ " + tr("err_" + s.error_code)
        else:
            status = tr("mac_status_waiting")
        self.status_item.title = status
        if s.client and s.stats_fps:
            self.stats_item.title = tr("mac_stats", fps=f"{s.stats_fps:.0f}", mbps=f"{s.stats_mbps:.1f}")
        else:
            self.stats_item.title = ""
        ips = get_local_ips()
        self.ip_item.title = tr("mac_ip", ips=", ".join(ips) if ips else tr("mac_no_network"))
        self.kick_item.set_callback(self.kick if s.client else None)

        if s.client != self._last_client:
            if s.client:
                self._notify(tr("mac_notify_title"), tr("mac_notify_text", ip=s.client))
            self._last_client = s.client
        if s.error_code in ("camera_open_failed", "camera_no_frames") and camera_auth_status() == "denied":
            s.error_code = ""
            self.camera_denied_alert()

    def _notify(self, title, text):
        try:
            rumps.notification(APP_NAME, title, text, sound=False)
        except Exception:  # noqa: BLE001
            pass


def main():
    set_log_file(os.path.expanduser("~/Library/Logs/MacBookCam.log"))
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
