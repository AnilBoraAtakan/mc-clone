from __future__ import annotations

from pathlib import Path
import random

from panda3d.core import PNMImage


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def rgb(hex_color: int) -> tuple[float, float, float]:
    r = (hex_color >> 16) & 0xFF
    g = (hex_color >> 8) & 0xFF
    b = hex_color & 0xFF
    return (r / 255.0, g / 255.0, b / 255.0)


def fill(img: PNMImage, color: tuple[float, float, float]):
    img.fill(*color)
    img.alphaFill(1.0)


def set_px(img: PNMImage, x: int, y: int, color: tuple[float, float, float]):
    img.setXelA(x, y, color[0], color[1], color[2], 1.0)


def rect(img: PNMImage, x0: int, y0: int, x1: int, y1: int, color: tuple[float, float, float]):
    for y in range(y0, y1):
        for x in range(x0, x1):
            set_px(img, x, y, color)


def outline(img: PNMImage, x0: int, y0: int, x1: int, y1: int, color: tuple[float, float, float]):
    for x in range(x0, x1):
        set_px(img, x, y0, color)
        set_px(img, x, y1 - 1, color)
    for y in range(y0, y1):
        set_px(img, x0, y, color)
        set_px(img, x1 - 1, y, color)


def wood_planks(img: PNMImage, rng: random.Random, base: tuple[float, float, float]):
    w = img.getXSize()
    h = img.getYSize()

    # Horizontal planks with small per-pixel variation.
    plank_h = max(4, h // 6)
    for y in range(h):
        plank_index = y // plank_h
        plank_tint = (plank_index % 3) * 0.03
        for x in range(w):
            noise = (rng.random() - 0.5) * 0.06
            r = clamp(base[0] + plank_tint + noise)
            g = clamp(base[1] + plank_tint * 0.6 + noise * 0.7)
            b = clamp(base[2] + noise * 0.5)
            set_px(img, x, y, (r, g, b))

    # Plank seams.
    seam = (base[0] * 0.75, base[1] * 0.70, base[2] * 0.65)
    for y in range(0, h, plank_h):
        for x in range(w):
            set_px(img, x, y, seam)


def draw_chest_face(img: PNMImage, with_latch: bool, rng: random.Random):
    base = rgb(0xB0763A)
    dark = rgb(0x6C4322)
    mid = rgb(0x8A5A2F)
    metal = rgb(0xB8B8B8)
    metal_dark = rgb(0x6F6F6F)
    gold = rgb(0xD2B041)
    gold_dark = rgb(0x9A7A22)

    wood_planks(img, rng, base)

    w = img.getXSize()
    h = img.getYSize()

    # Outer border.
    outline(img, 0, 0, w, h, dark)
    outline(img, 1, 1, w - 1, h - 1, mid)

    # Lid seam line (approx. 10/16 of height for the base).
    seam_y = int(round(h * (10.0 / 14.0)))  # map base/lid split into 14/16 tall model
    seam_y = max(2, min(h - 3, seam_y))
    for x in range(2, w - 2):
        set_px(img, x, seam_y, dark)

    if with_latch:
        # Simple latch: metal plate + gold lock.
        plate_w = max(6, w // 5)
        plate_h = max(10, h // 3)
        px0 = (w - plate_w) // 2
        py0 = seam_y - (plate_h // 2)
        rect(img, px0, py0, px0 + plate_w, py0 + plate_h, metal)
        outline(img, px0, py0, px0 + plate_w, py0 + plate_h, metal_dark)

        lock_w = max(4, plate_w - 2)
        lock_h = max(5, plate_h // 2)
        lx0 = (w - lock_w) // 2
        ly0 = py0 + (plate_h // 2) - (lock_h // 2)
        rect(img, lx0, ly0, lx0 + lock_w, ly0 + lock_h, gold)
        outline(img, lx0, ly0, lx0 + lock_w, ly0 + lock_h, gold_dark)


def draw_chest_top(img: PNMImage, rng: random.Random):
    base = rgb(0xB0763A)
    dark = rgb(0x6C4322)
    mid = rgb(0x8A5A2F)
    wood_planks(img, rng, base)
    w = img.getXSize()
    h = img.getYSize()
    outline(img, 0, 0, w, h, dark)
    outline(img, 1, 1, w - 1, h - 1, mid)

    # Add subtle center shading.
    for y in range(2, h - 2):
        for x in range(2, w - 2):
            dx = abs((x + 0.5) - (w / 2.0)) / (w / 2.0)
            dy = abs((y + 0.5) - (h / 2.0)) / (h / 2.0)
            shade = (dx + dy) * 0.06
            c = img.getXel(x, y)
            set_px(img, x, y, (clamp(c[0] - shade), clamp(c[1] - shade * 0.9), clamp(c[2] - shade * 0.8)))


def draw_chest_bottom(img: PNMImage, rng: random.Random):
    base = rgb(0x8A5A2F)
    dark = rgb(0x4A2E17)
    wood_planks(img, rng, base)
    w = img.getXSize()
    h = img.getYSize()
    outline(img, 0, 0, w, h, dark)


def main():
    out_dir = Path(__file__).resolve().parents[1] / "assets" / "textures"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(1337)
    size = 64

    faces = {
        "chest_front.png": ("front", True),
        "chest_back.png": ("back", False),
        "chest_side.png": ("side", False),
    }

    for file_name, (_, latch) in faces.items():
        img = PNMImage(size, size, 4)
        fill(img, (0.0, 0.0, 0.0))
        draw_chest_face(img, with_latch=latch, rng=rng)
        img.write(str(out_dir / file_name))

    top_img = PNMImage(size, size, 4)
    fill(top_img, (0.0, 0.0, 0.0))
    draw_chest_top(top_img, rng=rng)
    top_img.write(str(out_dir / "chest_top.png"))

    bottom_img = PNMImage(size, size, 4)
    fill(bottom_img, (0.0, 0.0, 0.0))
    draw_chest_bottom(bottom_img, rng=rng)
    bottom_img.write(str(out_dir / "chest_bottom.png"))


if __name__ == "__main__":
    main()

