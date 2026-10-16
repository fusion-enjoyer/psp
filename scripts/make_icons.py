#!/usr/bin/env python3
"""Draws the XMB icon (ICON0.PNG, 144x80) and background (PIC1.PNG, 480x272)
for the Deck EBOOT. Run once; the PNGs are committed next to the app.

  python3 scripts/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "psp" / "apps" / "deck"
BG = (18, 20, 25)
COLORS = [(61, 139, 253), (163, 113, 247), (240, 78, 78), (61, 220, 132)]


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def tiles(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, gap: int) -> None:
    """The Deck's face-button diamond: four colored tiles around a center."""
    for (dx, dy), color in zip(((0, -1), (-1, 0), (1, 0), (0, 1)), COLORS):
        x, y = cx + dx * (size + gap) - size // 2, cy + dy * (size + gap) - size // 2
        fill = tuple(int(c * 0.35 + b * 0.65) for c, b in zip(color, BG))
        draw.rounded_rectangle((x, y, x + size, y + size), radius=max(2, size // 6), fill=fill,
                               outline=color, width=max(2, size // 10))


def icon0() -> None:
    img = Image.new("RGBA", (144, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 143, 79), radius=10, fill=BG + (255,))
    tiles(d, 36, 40, 18, 3)
    d.text((70, 18), "pspkit", font=font(13), fill=(138, 144, 156))
    d.text((70, 34), "Deck", font=font(24), fill=(238, 240, 244))
    img.save(OUT / "ICON0.PNG")


def pic1() -> None:
    img = Image.new("RGB", (480, 272), BG)
    d = ImageDraw.Draw(img)
    for y in range(272):  # subtle vertical fade
        shade = int(8 * y / 272)
        d.line((0, y, 480, y), fill=(BG[0] + shade, BG[1] + shade, BG[2] + shade + 4))
    tiles(d, 360, 136, 52, 8)
    d.text((40, 96), "pspkit", font=font(22), fill=(138, 144, 156))
    d.text((40, 122), "Deck", font=font(48), fill=(238, 240, 244))
    d.text((40, 182), "PSP'yi Stream Deck'e çevir", font=font(14), fill=(138, 144, 156))
    img.save(OUT / "PIC1.PNG")


if __name__ == "__main__":
    icon0()
    pic1()
    print(f"yazildi: {OUT / 'ICON0.PNG'}, {OUT / 'PIC1.PNG'}")
