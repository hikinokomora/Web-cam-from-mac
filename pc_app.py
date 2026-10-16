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
import time
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox as messagebox
import webbrowser

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from macbookcam import __version__
from macbookcam.client import Bridge, _font
from macbookcam.i18n import LANGUAGES, set_language, tr
from macbookcam.protocol import DEFAULT_PORT, discover

RESOLUTIONS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
FPS_OPTIONS = ["15", "24", "30", "60"]
SMOOTHING_OPTIONS = ["off", "auto", "strong"]
AUTO = "__auto__"
PREVIEW_W, PREVIEW_H = 576, 324
SIDEBAR_W = 316
REPO_URL = "https://github.com/hikinokomora/Web-cam-from-mac"

SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "MacBookCam", "settings.json")
DEFAULTS = {"mac": AUTO, "manual_ip": "", "resolution": "720p", "fps": "30",
            "quality": 80, "mirror": False, "autoconnect": False,
            "smoothing": "auto", "language": "auto"}

# Палитра: (светлая тема, тёмная тема)
BG = ("#F3F4F6", "#111215")
CARD = ("#FFFFFF", "#1A1C20")
BORDER = ("#E2E4E8", "#272A30")
CONTROL = ("#EEF0F3", "#23262B")
CONTROL_HOVER = ("#E2E5EA", "#2C3036")
CHECK_BORDER = ("#B9BEC7", "#4A4F58")
TEXT = ("#15171C", "#ECEDEF")
MUTED = ("#6B7079", "#8B909A")
ACCENT = ("#2F6BFF", "#3B76FF")
ACCENT_HOVER = ("#2558D9", "#2F64E6")
DANGER = ("#E5484D", "#E5484D")
DANGER_HOVER = ("#C93A3F", "#CC3C41")
LIVE = "#30A46C"
IDLE = "#8B909A"
WAIT = "#F5A524"
VIDEO_BG = (14, 15, 18)


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


def pick_font_family():
    families = set(tkfont.families())
    for name in ("Segoe UI Variable Text", "Segoe UI", "Helvetica"):
        if name in families:
            return name
    return "TkDefaultFont"


def idle_image(text):
    """Картинка для пустого предпросмотра (тёмная в обеих темах, как у видео)."""
    img = Image.new("RGB", (PREVIEW_W, PREVIEW_H), VIDEO_BG)
    d = ImageDraw.Draw(img)
    cx, cy = PREVIEW_W // 2, PREVIEW_H // 2 - 14
    d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=(70, 74, 82), width=3)
    d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(70, 74, 82))
    d.text((cx, cy + 50), text, font=_font(15), fill=(130, 134, 142), anchor="ms")
    return img


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.settings = load_settings()
        set_language(self.settings["language"])
        self.family = pick_font_family()
        self.geometry("1000x720")
        self.minsize(1000, 720)
        try:
            self.iconbitmap(resource_path("assets/icon.ico"))
        except Exception:  # noqa: BLE001
            pass

        self.bridge = None
        self.found = []     # [(host, port, name)]
        self._scanning = False
        self._preview_seq = -1
        self._stats_at = 0.0
        self._photo = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.scan)
        if self.settings["autoconnect"]:
            self.after(600, self.toggle_connection)
        self.after(15, self.tick)

    # --- шрифты ---

    def font(self, size=13, weight="normal"):
        return ctk.CTkFont(family=self.family, size=size, weight=weight)

    # --- разметка ---

    def _build_ui(self):
        self.title("MacBookCam")
        self._build_header()
        self._build_preview()
        self._build_sidebar()
        self._fill_mac_menu()
        if self.bridge:
            self._set_connected_ui(True)
        else:
            self._show_idle(tr("preview_idle"))
            self._set_pill("idle")

    def _rebuild_ui(self):
        self._collect_settings()
        for w in self.winfo_children():
            w.destroy()
        self._photo = None
        self._preview_seq = -1
        self._build_ui()

    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        head.grid_columnconfigure(1, weight=1)

        try:
            logo = Image.open(resource_path("assets/icon.png"))
            self._logo = ctk.CTkImage(logo, logo, size=(30, 30))
            ctk.CTkLabel(head, image=self._logo, text="").grid(row=0, column=0, padx=(0, 10))
        except OSError:
            pass
        title = ctk.CTkFrame(head, fg_color="transparent")
        title.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(title, text="MacBookCam", font=self.font(18, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(title, text=f"  v{__version__}", font=self.font(12), text_color=MUTED).pack(side="left", pady=(4, 0))

        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")
        self.pill = ctk.CTkFrame(right, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        self.pill.pack(side="left")
        self.pill_dot = ctk.CTkLabel(self.pill, text="●", font=self.font(12), text_color=IDLE, width=10)
        self.pill_dot.pack(side="left", padx=(12, 4), pady=4)
        self.pill_text = ctk.CTkLabel(self.pill, text="", font=self.font(12, "bold"), text_color=TEXT)
        self.pill_text.pack(side="left", padx=(0, 12), pady=4)

        link = ctk.CTkLabel(right, text="GitHub ↗", font=self.font(12), text_color=MUTED, cursor="hand2")
        link.pack(side="left", padx=(16, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(REPO_URL))
        link.bind("<Enter>", lambda _e: link.configure(text_color=ACCENT))
        link.bind("<Leave>", lambda _e: link.configure(text_color=MUTED))

    def _card(self, parent, **grid):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(**grid)
        return card

    def _build_preview(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 22))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.body = body

        card = self._card(body, row=0, column=0, sticky="nsew", padx=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        # tk.Label с одной PhotoImage, которая обновляется на месте: дёшево по памяти и CPU
        frame = tk.Frame(card, bg="#0E0F12", width=PREVIEW_W, height=PREVIEW_H)
        frame.grid(row=0, column=0, padx=18, pady=(18, 12))
        frame.grid_propagate(False)
        self.preview = tk.Label(frame, bg="#0E0F12", bd=0, highlightthickness=0)
        self.preview.place(relx=0.5, rely=0.5, anchor="center")

        self.status = ctk.CTkLabel(card, text="", font=self.font(13), text_color=TEXT, anchor="w",
                                   justify="left", wraplength=PREVIEW_W)
        self.status.grid(row=1, column=0, sticky="ew", padx=20)

        metrics = ctk.CTkFrame(card, fg_color="transparent")
        metrics.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 0))
        self.metric_values = {}
        for i, key in enumerate(("metric_fps", "metric_bitrate", "metric_jitter", "metric_buffer")):
            metrics.grid_columnconfigure(i, weight=1, uniform="m")
            box = ctk.CTkFrame(metrics, fg_color=CONTROL, corner_radius=10)
            box.grid(row=0, column=i, sticky="ew", padx=4)
            value = ctk.CTkLabel(box, text="—", font=self.font(16, "bold"), text_color=TEXT, anchor="w")
            value.pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(box, text=tr(key), font=self.font(11), text_color=MUTED, anchor="w").pack(
                anchor="w", padx=12, pady=(0, 8))
            self.metric_values[key] = value

        self.note = ctk.CTkLabel(card, text="", font=self.font(12), text_color=MUTED, anchor="nw",
                                 justify="left", wraplength=PREVIEW_W)
        self.note.grid(row=3, column=0, sticky="new", padx=20, pady=(10, 14))

    def _section(self, parent, text, row, top=14):
        ctk.CTkLabel(parent, text=text.upper(), font=self.font(11, "bold"), text_color=MUTED,
                     anchor="w").grid(row=row, column=0, sticky="ew", padx=20, pady=(top, 8))

    def _segmented(self, parent, values, command=None):
        return ctk.CTkSegmentedButton(
            parent, values=values, command=command, height=32, corner_radius=8,
            font=self.font(12, "bold"), fg_color=CONTROL, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, unselected_color=CONTROL,
            unselected_hover_color=CONTROL_HOVER, text_color=TEXT, text_color_disabled=MUTED)

    def _build_sidebar(self):
        side = self._card(self.body, row=0, column=1, sticky="ns")
        side.configure(width=SIDEBAR_W)
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        pad = {"padx": 20, "sticky": "ew"}
        row = 0

        # Источник
        self._section(side, tr("section_source"), row, top=18)
        row += 1
        mac_row = ctk.CTkFrame(side, fg_color="transparent")
        mac_row.grid(row=row, column=0, **pad)
        mac_row.grid_columnconfigure(0, weight=1)
        self.mac_menu = ctk.CTkOptionMenu(
            mac_row, values=[tr("mac_auto")], dynamic_resizing=False, height=34, corner_radius=8,
            font=self.font(13), dropdown_font=self.font(13), fg_color=CONTROL, button_color=CONTROL,
            button_hover_color=CONTROL_HOVER, text_color=TEXT, dropdown_fg_color=CARD,
            dropdown_hover_color=CONTROL, dropdown_text_color=TEXT)
        self.mac_menu.grid(row=0, column=0, sticky="ew")
        self.scan_btn = ctk.CTkButton(mac_row, text="↻", width=34, height=34, corner_radius=8,
                                      font=self.font(15), fg_color=CONTROL, hover_color=CONTROL_HOVER,
                                      text_color=TEXT, command=self.scan)
        self.scan_btn.grid(row=0, column=1, padx=(8, 0))
        row += 1
        self.ip_entry = ctk.CTkEntry(side, placeholder_text=tr("ip_placeholder"), height=34, corner_radius=8,
                                     font=self.font(13), fg_color=CONTROL, border_color=BORDER, border_width=1,
                                     text_color=TEXT, placeholder_text_color=MUTED)
        self.ip_entry.grid(row=row, column=0, pady=(8, 0), **pad)
        if self.settings["manual_ip"]:
            self.ip_entry.insert(0, self.settings["manual_ip"])
        row += 1

        # Видео
        self._section(side, tr("section_video"), row)
        row += 1
        self.res_menu = self._segmented(side, list(RESOLUTIONS))
        self.res_menu.set(self.settings["resolution"])
        self.res_menu.grid(row=row, column=0, **pad)
        row += 1
        fps_row = ctk.CTkFrame(side, fg_color="transparent")
        fps_row.grid(row=row, column=0, pady=(8, 0), **pad)
        fps_row.grid_columnconfigure(0, weight=1)
        self.fps_menu = self._segmented(fps_row, FPS_OPTIONS)
        self.fps_menu.set(self.settings["fps"] if self.settings["fps"] in FPS_OPTIONS else "30")
        self.fps_menu.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(fps_row, text=tr("fps_unit"), font=self.font(12), text_color=MUTED).grid(
            row=0, column=1, padx=(10, 0))
        row += 1

        q_row = ctk.CTkFrame(side, fg_color="transparent")
        q_row.grid(row=row, column=0, pady=(12, 0), **pad)
        q_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(q_row, text=tr("jpeg_quality_label"), font=self.font(12), text_color=TEXT).grid(
            row=0, column=0, sticky="w")
        self.quality_value = ctk.CTkLabel(q_row, text="", font=self.font(12, "bold"), text_color=TEXT)
        self.quality_value.grid(row=0, column=1, sticky="e")
        row += 1
        self.quality = ctk.CTkSlider(side, from_=40, to=95, number_of_steps=11, height=16,
                                     fg_color=CONTROL, progress_color=ACCENT, button_color=ACCENT,
                                     button_hover_color=ACCENT_HOVER,
                                     command=lambda _v: self._update_quality_label())
        self.quality.set(self.settings["quality"])
        self.quality.grid(row=row, column=0, pady=(6, 0), **pad)
        row += 1
        self._update_quality_label()

        # Сглаживание
        self._section(side, tr("smoothing"), row)
        row += 1
        self._smooth_labels = {k: tr("smoothing_" + k) for k in SMOOTHING_OPTIONS}
        self.smooth_menu = self._segmented(side, list(self._smooth_labels.values()), self._apply_smoothing)
        self.smooth_menu.set(self._smooth_labels.get(self.settings["smoothing"], self._smooth_labels["auto"]))
        self.smooth_menu.grid(row=row, column=0, **pad)
        row += 1
        self.smooth_hint = ctk.CTkLabel(side, text="", font=self.font(11), text_color=MUTED, anchor="w",
                                        justify="left", wraplength=SIDEBAR_W - 40)
        self.smooth_hint.grid(row=row, column=0, pady=(6, 0), **pad)
        row += 1
        self._update_smooth_hint()

        # Параметры
        cb = {"font": self.font(13), "text_color": TEXT, "fg_color": ACCENT, "hover_color": ACCENT_HOVER,
              "border_color": CHECK_BORDER, "border_width": 2, "checkbox_width": 18, "checkbox_height": 18,
              "corner_radius": 5, "checkmark_color": "#FFFFFF"}
        self.mirror = ctk.CTkCheckBox(side, text=tr("mirror"), command=self._apply_mirror, **cb)
        if self.settings["mirror"]:
            self.mirror.select()
        self.mirror.grid(row=row, column=0, pady=(16, 0), **pad)
        row += 1
        self.autoconnect = ctk.CTkCheckBox(side, text=tr("autoconnect"), **cb)
        if self.settings["autoconnect"]:
            self.autoconnect.select()
        self.autoconnect.grid(row=row, column=0, pady=(10, 0), **pad)
        row += 1

        side.grid_rowconfigure(row, weight=1)
        row += 1
        self.connect_btn = ctk.CTkButton(side, text=tr("connect"), height=44, corner_radius=10,
                                         font=self.font(14, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                         text_color="#FFFFFF", command=self.toggle_connection)
        self.connect_btn.grid(row=row, column=0, pady=(10, 6), **pad)
        row += 1
        self.hint = ctk.CTkLabel(side, text=tr("vcam_hint"), font=self.font(11), text_color=MUTED,
                                 wraplength=SIDEBAR_W - 40, justify="center")
        self.hint.grid(row=row, column=0, **pad)
        row += 1

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.grid(row=row, column=0, pady=(8, 14), **pad)
        ctk.CTkLabel(foot, text=tr("language"), font=self.font(11), text_color=MUTED).pack(side="left")
        names = [tr("language_auto")] + [LANGUAGES[c] for c in LANGUAGES]
        self.lang_menu = ctk.CTkOptionMenu(
            foot, values=names, width=110, height=26, corner_radius=6, font=self.font(11),
            dropdown_font=self.font(12), fg_color=CONTROL, button_color=CONTROL,
            button_hover_color=CONTROL_HOVER, text_color=TEXT, dropdown_fg_color=CARD,
            dropdown_hover_color=CONTROL, dropdown_text_color=TEXT, command=self._change_language)
        self.lang_menu.set(LANGUAGES.get(self.settings["language"], tr("language_auto")))
        self.lang_menu.pack(side="right")

    # --- мелкие обработчики ---

    def _update_quality_label(self):
        self.quality_value.configure(text=f"{int(self.quality.get())}%")

    def _apply_mirror(self):
        if self.bridge:
            self.bridge.mirror = bool(self.mirror.get())

    def _smoothing_key(self):
        label = self.smooth_menu.get()
        return next((k for k, v in self._smooth_labels.items() if v == label), "auto")

    def _update_smooth_hint(self):
        self.smooth_hint.configure(text=tr("smoothing_hint_" + self._smoothing_key()))

    def _apply_smoothing(self, _value=None):
        self._update_smooth_hint()
        if self.bridge:
            self.bridge.smoothing = self._smoothing_key()

    def _change_language(self, name):
        code = next((c for c, n in LANGUAGES.items() if n == name), "auto")
        self.settings["language"] = code
        set_language(code)
        self._rebuild_ui()
        self.save()

    def _set_pill(self, state):
        color = {"live": LIVE, "wait": WAIT}.get(state, IDLE)
        self.pill_dot.configure(text_color=color)
        self.pill_text.configure(text=tr("pill_" + state))

    def _show_idle(self, text):
        self._set_preview(idle_image(text))

    def _set_preview(self, img):
        if img.size != (PREVIEW_W, PREVIEW_H):
            img = img.resize((PREVIEW_W, PREVIEW_H), Image.Resampling.BILINEAR, reducing_gap=2.0)
        if self._photo is None:
            self._photo = ImageTk.PhotoImage(img)
            self.preview.configure(image=self._photo)
        else:
            self._photo.paste(img)

    # --- поиск Mac ---

    def scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.configure(state="disabled")
        if not self.bridge:
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
        fps = int(self.fps_menu.get())
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
        self._show_idle(tr("preview_idle"))
        self._preview_seq = -1
        self.status.configure(text=tr("status_disconnected"))
        self.note.configure(text="")
        for v in self.metric_values.values():
            v.configure(text="—")
        self._set_pill("idle")

    def _set_connected_ui(self, connected):
        state = "disabled" if connected else "normal"
        for w in (self.mac_menu, self.scan_btn, self.ip_entry, self.res_menu, self.fps_menu, self.quality):
            w.configure(state=state)
        if connected:
            self.connect_btn.configure(state="normal", text=tr("disconnect"), fg_color=DANGER,
                                       hover_color=DANGER_HOVER)
            self._set_pill("wait")
        else:
            self.connect_btn.configure(state="normal", text=tr("connect"), fg_color=ACCENT,
                                       hover_color=ACCENT_HOVER)

    # --- обновление экрана ---

    def tick(self):
        b = self.bridge
        if b:
            img = b.output
            if img is not None and b.output_seq != self._preview_seq:
                self._preview_seq = b.output_seq
                self._set_preview(img)
            if time.time() - self._stats_at > 0.25:
                self._stats_at = time.time()
                self._update_stats(b)
        self.after(15, self.tick)

    def _update_stats(self, b):
        self.status.configure(text=b.status)
        mv = self.metric_values
        if not b.connected:
            self._set_pill("wait")
            for v in mv.values():
                v.configure(text="—")
            self.note.configure(text=tr("vcam_placeholder", name=b.vcam_name) if b.vcam_name else "")
            return
        rx = b.rx
        self._set_pill("live")
        mv["metric_fps"].configure(text=f"{rx.stats_fps:.0f}")
        mv["metric_bitrate"].configure(text=tr("value_mbps", v=f"{rx.stats_mbps:.1f}"))
        mv["metric_jitter"].configure(text=tr("value_ms", v=f"±{b.jitter_ms:.0f}"))
        mv["metric_buffer"].configure(text=tr("value_ms", v=f"{b.buffer_ms:.0f}"))
        notes = []
        if rx.info.get("backend_error"):
            notes.append(tr("camera_fallback", reason=rx.info["backend_error"].splitlines()[0][:160]))
        elif rx.info.get("max_fps") and int(self.fps_menu.get()) > rx.info["max_fps"]:
            notes.append(tr("camera_fps_limit", max_fps=rx.info["max_fps"]))
        notes.append(tr("vcam_name", name=b.vcam_name) if b.vcam_name else tr("vcam_none"))
        self.note.configure(text="\n".join(notes))

    def _collect_settings(self):
        self.settings.update({
            "mac": self._selected_host(),
            "manual_ip": self.ip_entry.get().strip(),
            "resolution": self.res_menu.get(),
            "fps": self.fps_menu.get(),
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
    if sys.platform == "win32":
        try:
            import ctypes
            # своя иконка на панели задач, а не значок Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hikinokomora.MacBookCam")
        except Exception:  # noqa: BLE001
            pass
    ctk.set_appearance_mode("system")
    App().mainloop()


if __name__ == "__main__":
    main()
