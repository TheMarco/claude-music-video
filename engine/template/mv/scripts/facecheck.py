"""Checks the overlay of every frame against the head boxes from heads.py: no word, card, caption or fine
print may land on a face.

  .venv/bin/python mv/scripts/facecheck.py [--size 1920x1080] [--start S] [--end E]

Draws fx.py's front layer for each frame at --size (the output size), and the behind layer on shots with
no person matte (where nothing hides it), then lists every frame where pixels above 15% opacity fall
inside a head box, and every block ov.place() found no clear spot for. Exits 1 when anything is listed,
so a render that fails it is not delivered. It checks against mv/data/heads.json, so run heads.py after
every EDL change, and look at its sheets first: a head the sheets show without a box is not checked.
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from timing import DUR, FPS, on_frame  # noqa: E402

ALPHA = 40


def work(job):
    frames, (W, H) = job
    from media import is_ai, matte_path
    from overlay import Overlay
    ov = Overlay(W, H)
    heads = json.loads(Path("mv/data/heads.json").read_text())["frames"]
    segs = json.loads(Path("mv/data/edl.json").read_text())["main"]
    bad = []
    for n in frames:
        t = n / FPS
        seg = None
        for s in segs:
            if on_frame(s["start"]) <= t:
                seg = s
        if seg is None:
            continue
        local = t - on_frame(seg["start"])
        behind, front = ov.frame(t, {"src": seg["src"], "local": local, "dur": seg["dur"], "label": seg.get("label")})
        matted = seg.get("matte") or (is_ai(seg["src"]) and matte_path(seg["src"]).exists())
        layers = [x for x in (front, None if matted else behind) if x is not None]
        for b in heads.get(str(n), []):
            x0, y0 = max(0, int(b[0] * W)), max(0, int(b[1] * H))
            x1, y1 = min(W, int(b[2] * W)), min(H, int(b[3] * H))
            if x1 <= x0 or y1 <= y0:
                continue
            cover = max(float((lay[y0:y1, x0:x1, 3] > ALPHA).mean()) for lay in layers) if layers else 0.0
            if cover > 0:
                bad.append((n, round(t, 2), seg["src"], [round(v, 2) for v in b], round(cover, 3)))
    return bad, ov.place_misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    args = ap.parse_args()
    if not Path("mv/data/heads.json").exists():
        sys.exit("no mv/data/heads.json: run mv/scripts/heads.py first")
    W, H = map(int, args.size.lower().split("x"))
    frames = list(range(int(args.start * FPS), int(min(args.end, DUR) * FPS)))
    k = max(1, min(os.cpu_count() or 4, 12))
    with Pool(k) as p:
        res = p.map(work, [(frames[i::k], (W, H)) for i in range(k)])
    bad = sorted(b for r, _ in res for b in r)
    misses = sorted({m for _, ms in res for m in ms})
    print(f"{len(frames)} frames checked: {len(bad)} with overlay on a face, {len(misses)} blocks with no clear spot")
    runs = []
    for n, t, src, box, cover in bad:
        if runs and n - runs[-1][1] <= 2 and runs[-1][2] == src:
            runs[-1][1], runs[-1][4] = n, max(runs[-1][4], cover)
        else:
            runs.append([n, n, src, box, cover])
    for a, b, src, box, cover in runs:
        print(f"  {a / FPS:6.2f}-{b / FPS:6.2f}s  {src}  head {box}  up to {cover:.1%} of the box covered")
    for m in misses:
        print("  no clear spot:", m)
    sys.exit(1 if bad or misses else 0)


if __name__ == "__main__":
    main()
