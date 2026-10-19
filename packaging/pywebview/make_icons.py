"""Draw the FoxLogin app icon and export every copy the apps use.

    python3 packaging/pywebview/make_icons.py

A white fox head on the orange-to-pink gradient of the Camoufox icon. Writes:
    packaging/pywebview/assets/icon.{png,ico,icns}   pywebview app (.icns on macOS only)
    packaging/tauri/app-icon.png                     Tauri source icon (`npx tauri icon` makes the rest)
    app/static/logo.svg, packaging/tauri/ui/logo.svg web UI badge and favicon, Tauri loading page
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "assets"
TOP, BOTTOM = (248, 176, 101), (226, 43, 81)   # Camoufox icon gradient, top to bottom
NOSE = (74, 28, 44)

# Fox head on a 0..1 canvas. HEAD is the white silhouette; EARS and EYES are
# cut back out of it so the gradient shows through.
HEAD = [(0.25, 0.17), (0.41, 0.33), (0.50, 0.31), (0.59, 0.33), (0.75, 0.17),
        (0.77, 0.45), (0.85, 0.57), (0.64, 0.66), (0.50, 0.82),
        (0.36, 0.66), (0.15, 0.57), (0.23, 0.45)]
EARS = [[(0.29, 0.26), (0.37, 0.35), (0.28, 0.42)],
        [(0.71, 0.26), (0.63, 0.35), (0.72, 0.42)]]
EYES = [[(0.33, 0.49), (0.43, 0.50), (0.41, 0.55)],
        [(0.67, 0.49), (0.57, 0.50), (0.59, 0.55)]]
NOSE_C, NOSE_R = (0.50, 0.775), 0.035


def draw(n=1024, ss=4):
    """The icon at n x n, drawn ss times larger and scaled down for smooth edges."""
    s = n * ss
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / s
        gd.line([(0, y), (s, y)], fill=tuple(round(TOP[i] * (1 - t) + BOTTOM[i] * t) for i in range(3)) + (255,))
    # macOS icon grid: ~10% margin, rounded square
    m, r = s * 0.1, s * 0.2
    tile = Image.new("L", (s, s), 0)
    ImageDraw.Draw(tile).rounded_rectangle([m, m, s - m, s - m], r, fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), tile)

    # The fox fills the tile's inner 80%
    pt = lambda x, y: (m + x * (s - 2 * m), m + y * (s - 2 * m))
    head = Image.new("L", (s, s), 0)
    hd = ImageDraw.Draw(head)
    hd.polygon([pt(*p) for p in HEAD], fill=255)
    for poly in EARS + EYES:
        hd.polygon([pt(*p) for p in poly], fill=0)
    img.paste((255, 255, 255, 255), (0, 0), head)
    cx, cy = pt(*NOSE_C)
    rr = NOSE_R * (s - 2 * m)
    ImageDraw.Draw(img).ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=NOSE + (255,))
    return img.resize((n, n), Image.LANCZOS)


def svg() -> str:
    """The same icon as SVG, full-bleed (no macOS margin), for the web UI."""
    m, k = 10, 80   # 100-unit viewBox: the fox spans the inner 80%, like the PNG
    pts = lambda poly: " ".join(f"{m + x * k:.1f},{m + y * k:.1f}" for x, y in poly)
    cuts = "".join(f'<polygon points="{pts(p)}" fill="url(#g)"/>' for p in EARS + EYES)
    hexc = lambda c: "#%02x%02x%02x" % c
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f'<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="100">'
            f'<stop offset="0" stop-color="{hexc(TOP)}"/><stop offset="1" stop-color="{hexc(BOTTOM)}"/>'
            f'</linearGradient></defs><rect width="100" height="100" rx="22" fill="url(#g)"/>'
            f'<polygon points="{pts(HEAD)}" fill="#fff"/>{cuts}'
            f'<circle cx="{m + NOSE_C[0] * k:.1f}" cy="{m + NOSE_C[1] * k:.1f}" r="{NOSE_R * k:.1f}" fill="{hexc(NOSE)}"/>'
            f'</svg>\n')


def main():
    OUT.mkdir(exist_ok=True)
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(ROOT / "packaging" / "tauri" / "app-icon.png")
    for d in (ROOT / "app" / "static", ROOT / "packaging" / "tauri" / "ui"):
        (d / "logo.svg").write_text(svg())
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
