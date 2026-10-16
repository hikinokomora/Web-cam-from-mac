"""Генерирует иконки в assets/: icon.png, icon.ico, menubar.png (шаблон для строки меню macOS)."""

import os

from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def camera_glyph(draw, box, color, lens_color):
    """Силуэт видеокамеры: корпус + объектив-треугольник."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    body = (x0, y0 + h * 0.18, x0 + w * 0.68, y1 - h * 0.18)
    draw.rounded_rectangle(body, radius=h * 0.14, fill=color)
    draw.polygon([(x0 + w * 0.72, y0 + h * 0.5), (x1, y0 + h * 0.24), (x1, y1 - h * 0.24)], fill=color)
    cx, cy, r = x0 + w * 0.34, y0 + h * 0.5, h * 0.17
    if lens_color:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=lens_color)


def app_icon(size=1024):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # фон: скруглённый квадрат с вертикальным градиентом
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    top, bottom = (64, 156, 255), (28, 92, 214)
    for y in range(size):
        t = y / (size - 1)
        gd.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((size * 0.06, size * 0.06, size * 0.94, size * 0.94),
                                           radius=size * 0.2, fill=255)
    img.paste(grad, (0, 0), mask)
    camera_glyph(d, (size * 0.2, size * 0.28, size * 0.8, size * 0.72), (255, 255, 255, 255), (40, 110, 230, 255))
    return img


def menubar_icon(size=44):
    # macOS-шаблон: чёрный с альфой, система сама перекрасит под тему
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    camera_glyph(d, (size * 0.06, size * 0.2, size * 0.94, size * 0.8), (0, 0, 0, 255), (0, 0, 0, 0))
    # прорезь объектива
    cx, cy, r = size * 0.06 + size * 0.88 * 0.34, size * 0.5, size * 0.6 * 0.17
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 0))
    return img


def main():
    os.makedirs(ROOT, exist_ok=True)
    icon = app_icon()
    icon.save(os.path.join(ROOT, "icon.png"))
    icon.save(os.path.join(ROOT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    menubar_icon().save(os.path.join(ROOT, "menubar.png"))
    print("Иконки сохранены в", os.path.abspath(ROOT))


if __name__ == "__main__":
    main()
