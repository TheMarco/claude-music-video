"""Build labeled contact sheets from (code, time) samples, or of every shot in the edit.

Usage: .venv/bin/python mv/scripts/contact.py OUT_PREFIX SPEC.json
       .venv/bin/python mv/scripts/contact.py OUT_PREFIX --edl
SPEC.json is a list of [code, seconds] (archive codes or AI clip codes). Writes OUT_PREFIX_NN.jpg,
30 labeled thumbs per sheet, for picking in-points by eye.

--edl samples every main-track shot of mv/data/edl.json at its midpoint, cropped the way the render
crops it, labeled with the shot number, song time and code, and prints a brightness report. Look at
every sheet before a full render: it catches title cards, in-points on the wrong side of a cut, shots
too dark to read and skies that will blow out. Shots flagged bright (mean luma above 0.42 or 90th
percentile above 0.85) usually want expo=0.6-0.8 in the EDL; flagged shots get a red frame.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from media import crop_for, is_gen, is_image, src_path as src  # noqa: E402

TW, TH, COLS, ROWS = 320, 200, 6, 5
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 18)
except OSError:   # not macOS
    FONT = ImageFont.load_default(18)


def grab(code, t, crop=None):
    vf = f"scale={TW}:{TH}:force_original_aspect_ratio=decrease,pad={TW}:{TH}:(ow-iw)/2:(oh-ih)/2"
    if crop:
        x, y, w, h = crop
        vf = f"crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f}," + vf
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src(code)), "-frames:v", "1",
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if len(raw) < TW * TH * 3:
        return Image.new("RGB", (TW, TH), (40, 0, 0))
    return Image.frombytes("RGB", (TW, TH), raw[:TW * TH * 3])


def edl_spec():
    """(code, source time, label, shot) for every main-track shot that shows footage."""
    segs = json.loads(Path("mv/data/edl.json").read_text())["main"]
    out = []
    for i, s in enumerate(segs):
        if s["src"] == "BLACK" or is_gen(s["src"]):
            continue
        t = 0.0 if is_image(s["src"]) else s["in"] + s["dur"] * s.get("speed", 1.0) / 2
        out.append((s["src"], t, f"{i:03d} {s['start']:6.1f}s {s['src']}", s))
    return out


def sheets(prefix, items, thumbs, flags):
    per = COLS * ROWS
    for n in range(0, len(items), per):
        sheet = Image.new("RGB", (COLS * TW, ROWS * (TH + 24)), (12, 12, 12))
        d = ImageDraw.Draw(sheet)
        for k, (im, label, flag) in enumerate(zip(thumbs[n:n + per], items[n:n + per], flags[n:n + per])):
            x, y = (k % COLS) * TW, (k // COLS) * (TH + 24)
            sheet.paste(im, (x, y))
            if flag:
                d.rectangle((x, y, x + TW - 1, y + TH - 1), outline=(255, 40, 40), width=4)
            d.text((x + 4, y + TH + 2), label, fill=(255, 220, 90), font=FONT)
        out = f"{prefix}_{n // per:02d}.jpg"
        sheet.save(out, quality=82)
        print(out)


def main():
    prefix = sys.argv[1]
    if sys.argv[2] == "--edl":
        spec = edl_spec()
        with ThreadPoolExecutor(12) as ex:
            thumbs = list(ex.map(lambda e: grab(e[0], e[1], crop_for(e[0])), spec))
        flags = []
        print(f"{'shot':18} {'grade':8} {'expo':>4} {'mean':>5} {'p90':>5}")
        for (code, t, label, s), im in zip(spec, thumbs):
            lum = np.asarray(im.convert("L"), dtype=np.float32) / 255
            mean, p90, expo = float(lum.mean()), float(np.percentile(lum, 90)), s.get("expo", 1.0)
            note = ""
            if (mean * expo > 0.42 or p90 * expo > 0.85) and expo > 0.85:
                note = "bright: try expo=0.6-0.8"
            elif mean * expo < 0.06 and p90 * expo < 0.25:
                note = "dark: check it reads"
            flags.append(bool(note))
            print(f"{label:18} {s.get('grade', ''):8} {expo:4.2f} {mean:5.2f} {p90:5.2f}  {note}")
        print(f"{sum(flags)} of {len(flags)} shots flagged")
        sheets(prefix, [e[2] for e in spec], thumbs, flags)
        return
    spec = json.loads(Path(sys.argv[2]).read_text())
    with ThreadPoolExecutor(12) as ex:
        thumbs = list(ex.map(lambda s: grab(*s), spec))
    sheets(prefix, [f"{code} {t:7.1f}" for code, t in spec], thumbs, [False] * len(spec))


if __name__ == "__main__":
    main()
