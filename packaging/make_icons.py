"""Draw the FoxLogin app icon and export .icns (macOS), .ico (Windows), .png (Linux).

    python3 packaging/make_icons.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "assets"
GREEN, DARK = (74, 158, 120), (52, 122, 92)


def font(size):
    for f in ("/System/Library/Fonts/SFNSRounded.ttf", "/System/Library/Fonts/SFNS.ttf",
              "C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def draw(n=1024):
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    # macOS icon grid: ~10% margin, squircle-ish rounded square, vertical gradient
    m, r = int(n * 0.1), int(n * 0.2)
    grad = Image.new("RGBA", (n, n))
    gd = ImageDraw.Draw(grad)
    for y in range(n):
        t = y / n
        gd.line([(0, y), (n, y)], fill=tuple(int(GREEN[i] * (1 - t) + DARK[i] * t) for i in range(3)) + (255,))
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, n - m, n - m], r, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # Fox ears + "F"
    ear = int(n * 0.11)
    for cx in (n * 0.36, n * 0.64):
        d.polygon([(cx - ear, n * 0.33), (cx + ear, n * 0.33), (cx, n * 0.19)], fill=(255, 255, 255, 235))
    f = font(int(n * 0.5))
    d.text((n / 2, n * 0.6), "F", font=f, fill="white", anchor="mm")
    return img


def main():
    OUT.mkdir(exist_ok=True)
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        iconset = OUT / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            img.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            img.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
        shutil.rmtree(iconset)


if __name__ == "__main__":
    main()
