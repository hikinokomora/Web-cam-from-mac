"""
MacBookCam — приложение для Windows.

Окно: выбор Mac в сети, качество, сглаживание, предпросмотр. Видео уходит в виртуальную
камеру «OBS Virtual Camera», которую можно выбрать в любой программе (видеозвонки,
стриминг, браузер).
"""

import json
import os
import sys
import threading
import tkinter.messagebox as messagebox
import webbrowser

import customtkinter as ctk
import cv2
from PIL import Image

from macbookcam import __version__
from macbookcam.client import Bridge
from macbookcam.i18n import LANGUAGES, set_language, tr
from macbookcam.protocol import DEFAULT_PORT, discover

RESOLUTIONS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
FPS_OPTIONS = ["15", "24", "30", "60"]
SMOOTHING_OPTIONS = ["off", "auto", "strong"]
AUTO = "__auto__"
PREVIEW_W, PREVIEW_H = 560, 315
REPO_URL = "https://github.com/hikinokomora/Web-cam-from-mac"

SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "MacBookCam", "settings.json")
DEFAULTS = {"mac": AUTO, "manual_ip": "", "resolution": "720p", "fps": "30",
            "quality": 80, "mirror": False, "autoconnect": False,
            "smoothing": "auto", "language": "auto"}


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8-sig") as f:
            data = {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if data["mac"] in ("Автопоиск", "Auto"):  # формат версий 1.0.x
        data["mac"] = AUTO
    return data


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        set_language(self.settings["language"])
        self.geometry("940x580")
        self.minsize(940, 580)
        try:
            self.iconbitmap(resource_path("assets/icon.ico"))
        except Exception:  # noqa: BLE001
            pass

        self.bridge = None
        self.found = []     # [(host, port, name)]
        self._scanning = False
        self._preview_img = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.scan)
        if self.settings["autoconnect"]:
            self.after(600, self.toggle_connection)
        self.after(66, self.tick)

    # --- разметка ---

    def _build_ui(self):
        self.title(f"MacBookCam {__version__}")
        self._build_preview()
        self._build_controls()
        if self.bridge:
            self._set_connected_ui(True)

    def _rebuild_ui(self):
        self._collect_settings()
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()
        self._fill_mac_menu()

    def _build_preview(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        left.grid_rowconfigure(3, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.preview = ctk.CTkLabel(left, text=tr("preview_idle"), width=PREVIEW_W, height=PREVIEW_H,
                                    fg_color=("gray75", "gray8"), corner_radius=8,
                                    text_color=("gray35", "gray55"))
        self.preview.grid(row=0, column=0, sticky="n")

        self.status = ctk.CTkLabel(left, text="", anchor="w", justify="left", wraplength=PREVIEW_W)
        self.status.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.stats = ctk.CTkLabel(left, text="", anchor="w", justify="left", wraplength=PREVIEW_W,
                                  text_color=("gray40", "gray60"))
        self.stats.grid(row=2, column=0, sticky="ew")

        links = ctk.CTkFrame(left, fg_color="transparent")
        links.grid(row=4, column=0, sticky="sw")
        ctk.CTkLabel(links, text=tr("language") + ":", text_color=("gray40", "gray60")).pack(side="left")
        names = [tr("language_auto")] + [LANGUAGES[c] for c in LANGUAGES]
        self.lang_menu = ctk.CTkOptionMenu(links, values=names, width=120, command=self._change_language)
        current = self.settings["language"]
        self.lang_menu.set(LANGUAGES.get(current, tr("language_auto")))
        self.lang_menu.pack(side="left", padx=(6, 12))
        ctk.CTkButton(links, text="GitHub", width=70, fg_color="transparent", border_width=1,
                      text_color=("gray20", "gray80"),
                      command=lambda: webbrowser.open(REPO_URL)).pack(side="left")

    def _build_controls(self):
        right = ctk.CTkFrame(self, width=300)
        right.grid(row=0, column=1, sticky="ns", padx=(8, 16), pady=16)
        right.grid_columnconfigure(0, weight=1)
        pad = {"padx": 14, "sticky": "ew"}
        row = 0

        def label(text):
            nonlocal row
            ctk.CTkLabel(right, text=text, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
                row=row, column=0, pady=(12 if row else 14, 2), **pad)
            row += 1

        label("Mac")
        mac_row = ctk.CTkFrame(right, fg_color="transparent")
        mac_row.grid(row=row, column=0, **pad)
        mac_row.grid_columnconfigure(0, weight=1)
        self.mac_menu = ctk.CTkOptionMenu(mac_row, values=[tr("mac_auto")], dynamic_resizing=False)
        self.mac_menu.grid(row=0, column=0, sticky="ew")
        self.scan_btn = ctk.CTkButton(mac_row, text="↻", width=32, command=self.scan)
        self.scan_btn.grid(row=0, column=1, padx=(6, 0))
        row += 1
        self.ip_entry = ctk.CTkEntry(right, placeholder_text=tr("ip_placeholder"))
        self.ip_entry.grid(row=row, column=0, pady=(6, 0), **pad)
        if self.settings["manual_ip"]:
            self.ip_entry.insert(0, self.settings["manual_ip"])
        row += 1

        label(tr("quality"))
        q_row = ctk.CTkFrame(right, fg_color="transparent")
        q_row.grid(row=row, column=0, **pad)
        q_row.grid_columnconfigure((0, 1), weight=1)
        self.res_menu = ctk.CTkOptionMenu(q_row, values=list(RESOLUTIONS), width=110)
        self.res_menu.set(self.settings["resolution"])
        self.res_menu.grid(row=0, column=0, sticky="ew")
        self._fps_labels = {f: tr("fps_value", fps=f) for f in FPS_OPTIONS}
        self.fps_menu = ctk.CTkOptionMenu(q_row, values=list(self._fps_labels.values()), width=110)
        self.fps_menu.set(self._fps_labels.get(self.settings["fps"], self._fps_labels["30"]))
        self.fps_menu.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        row += 1

        self.quality_label = ctk.CTkLabel(right, text="", anchor="w")
        self.quality_label.grid(row=row, column=0, pady=(8, 0), **pad)
        row += 1
        self.quality = ctk.CTkSlider(right, from_=40, to=95, number_of_steps=11,
                                     command=lambda _v: self._update_quality_label())
        self.quality.set(self.settings["quality"])
        self.quality.grid(row=row, column=0, **pad)
        row += 1
        self._update_quality_label()

        label(tr("smoothing"))
        self._smooth_labels = {k: tr("smoothing_" + k) for k in SMOOTHING_OPTIONS}
        self.smooth_menu = ctk.CTkSegmentedButton(right, values=list(self._smooth_labels.values()),
                                                  command=self._apply_smoothing)
        self.smooth_menu.set(self._smooth_labels.get(self.settings["smoothing"], self._smooth_labels["auto"]))
        self.smooth_menu.grid(row=row, column=0, **pad)
        row += 1

        label(tr("options"))
        self.mirror = ctk.CTkSwitch(right, text=tr("mirror"), command=self._apply_mirror)
        if self.settings["mirror"]:
            self.mirror.select()
        self.mirror.grid(row=row, column=0, pady=2, **pad)
        row += 1
        self.autoconnect = ctk.CTkSwitch(right, text=tr("autoconnect"))
        if self.settings["autoconnect"]:
            self.autoconnect.select()
        self.autoconnect.grid(row=row, column=0, pady=2, **pad)
        row += 1

        right.grid_rowconfigure(row, weight=1)
        row += 1
        self.connect_btn = ctk.CTkButton(right, text=tr("connect"), height=40,
                                         font=ctk.CTkFont(size=15, weight="bold"),
                                         command=self.toggle_connection)
        self.connect_btn.grid(row=row, column=0, pady=(12, 6), **pad)
        row += 1
        self.hint = ctk.CTkLabel(right, text=tr("vcam_hint"), wraplength=260,
                                 text_color=("gray40", "gray60"), justify="center")
        self.hint.grid(row=row, column=0, pady=(0, 12), **pad)

    def _update_quality_label(self):
        self.quality_label.configure(text=tr("jpeg_quality", q=int(self.quality.get())))

    def _apply_mirror(self):
        if self.bridge:
            self.bridge.mirror = bool(self.mirror.get())

    def _smoothing_key(self):
        label = self.smooth_menu.get()
        return next((k for k, v in self._smooth_labels.items() if v == label), "auto")

    def _apply_smoothing(self, _value=None):
        if self.bridge:
            self.bridge.smoothing = self._smoothing_key()

    def _fps_value(self):
        label = self.fps_menu.get()
        return next((k for k, v in self._fps_labels.items() if v == label), "30")

    def _change_language(self, name):
        code = next((c for c, n in LANGUAGES.items() if n == name), "auto")
        self.settings["language"] = code
        set_language(code)
        self._rebuild_ui()
        self.save()

    # --- поиск Mac ---

    def scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled")
        self.status.configure(text=tr("scan_running"))

        def work():
            found = discover(timeout=2.0, first_only=False)
            self.after(0, lambda: self._scan_done(found))

        threading.Thread(target=work, daemon=True).start()

    def _mac_label(self, host, name):
        return f"{name} ({host})"

    def _fill_mac_menu(self):
        values = [tr("mac_auto")] + [self._mac_label(h, n) for h, _p, n in self.found]
        self.mac_menu.configure(values=values)
        saved = self.settings["mac"]
        saved_label = next((self._mac_label(h, n) for h, _p, n in self.found if h == saved), None)
        self.mac_menu.set(saved_label or values[0])

    def _scan_done(self, found):
        self._scanning = False
        self.found = found
        try:
            self.scan_btn.configure(state="normal" if not self.bridge else "disabled")
            self._fill_mac_menu()
        except Exception:  # noqa: BLE001  (окно могло пересобраться)
            return
        if not self.bridge:
            manual = self.ip_entry.get().strip()
            if manual:
                self.status.configure(text=tr("scan_manual_ready", ip=manual))
            elif found:
                names = ", ".join(self._mac_label(h, n) for h, _p, n in found)
                self.status.configure(text=tr("scan_found", names=names))
            else:
                self.status.configure(text=tr("scan_not_found"))

    # --- подключение ---

    def _selected_host(self):
        label = self.mac_menu.get()
        return next((h for h, _p, n in self.found if self._mac_label(h, n) == label), AUTO)

    def _target(self):
        ip = self.ip_entry.get().strip()
        if ip:
            return ip, DEFAULT_PORT
        host = self._selected_host()
        if host != AUTO:
            port = next(p for h, p, _n in self.found if h == host)
            return host, port
        return None, DEFAULT_PORT  # автопоиск внутри приёмника

    def toggle_connection(self):
        if self.bridge:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        host, port = self._target()
        width, height = RESOLUTIONS[self.res_menu.get()]
        fps = int(self._fps_value())
        self.connect_btn.configure(state="disabled", text=tr("starting"))
        self.update_idletasks()
        try:
            self.bridge = Bridge(host, port, width, height, fps, int(self.quality.get()),
                                 bool(self.mirror.get()), smoothing=self._smoothing_key())
        except Exception as e:  # noqa: BLE001
            self.bridge = None
            self.connect_btn.configure(state="normal", text=tr("connect"))
            if messagebox.askyesno(tr("vcam_error_title"), tr("vcam_error_text", error=e)):
                webbrowser.open("https://obsproject.com/download")
            return
        self._set_connected_ui(True)
        self.save()

    def disconnect(self):
        bridge, self.bridge = self.bridge, None
        if bridge:
            threading.Thread(target=bridge.stop, daemon=True).start()
        self._set_connected_ui(False)
        self.preview.configure(image=None, text=tr("preview_idle"))
        self._preview_img = None
        self.status.configure(text=tr("status_disconnected"))
        self.stats.configure(text="")

    def _set_connected_ui(self, connected):
        state = "disabled" if connected else "normal"
        for w in (self.mac_menu, self.scan_btn, self.ip_entry, self.res_menu, self.fps_menu, self.quality):
            w.configure(state=state)
        if connected:
            self.connect_btn.configure(state="normal", text=tr("disconnect"),
                                       fg_color=("#c0392b", "#a93226"), hover_color=("#a93226", "#922b21"))
        else:
            theme = ctk.ThemeManager.theme["CTkButton"]
            self.connect_btn.configure(state="normal", text=tr("connect"), fg_color=theme["fg_color"],
                                       hover_color=theme["hover_color"])

    # --- обновление экрана ---

    def tick(self):
        b = self.bridge
        if b:
            frame = b.output
            if frame is not None:
                h, w = frame.shape[:2]
                scale = min(PREVIEW_W / w, PREVIEW_H / h)
                size = (int(w * scale), int(h * scale))
                small = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
                img = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                self._preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self.preview.configure(image=self._preview_img, text="")
            self.status.configure(text=b.status)
            if b.connected:
                rx = b.rx
                lines = [tr("stats_line", fps=f"{rx.stats_fps:.0f}", mbps=f"{rx.stats_mbps:.1f}",
                            jitter=f"{b.jitter_ms:.0f}", buffer=f"{b.buffer_ms:.0f}",
                            pacing=f"{b.pacing_ms:.1f}")]
                max_fps = rx.info.get("max_fps")
                if rx.info.get("backend_error"):
                    lines.append(tr("camera_fallback", reason=rx.info["backend_error"].splitlines()[0][:160]))
                elif max_fps and b.fps > max_fps:
                    lines.append(tr("camera_fps_limit", max_fps=max_fps))
                lines.append(tr("vcam_name", name=b.vcam_name))
                self.stats.configure(text="\n".join(lines))
            else:
                self.stats.configure(text=tr("vcam_placeholder", name=b.vcam_name))
        self.after(66, self.tick)

    def _collect_settings(self):
        self.settings.update({
            "mac": self._selected_host(),
            "manual_ip": self.ip_entry.get().strip(),
            "resolution": self.res_menu.get(),
            "fps": self._fps_value(),
            "quality": int(self.quality.get()),
            "mirror": bool(self.mirror.get()),
            "autoconnect": bool(self.autoconnect.get()),
            "smoothing": self._smoothing_key(),
        })

    def save(self):
        self._collect_settings()
        save_settings(self.settings)

    def on_close(self):
        self.save()
        if self.bridge:
            self.bridge.stop()
        self.destroy()


def main():
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
