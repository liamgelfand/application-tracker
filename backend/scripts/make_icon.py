"""Generate the application icon used by the exe, the tray, and the web app.

Run from the backend/ directory:
    python scripts/make_icon.py

Writes assets/icon.ico, assets/icon.png and ../frontend/public/favicon.svg so
every surface shows the same mark.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
ASSETS = HERE / "assets"
FAVICON = HERE.parent / "frontend" / "public" / "favicon.svg"

# Matches --bg-card / --accent in frontend/src/index.css.
PLATE = (26, 25, 23, 255)
ACCENT = (200, 115, 74, 255)
BONE = (233, 229, 222, 255)

# Three ascending bars: the pipeline, not another briefcase.
BARS = ((0.22, 0.58, BONE), (0.45, 0.40, BONE), (0.68, 0.22, ACCENT))


def _draw(size: int) -> Image.Image:
    # Supersample so small icon sizes keep clean edges.
    scale = 8
    px = size * scale
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, px - 1, px - 1], radius=int(px * 0.22), fill=PLATE)

    width = px * 0.13
    bottom = px * 0.78
    for left_frac, top_frac, color in BARS:
        left = px * left_frac
        draw.rounded_rectangle(
            [left, px * top_frac, left + width, bottom],
            radius=int(width * 0.35),
            fill=color,
        )
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [_draw(s) for s in sizes]
    frames[-1].save(ASSETS / "icon.ico", format="ICO", sizes=[(s, s) for s in sizes])
    frames[-1].save(ASSETS / "icon.png", format="PNG")

    plate = "#%02x%02x%02x" % PLATE[:3]
    accent = "#%02x%02x%02x" % ACCENT[:3]
    bone = "#%02x%02x%02x" % BONE[:3]
    bars = "\n".join(
        f'  <rect x="{left * 64:.1f}" y="{top * 64:.1f}" '
        f'width="{0.13 * 64:.1f}" height="{(0.78 - top) * 64:.1f}" rx="3" '
        f'fill="{bone if color is BONE else accent}"/>'
        for left, top, color in BARS
    )
    FAVICON.parent.mkdir(parents=True, exist_ok=True)
    FAVICON.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">\n'
        f'  <rect width="64" height="64" rx="14" fill="{plate}"/>\n'
        f"{bars}\n"
        "</svg>\n",
        encoding="utf-8",
    )
    print(f"Wrote {ASSETS / 'icon.ico'}, {ASSETS / 'icon.png'} and {FAVICON}")


if __name__ == "__main__":
    main()
