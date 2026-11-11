"""Check a clip's real frame rate and, when its file misreports it, rewrite it with every frame once.

Usage: .venv/bin/python mv/scripts/conform.py CLIP.mp4 [CLIP.mp4 ...] [--fps N] [--check]

Some generators deliver files whose stated frame rate is not what they hold: a 24 fps take written on a
60 fps clock, with uneven gaps between frames. Read at the stated rate, such a clip gets frames
duplicated or dropped, and the picture stutters. For each clip this counts the frames, divides by the
duration, and compares that with the rate the file states and with how even the gaps between frames are.
A clean clip is left alone. Otherwise the original moves to an "original" folder next to the clip and
the clip is rewritten at the nearest standard rate (or --fps) with every source frame shown exactly
once, in order (setpts=N/FPS/TB); the sound is copied unchanged. The clip's person matte and its cached
segments are removed, since they were made from the old frames.

--check only reports. Run it on every generated clip before mattes, sync measurement and the edit.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

STANDARD = {23.976: "24000/1001", 24: "24", 25: "25", 29.97: "30000/1001", 30: "30", 48: "48", 50: "50",
            59.94: "60000/1001", 60: "60"}


def probe(path):
    """(stated fps, real fps, frames, duration, share of uneven gaps)."""
    j = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate:packet=pts_time", "-of", "json", str(path)], capture_output=True, text=True).stdout)
    num, den = j["streams"][0]["r_frame_rate"].split("/")
    stated = float(num) / float(den)
    pts = np.sort(np.array([float(p["pts_time"]) for p in j["packets"] if p.get("pts_time") not in (None, "N/A")]))
    if len(pts) < 3:
        sys.exit(f"{path}: no readable video frames")
    gaps = np.diff(pts)
    span = float(pts[-1] - pts[0])
    real = (len(pts) - 1) / span
    uneven = float((np.abs(gaps - np.median(gaps)) > 0.2 * np.median(gaps)).mean())
    return stated, real, len(pts), span + float(np.median(gaps)), uneven


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--fps", type=float, default=None, help="target rate; default: the standard rate nearest the real one")
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()
    changed = 0
    for name in args.clips:
        clip = Path(name)
        if clip.stem.endswith("_matte"):
            continue
        stated, real, n, dur, uneven = probe(clip)
        target = args.fps or min(STANDARD, key=lambda r: abs(r - real))
        clean = abs(stated - real) < 0.01 * real and uneven < 0.02 and abs(target - real) < 0.01 * real
        head = f"{clip.name}: {n} frames in {dur:.2f} s = {real:.3f} fps, file states {stated:.3f}, {uneven:.0%} uneven gaps"
        if clean:
            print(head + "  -> clean")
            continue
        stretch = real / target - 1
        print(head + f"  -> {'needs conforming' if args.check else 'conforming'} to {target:g} fps")
        if abs(stretch) > 0.005:
            print(f"  NOTE the picture gets {abs(stretch):.1%} {'longer' if stretch > 0 else 'shorter'} than its sound: "
                  "measure a lip-sync take again afterwards, or pass --fps with the rate it was made at")
        changed += 1
        if args.check:
            continue
        keep = clip.parent / "original" / clip.name
        keep.parent.mkdir(exist_ok=True)
        if keep.exists():   # an earlier take of the same code
            k = len(list(keep.parent.glob(f"{clip.stem}_take*{clip.suffix}"))) + 1
            keep.rename(keep.parent / f"{clip.stem}_take{k}{clip.suffix}")
        clip.rename(keep)
        rate = STANDARD.get(target, f"{target:g}")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(keep), "-vf", f"setpts=N/({rate})/TB", "-fps_mode", "cfr",
                        "-r", rate, "-c:v", "libx264", "-crf", "13", "-preset", "medium", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", str(clip)], check=True)
        got = probe(clip)[2]
        if got != n:
            sys.exit(f"{clip.name}: {n} frames in, {got} out; the original is at {keep}")
        (clip.parent / f"{clip.stem}_matte.mp4").unlink(missing_ok=True)
        for seg in Path("mv/work/seg").glob(f"{clip.stem}_*"):
            seg.unlink()
        print(f"  wrote {clip} ({got} frames, every one once); original kept at {keep}")
    if args.check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
