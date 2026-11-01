"""Build original optical materials from seeded noise; no external imagery."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

DESTINATION = Path(__file__).resolve().parents[1] / "assets/themes/2049"


def build():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2049)
    size = 768
    noise = rng.normal(0, 1, (size, size))
    alpha = np.clip(1 + noise * 1.2, 0, 5).astype(np.uint8)
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, :3] = (170, 204, 197)
    rgba[:, :, 3] = alpha
    glass = Image.fromarray(rgba)
    dust = ImageDraw.Draw(glass)
    for _ in range(280):
        x, y = rng.integers(0, size, 2)
        length = int(rng.choice([1, 1, 1, 2, 3, 5]))
        dust.line((int(x), int(y), int(x + length), int(y)), fill=(185, 219, 206, int(rng.integers(8, 24))))
    for _ in range(8):
        x, y = rng.integers(0, size, 2)
        dust.line((int(x), int(y), int(x + rng.integers(-20, 60)), int(y + rng.integers(8, 85))), fill=(160, 197, 187, 10), width=1)
    glass.save(DESTINATION / "optical-glass.png", optimize=True)

    raster = Image.new("RGBA", (192, 96))
    draw = ImageDraw.Draw(raster)
    for y in range(0, 96, 4):
        draw.line((0, y, 191, y), fill=(118, 198, 180, 7))
    raster.save(DESTINATION / "phosphor-raster.png", optimize=True)

    # Restrict wear and light spill to the physical perimeter. The working
    # surface stays quiet so emitted lines, not background grain, define it.
    width, height = 1920, 1080
    y, x = np.mgrid[0:height, 0:width]
    nx, ny = x / width, y / height
    edge = np.minimum.reduce((nx, 1 - nx, ny * 1.6, (1 - ny) * 1.6))
    exposure = np.exp(-edge * 100)
    edge_noise = rng.normal(0, 2.0, (height, width)) * np.exp(-edge * 55)
    pixels = np.zeros((height, width, 3), dtype=np.float32)
    for channel, (base, gain) in enumerate(((4, 9), (12, 42), (13, 39))):
        pixels[:, :, channel] = base + exposure * gain + edge_noise
    backing = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    bloom = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(bloom)
    for margin, opacity in ((19, 150), (27, 65)):
        d.rounded_rectangle((margin, margin, width - margin - 1, height - margin - 1), radius=52, outline=(100, 229, 207, opacity), width=1)
        d.rounded_rectangle((margin + 1, margin + 1, width - margin, height - margin), radius=52, outline=(81, 115, 242, int(opacity * .3)), width=1)
    backing = Image.alpha_composite(backing.convert("RGBA"), bloom.filter(ImageFilter.GaussianBlur(9)))
    backing = Image.alpha_composite(backing, bloom.filter(ImageFilter.GaussianBlur(2)))
    backing = Image.alpha_composite(backing, bloom)
    etching = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(etching)
    for yy in range(-20, height + 30, 24):
        for xx in range(-20, width + 30, 28):
            if min(xx, width - xx) > 160 or min(yy, height - yy) > 65:
                continue
            cx = xx + (14 if (yy // 24) % 2 else 0)
            d.line((cx - 14, yy - 8, cx, yy - 16, cx + 14, yy - 8, cx + 14, yy + 8, cx, yy + 16, cx - 14, yy + 8, cx - 14, yy - 8), fill=(79, 214, 174, 18), width=1)
    for _ in range(36):
        xx = int(rng.integers(35, width - 35))
        yy = int(rng.choice([rng.integers(26, 55), rng.integers(height - 55, height - 26)]))
        d.line((xx, yy, xx + int(rng.integers(-65, 65)), yy + int(rng.integers(-12, 12))), fill=(139, 183, 154, 18), width=1)
    backing = Image.alpha_composite(backing, etching)
    backing.save(DESTINATION / "optical-backing.png", optimize=True)
    rim = np.zeros((height, width, 4), dtype=np.uint8)
    rim[:, :, :3] = (1, 5, 8)
    rim[:, :, 3] = np.clip(np.exp(-edge * 110) * 145, 0, 145).astype(np.uint8)
    Image.fromarray(rim).save(DESTINATION / "optical-rim.png", optimize=True)

    # Analog marks use a separate seed so adding them never changes the base glass.
    analog_rng = np.random.default_rng(20492049)
    wear = Image.new("RGBA", (1024, 512))
    marks = ImageDraw.Draw(wear)
    for _ in range(85):
        xx, yy = (int(v) for v in analog_rng.integers((0, 0), (1024, 512)))
        length = int(analog_rng.integers(3, 70))
        marks.line((xx, yy, min(1023, xx + length), yy), fill=(130, 190, 163, int(analog_rng.integers(6, 22))))
    for yy in (51, 137, 306, 431):
        for xx in range(0, 1024, 93):
            marks.line((xx, yy, min(1023, xx + int(analog_rng.integers(14, 76))), yy), fill=(71, 130, 113, 13))
    wear.save(DESTINATION / "analog-wear.png", optimize=True)

    sweep = np.zeros((80, 1024, 4), dtype=np.uint8)
    sweep[:, :, :3] = (115, 207, 175)
    rows = np.arange(80, dtype=np.float32)
    envelope = np.exp(-((rows - 53) / 16) ** 2) * 9
    envelope[55] = 40
    envelope[58] = 22
    envelope[61] = 12
    modulation = analog_rng.uniform(0.65, 1.0, (80, 1024))
    sweep[:, :, 3] = (envelope[:, None] * modulation).astype(np.uint8)
    sweep[55, 120:214, 3] //= 3
    sweep[55, 690:765, 3] //= 4
    Image.fromarray(sweep).save(DESTINATION / "analog-sweep.png", optimize=True)


if __name__ == "__main__":
    build()
