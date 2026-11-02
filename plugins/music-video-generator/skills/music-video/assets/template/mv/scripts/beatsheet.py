"""One frame per beat of a rendered video, tiled and labeled, to check how a drop or a build moves.

Usage: .venv/bin/python mv/scripts/beatsheet.py VIDEO OUT.jpg T0 N [BEATS_PER_FRAME] [--start S]
Frames sit on the song's real beats (timing.py, so drifting tempos stay on the beat), starting at the
beat nearest T0; BEATS_PER_FRAME 0.5 gives half beats, 2 every other beat. --start S for a video
rendered with render.py --start S. Each tile shows its song time and beat offset; drops are marked.
For a drop: T0 a bar before it, N 16 or 32.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from timing import DROPS, FPS, beat, beat_at  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("out")
ap.add_argument("t0", type=float)
ap.add_argument("n", type=int)
ap.add_argument("step", type=float, nargs="?", default=1.0)
ap.add_argument("--start", type=float, default=0.0)
args = ap.parse_args()

k0 = round(beat_at(args.t0))
times = [beat(k0 + i * args.step) for i in range(args.n)]
frames = [max(0, int(round((t - args.start) * FPS))) for t in times]
TW, TH = 480, 270
sel = "+".join(f"eq(n\\,{f})" for f in sorted(set(frames)))
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", args.video, "-vf", f"select='{sel}',scale={TW}:{TH}",
                      "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
got = {f: raw[k * TW * TH * 3:(k + 1) * TW * TH * 3] for k, f in enumerate(sorted(set(frames)))}
try:
    font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
except OSError:   # not macOS
    font = ImageFont.load_default(16)
rows = (args.n + 3) // 4
sheet = Image.new("RGB", (4 * TW, rows * TH), (20, 0, 0))
for i, (t, f) in enumerate(zip(times, frames)):
    data = got.get(f, b"")
    im = Image.frombytes("RGB", (TW, TH), data) if len(data) == TW * TH * 3 else Image.new("RGB", (TW, TH), (60, 0, 0))
    d = ImageDraw.Draw(im)
    drop = any(abs(t - x) < 0.5 * (beat(k0 + 1) - beat(k0)) for x in DROPS)
    d.text((6, 4), f"{t:7.2f}s  +{i * args.step:g}" + ("  DROP" if drop else ""),
           fill=(255, 80, 80) if drop else (255, 220, 90), font=font)
    sheet.paste(im, ((i % 4) * TW, (i // 4) * TH))
sheet.save(args.out, quality=85)
print(args.out)
