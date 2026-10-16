"""
MacBookCam — приложение для Windows.

Окно: выбор Mac в сети, качество, предпросмотр. Видео уходит в OBS Virtual Camera,
которую затем выбирают в Zoom, Teams, Discord и т.д.
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
from macbookcam.protocol import DEFAULT_PORT, discover

RESOLUTIONS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
FPS_OPTIONS = ["15", "24", "30"]
AUTO = "Автопоиск"
PREVIEW_W, PREVIEW_H = 560, 315

SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "MacBookCam", "settings.json")
DEFAULTS = {"mac": AUTO, "manual_ip": "", "resolution": "720p", "fps": "30",
            "quality": 80, "mirror": False, "autoconnect": False}


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


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
        self.title(f"MacBookCam {__version__}")
        self.geometry("900x470")
        self.minsize(900, 470)
        try:
            self.iconbitmap(resource_path("assets/icon.ico"))
        except Exception:  # noqa: BLE001
            pass

        self.settings = load_settings()
        self.bridge = None
        self.macs = {}  # подпись в списке → (host, port)
        self._scanning = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_preview()
        self._build_controls()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.scan)
        if self.settings["autoconnect"]:
            self.after(600, self.toggle_connection)
        self.after(66, self.tick)

    # --- разметка ---

    def _build_preview(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        left.grid_rowconfigure(3, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.preview = ctk.CTkLabel(left, text="Не подключено", width=PREVIEW_W, height=PREVIEW_H,
                                    fg_color=("gray75", "gray8"), corner_radius=8,
                                    text_color=("gray35", "gray55"))
        self.preview.grid(row=0, column=0, sticky="n")

        self.status = ctk.CTkLabel(left, text="", anchor="w", justify="left", wraplength=PREVIEW_W)
        self.status.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.stats = ctk.CTkLabel(left, text="", anchor="w", text_color=("gray40", "gray60"))
        self.stats.grid(row=2, column=0, sticky="ew")

    def _build_controls(self):
        right = ctk.CTkFrame(self, width=290)
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
        self.mac_menu = ctk.CTkOptionMenu(mac_row, values=[AUTO], dynamic_resizing=False)
        self.mac_menu.grid(row=0, column=0, sticky="ew")
        self.scan_btn = ctk.CTkButton(mac_row, text="↻", width=32, command=self.scan)
        self.scan_btn.grid(row=0, column=1, padx=(6, 0))
        row += 1
        self.ip_entry = ctk.CTkEntry(right, placeholder_text="или IP вручную, напр. 192.168.1.66")
        self.ip_entry.grid(row=row, column=0, pady=(6, 0), **pad)
        if self.settings["manual_ip"]:
            self.ip_entry.insert(0, self.settings["manual_ip"])
        row += 1

        label("Качество")
        q_row = ctk.CTkFrame(right, fg_color="transparent")
        q_row.grid(row=row, column=0, **pad)
        q_row.grid_columnconfigure((0, 1), weight=1)
        self.res_menu = ctk.CTkOptionMenu(q_row, values=list(RESOLUTIONS), width=110)
        self.res_menu.set(self.settings["resolution"])
        self.res_menu.grid(row=0, column=0, sticky="ew")
        self.fps_menu = ctk.CTkOptionMenu(q_row, values=[f + " к/с" for f in FPS_OPTIONS], width=110)
        self.fps_menu.set(self.settings["fps"] + " к/с")
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

        label("Параметры")
        self.mirror = ctk.CTkSwitch(right, text="Отразить по горизонтали", command=self._apply_mirror)
        if self.settings["mirror"]:
            self.mirror.select()
        self.mirror.grid(row=row, column=0, pady=2, **pad)
        row += 1
        self.autoconnect = ctk.CTkSwitch(right, text="Подключаться при запуске")
        if self.settings["autoconnect"]:
            self.autoconnect.select()
        self.autoconnect.grid(row=row, column=0, pady=2, **pad)
        row += 1

        right.grid_rowconfigure(row, weight=1)
        row += 1
        self.connect_btn = ctk.CTkButton(right, text="Подключить", height=40,
                                         font=ctk.CTkFont(size=15, weight="bold"),
                                         command=self.toggle_connection)
        self.connect_btn.grid(row=row, column=0, pady=(12, 6), **pad)
        row += 1
        self.hint = ctk.CTkLabel(right, text="В Zoom выберите камеру\n«OBS Virtual Camera»",
                                 text_color=("gray40", "gray60"), justify="center")
        self.hint.grid(row=row, column=0, pady=(0, 12), **pad)

    def _update_quality_label(self):
        self.quality_label.configure(text=f"Качество JPEG: {int(self.quality.get())}%")

    def _apply_mirror(self):
        if self.bridge:
            self.bridge.mirror = bool(self.mirror.get())

    # --- поиск Mac ---

    def scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled")
        self.status.configure(text="Ищу Mac в сети...")

        def work():
            found = discover(timeout=2.0, first_only=False)
            self.after(0, lambda: self._scan_done(found))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, found):
        self._scanning = False
        self.scan_btn.configure(state="normal")
        self.macs = {f"{name} ({host})": (host, port) for host, port, name in found}
        values = [AUTO] + list(self.macs)
        self.mac_menu.configure(values=values)
        saved = self.settings["mac"]
        self.mac_menu.set(saved if saved in values else (values[1] if len(values) > 1 else AUTO))
        if not self.bridge:
            if found:
                self.status.configure(text=f"Найдено Mac: {len(found)}. Нажмите «Подключить».")
            else:
                self.status.configure(text="Mac не найден. Запустите MacBookCam на Mac "
                                           "или впишите его IP вручную.")

    # --- подключение ---

    def _target(self):
        ip = self.ip_entry.get().strip()
        if ip:
            return ip, DEFAULT_PORT
        choice = self.mac_menu.get()
        if choice in self.macs:
            return self.macs[choice]
        return None, DEFAULT_PORT  # автопоиск внутри приёмника

    def toggle_connection(self):
        if self.bridge:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        host, port = self._target()
        width, height = RESOLUTIONS[self.res_menu.get()]
        fps = int(self.fps_menu.get().split()[0])
        self.connect_btn.configure(state="disabled", text="Запуск...")
        self.update_idletasks()
        try:
            self.bridge = Bridge(host, port, width, height, fps, int(self.quality.get()),
                                 bool(self.mirror.get()))
        except Exception as e:  # noqa: BLE001
            self.bridge = None
            self.connect_btn.configure(state="normal", text="Подключить")
            if messagebox.askyesno(
                    "Нет виртуальной камеры",
                    f"Не удалось запустить виртуальную камеру:\n{e}\n\n"
                    "Нужна установленная OBS Studio (она даёт драйвер «OBS Virtual Camera»). "
                    "Если OBS запущена и в ней включена виртуальная камера — остановите её.\n\n"
                    "Открыть страницу загрузки OBS?"):
                webbrowser.open("https://obsproject.com/download")
            return
        self._set_controls_state("disabled")
        self.connect_btn.configure(state="normal", text="Отключить",
                                   fg_color=("#c0392b", "#a93226"), hover_color=("#a93226", "#922b21"))
        self.save()

    def disconnect(self):
        bridge, self.bridge = self.bridge, None
        if bridge:
            threading.Thread(target=bridge.stop, daemon=True).start()
        self._set_controls_state("normal")
        self.connect_btn.configure(text="Подключить", fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                                   hover_color=ctk.ThemeManager.theme["CTkButton"]["hover_color"])
        self.preview.configure(image=None, text="Не подключено")
        self._preview_img = None
        self.status.configure(text="Отключено")
        self.stats.configure(text="")

    def _set_controls_state(self, state):
        for w in (self.mac_menu, self.scan_btn, self.ip_entry, self.res_menu, self.fps_menu, self.quality):
            w.configure(state=state)

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
                age = b.frame_age_ms()
                lag = f", задержка кадра ~{age:.0f} мс" if age is not None and age < 5000 else ""
                self.stats.configure(text=f"{b.rx.stats_fps:.0f} к/с, {b.rx.stats_mbps:.1f} Мбит/с{lag}"
                                          f"  •  {b.vcam_name}")
            else:
                self.stats.configure(text=f"Виртуальная камера: {b.vcam_name} (показывает заглушку)")
        self.after(66, self.tick)

    def save(self):
        save_settings({
            "mac": self.mac_menu.get(),
            "manual_ip": self.ip_entry.get().strip(),
            "resolution": self.res_menu.get(),
            "fps": self.fps_menu.get().split()[0],
            "quality": int(self.quality.get()),
            "mirror": bool(self.mirror.get()),
            "autoconnect": bool(self.autoconnect.get()),
        })

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
