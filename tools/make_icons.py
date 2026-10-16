"""
Генерирует иконки в assets/:
  icon.png (1024), icon.ico (16–256) — приложение;
  menubar.png — шаблон для строки меню macOS.

Всё рисуется в увеличенном масштабе и уменьшается — так края получаются гладкими.
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
SS = 4  # суперсэмплинг


def squircle_mask(size, radius_ratio=0.225):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=size * radius_ratio, fill=255)
    return m


def gradient(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g.resize((size, size))


def draw_glyph(d, cx, cy, r, color, hole):
    """Объектив веб-камеры + две дуги сигнала справа сверху."""
    # корпус объектива
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    # линза
    r2 = r * 0.56
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=hole)
    r3 = r * 0.22
    d.ellipse((cx - r3 + r * 0.16, cy - r3 - r * 0.16, cx + r3 + r * 0.16, cy - r3 - r * 0.16 + 2 * r3),
              fill=color)  # блик
    # дуги сигнала
    w = r * 0.17
    for k, rr in enumerate((r * 1.42, r * 1.86)):
        box = (cx - rr, cy - rr, cx + rr, cy + rr)
        d.arc(box, start=-75, end=-15, fill=color, width=int(w))


def app_icon(size=1024):
    big = size * SS
    base = gradient(big, (78, 140, 255), (37, 84, 220))
    icon = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    inset = int(big * 0.055)
    inner = big - 2 * inset
    icon.paste(base.resize((inner, inner)), (inset, inset), squircle_mask(inner))
    d = ImageDraw.Draw(icon)
    draw_glyph(d, big * 0.44, big * 0.56, big * 0.215, (255, 255, 255, 255), (37, 84, 220, 255))
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def menubar_icon(size=44):
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_glyph(d, big * 0.40, big * 0.60, big * 0.30, (0, 0, 0, 255), (0, 0, 0, 0))
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main():
    os.makedirs(ROOT, exist_ok=True)
    icon = app_icon()
    icon.save(os.path.join(ROOT, "icon.png"))
    icon.save(os.path.join(ROOT, "icon.ico"),
              sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    menubar_icon().save(os.path.join(ROOT, "menubar.png"))
    print("Иконки сохранены в", os.path.abspath(ROOT))


if __name__ == "__main__":
    main()
