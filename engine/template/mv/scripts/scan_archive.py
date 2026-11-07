"""Per-second visual stats for each archive film (2 samples/s at 96x72).

Usage: .venv/bin/python mv/scripts/scan_archive.py
Writes mv/data/scan/<id>.npz with arrays t, luma, hi, sat_hi, diff, colorful, then
mv/data/candidates.json with, per film, "night" runs (dark frames with bright colored highlights:
neon, marquees, city lights) and "flash" times (very bright frames or sudden jumps: explosions,
fireworks, flashbulbs). Feed those times into contact.py instead of eyeballing whole films.
"""
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ARCH = Path("mv/archive")
OUT = Path("mv/data/scan")
W, H, FPS = 96, 72, 2


def scan(d):
    f = next(p for p in d.iterdir() if p.suffix == ".mp4")
    out = OUT / f"{d.name}.npz"
    if out.exists():
        return d.name, "cached"
    cmd = ["ffmpeg", "-v", "error", "-i", str(f), "-vf", f"fps={FPS},scale={W}:{H}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.float32)
    r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    mx, mn = fr.max(-1), fr.min(-1)
    sat = (mx - mn) / (mx + 1e-3)
    hi = y > 190
    luma = y.mean((1, 2))
    hif = hi.mean((1, 2))
    sat_hi = np.where(hi, sat, 0).sum((1, 2)) / np.maximum(hi.sum((1, 2)), 1)
    bright_col = ((y > 120) & (sat > 0.45)).mean((1, 2))
    diff = np.r_[0, np.abs(np.diff(y, axis=0)).mean((1, 2))]
    t = np.arange(len(fr)) / FPS
    np.savez(out, t=t, luma=luma, hi=hif, sat_hi=sat_hi, colorful=bright_col, diff=diff)
    return d.name, len(fr)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    dirs = sorted(p for p in ARCH.iterdir() if p.is_dir())
    with ProcessPoolExecutor(8) as ex:
        for name, n in ex.map(scan, dirs):
            print(name, n)
    cand = {}
    for f in sorted(OUT.glob("*.npz")):
        d = np.load(f)
        t, L, hi, col, sh = d["t"], d["luma"], d["hi"], d["colorful"], d["sat_hi"]
        night = (L < 60) & (hi > 0.002) & (hi < 0.25) & ((col > 0.002) | (sh > 0.25))
        runs, i = [], 0
        while i < len(night):
            if night[i]:
                j = i
                while j < len(night) and (night[j] or (j + 1 < len(night) and night[j + 1])):
                    j += 1
                if j - i >= 3:
                    runs.append([float(t[i]), float(t[j - 1])])
                i = j
            else:
                i += 1
        flash = np.where((L > 175) | (np.r_[0, np.diff(L)] > 70))[0]
        cand[f.stem] = {"night": runs, "flash": [float(t[k]) for k in flash]}
        print(f"{f.stem[:44]:44} night {sum(b - a for a, b in runs):6.1f}s in {len(runs)} runs, {len(flash)} flashes")
    (Path("mv/data") / "candidates.json").write_text(json.dumps(cand, indent=1))
