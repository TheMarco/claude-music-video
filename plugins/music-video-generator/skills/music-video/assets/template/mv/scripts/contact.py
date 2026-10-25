"""Build labeled contact sheets from (code, time) samples.

Usage: .venv/bin/python mv/scripts/contact.py OUT_PREFIX SPEC.json
SPEC.json is a list of [code, seconds] (archive codes or AI clip codes). Writes OUT_PREFIX_NN.jpg,
30 labeled thumbs per sheet, for picking in-points by eye.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from media import src_path as src  # noqa: E402

TW, TH, COLS, ROWS = 320, 200, 6, 5
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
except OSError:   # not macOS
    FONT = ImageFont.load_default(18)


def grab(code, t):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src(code)), "-frames:v", "1",
           "-vf", f"scale={TW}:{TH}:force_original_aspect_ratio=decrease,pad={TW}:{TH}:(ow-iw)/2:(oh-ih)/2",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if len(raw) < TW * TH * 3:
        return Image.new("RGB", (TW, TH), (40, 0, 0))
    return Image.frombytes("RGB", (TW, TH), raw[:TW * TH * 3])


def main():
    prefix, spec = sys.argv[1], json.loads(Path(sys.argv[2]).read_text())
    with ThreadPoolExecutor(12) as ex:
        thumbs = list(ex.map(lambda s: grab(*s), spec))
    per = COLS * ROWS
    for n in range(0, len(spec), per):
        sheet = Image.new("RGB", (COLS * TW, ROWS * (TH + 24)), (12, 12, 12))
        d = ImageDraw.Draw(sheet)
        for k, (im, (code, t)) in enumerate(zip(thumbs[n:n + per], spec[n:n + per])):
            x, y = (k % COLS) * TW, (k // COLS) * (TH + 24)
            sheet.paste(im, (x, y))
            d.text((x + 4, y + TH + 2), f"{code} {t:7.1f}", fill=(255, 220, 90), font=FONT)
        out = f"{prefix}_{n // per:02d}.jpg"
        sheet.save(out, quality=82)
        print(out)


if __name__ == "__main__":
    main()
