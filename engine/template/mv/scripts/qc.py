"""Quick technical QC of a rendered video: unexpected black frames and frozen stretches.

Usage: .venv/bin/python mv/scripts/qc.py OUT.mp4 [--ignore-before 1.0] [--ignore-after END]
Low-motion stretches are not always bugs (a white flash, a dark title card); check each listed time.
"""
import argparse
import subprocess

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--ignore-before", type=float, default=1.0)
ap.add_argument("--ignore-after", type=float, default=1e9)
args = ap.parse_args()
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", args.video, "-vf", "scale=64:36,format=gray",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
d = np.frombuffer(raw, np.uint8).reshape(-1, 36 * 64).astype(float)
rate = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                       "-of", "csv=p=0", args.video], capture_output=True, text=True).stdout.strip().strip(",")
num, _, den = rate.partition("/")
fps = float(num) / float(den or 1) if num else 24.0
m = d.mean(1)
diff = np.r_[0, np.abs(np.diff(d, axis=0)).mean(1)]
ok = lambda i: args.ignore_before < i / fps < args.ignore_after
dark = [round(i / fps, 2) for i in np.where(m < 6)[0] if ok(i)]
runs, i = [], 0
while i < len(diff):
    if diff[i] < 0.15:
        j = i
        while j < len(diff) and diff[j] < 0.15:
            j += 1
        if j - i >= 10 and ok(i):
            runs.append((round(i / fps, 2), j - i))
        i = j
    else:
        i += 1
print(f"frames {len(m)}  ({len(m) / fps:.2f}s)")
print("black frames:", dark[:20], "..." if len(dark) > 20 else "")
print("low-motion runs (start s, frames):", runs)
