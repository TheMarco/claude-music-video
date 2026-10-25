"""Tile render stills into review sheets: sheet.py PREFIX OUT_PREFIX [per_sheet]

Also prints each still's tones: black = share of pixels under 10% luma, p5/p50 = 5th and 50th
percentile luma. A dark or moody brief needs real blacks: dark shots in a rich, moody grade measure
black 0.25-0.95, while a pale, printed-looking picture sits around 0.05-0.15 on every shot with p5
above 0.05.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

prefix, out = sys.argv[1], sys.argv[2]
per = int(sys.argv[3]) if len(sys.argv) > 3 else 6
fs = sorted(Path(prefix).parent.glob(Path(prefix).name + "_*.jpg"))
try:
    f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
except OSError:   # not macOS
    f = ImageFont.load_default(22)
rows = (per + 1) // 2
tones = []
for k in range(0, len(fs), per):
    sheet = Image.new("RGB", (1920, 540 * rows))
    for i, p in enumerate(fs[k:k + per]):
        im = Image.open(p).resize((960, 540))
        lum = np.asarray(im.convert("L"), dtype=np.float32) / 255
        tones.append(float(np.mean(lum < 0.1)))
        print(f"  {p.stem.split('_')[-1]:>8}  black {tones[-1]:.2f}  p5 {np.percentile(lum, 5):.2f}  p50 {np.median(lum):.2f}")
        sheet.paste(im, ((i % 2) * 960, (i // 2) * 540))
        ImageDraw.Draw(sheet).text(((i % 2) * 960 + 8, (i // 2) * 540 + 8), p.stem.split("_")[-1], fill=(0, 255, 0), font=f)
    sheet.save(f"{out}_{k // per}.jpg", quality=85)
    print(f"{out}_{k // per}.jpg")
print(f"median black share across stills: {np.median(tones):.2f}")
