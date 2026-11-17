#!/usr/bin/env python3
"""Generate the placeholder Avtaar: idle.png (static) and talking.gif (animated mouth + blink).

    backend/.venv/bin/python scripts/make_placeholder_avatar.py

Replace frontend/static/avatar/{idle.png,talking.gif} with your own art any time;
the app only cares about those two filenames.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "frontend" / "static" / "avatar"
SIZE = 400
SS = 3  # supersampling factor for smooth edges
W = SIZE * SS


def s(*vals: float) -> list[float]:
    return [v * SS * SIZE / 200 for v in vals]


def lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def base() -> Image.Image:
    img = Image.new("RGB", (W, W))
    d = ImageDraw.Draw(img)
    top, bottom = (199, 210, 254), (129, 140, 248)
    for y in range(W):
        d.line([(0, y), (W, y)], fill=lerp(top, bottom, y / W))
    return img


def draw_frame(mouth: float, blink: bool = False) -> Image.Image:
    """mouth: 0 = closed smile … 1 = wide open."""
    img = base()
    d = ImageDraw.Draw(img)
    skin, skin_shade = (250, 214, 180), (240, 196, 158)
    hair = (31, 41, 55)
    ink = (31, 41, 55)

    # shoulders + neck
    d.ellipse(s(28, 150, 172, 260), fill=(49, 46, 129))
    d.rounded_rectangle(s(86, 128, 114, 160), radius=12 * SS, fill=skin_shade)
    # ears
    d.ellipse(s(52, 88, 66, 110), fill=skin_shade)
    d.ellipse(s(134, 88, 148, 110), fill=skin_shade)
    # head
    d.ellipse(s(56, 44, 144, 144), fill=skin)
    # hair (cap + side fringe)
    d.chord(s(52, 30, 148, 118), start=180, end=360, fill=hair)
    d.polygon(s(56, 74, 70, 60, 100, 56, 132, 62, 146, 76, 140, 66, 118, 72, 92, 70, 70, 82), fill=hair)

    # brows
    d.arc(s(72, 80, 94, 92), start=200, end=340, fill=ink, width=3 * SS)
    d.arc(s(106, 80, 128, 92), start=200, end=340, fill=ink, width=3 * SS)

    # eyes
    if blink:
        d.arc(s(77, 94, 89, 102), start=10, end=170, fill=ink, width=3 * SS)
        d.arc(s(111, 94, 123, 102), start=10, end=170, fill=ink, width=3 * SS)
    else:
        d.ellipse(s(78, 92, 88, 104), fill=ink)
        d.ellipse(s(112, 92, 122, 104), fill=ink)
        d.ellipse(s(83, 94, 86, 97), fill="white")
        d.ellipse(s(117, 94, 120, 97), fill="white")

    # cheeks
    blush = (246, 170, 170)
    d.ellipse(s(66, 108, 80, 118), fill=lerp(skin, blush, 0.55))
    d.ellipse(s(120, 108, 134, 118), fill=lerp(skin, blush, 0.55))

    # mouth
    lip = (159, 18, 57)
    if mouth <= 0.01:
        d.arc(s(88, 110, 112, 126), start=20, end=160, fill=lip, width=4 * SS)
    else:
        h = 3 + 14 * mouth
        w = 20 - 4 * mouth
        cx, cy = 100, 121
        d.ellipse(s(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), fill=(127, 29, 29), outline=lip, width=2 * SS)
        if mouth > 0.35:  # teeth + tongue
            d.chord(s(cx - w / 2 + 2, cy - h / 2 + 1, cx + w / 2 - 2, cy - h / 2 + 7), start=180, end=360, fill="white")
            d.chord(s(cx - w / 3, cy, cx + w / 3, cy + h / 2 - 1), start=0, end=180, fill=(244, 114, 182))

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_frame(0).save(OUT / "idle.png", optimize=True)

    pattern = [0.0, 0.4, 0.8, 1.0, 0.6, 0.2, 0.5, 0.9, 0.7, 0.3, 0.0, 0.5, 1.0, 0.6, 0.25, 0.0]
    frames = [draw_frame(m, blink=(i in (9, 10))) for i, m in enumerate(pattern)]
    palette_src = frames[3].quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    gif_frames = [f.quantize(palette=palette_src, dither=Image.Dither.NONE) for f in frames]
    gif_frames[0].save(
        OUT / "talking.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=90,
        loop=0,
        optimize=False,
        disposal=1,
    )
    print("wrote", OUT / "idle.png", "and", OUT / "talking.gif")


if __name__ == "__main__":
    main()
