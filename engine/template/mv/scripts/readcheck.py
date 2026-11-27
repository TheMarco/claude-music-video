"""Checks that every piece of type can be read: long enough on screen, large enough on a phone, clear of
the frame's edges.

  .venv/bin/python mv/scripts/readcheck.py [--size 1920x1080] [--step 2] [--start S] [--end E]
                                           [--floor 2.0] [--fine-print] [--strict]

Draws fx.py's front layer at --size (the output size) for every sampled frame, splits it into elements the
way contrastcheck.py does (the words of a line joined, lines and cards apart), follows each element from
frame to frame, and lists:

  too short    type on screen for less than it takes to read: 0.4 s for one or two words, otherwise three
               quarters of 0.5 s plus 0.3 s a word (three words 1.05 s, six words 1.7 s); a card under
               1.2 s. Words are estimated from the line's width and height, so treat a near miss as a hint.
  too small    type whose line is lower than --floor percent of the frame's short side (2.0: about 22 px
               at 1080, a 28 px font) for half a second or more: unreadable on a phone. --fine-print
               lowers the floor to 1.3 for a style that wants fine print at the edges (slopcore).
  at the edge  type or a card closer to the frame's edge than the safe margin (4% at the sides, 5% top
               and bottom; on vertical output 8% at the top and 14% at the bottom, where the feed's own
               buttons and captions sit) for half a second or more.

Each case is drawn into mv/review/read_NN.jpg at phone size (360 px wide), over the clean frame when
heads.py has written one: if you can't read it there, a viewer can't. It is a report: it exits 0 unless
--strict is given, because drifting particles and marks are elements too and a one-word hit can be meant
to be short. Fix what is listed or know why it stands.
"""
import argparse
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from timing import DUR, FPS  # noqa: E402

FRAMES = Path("mv/work/heads/frames")


def elements(front, W, H):
    """[(kind, (x0, y0, x1, y1) in 0..1)] for every element of this frame's overlay."""
    ink = front[..., 3] > 127
    if not ink.any():
        return []
    gy, gx = max(2, round(0.004 * H)), max(3, round(0.025 * W))
    lab, _ = ndimage.label(ndimage.binary_dilation(ink, np.ones((gy, gx), bool)))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        ys, xs = sl
        el = (lab[sl] == i) & ink[sl]
        if el.sum() < max(25, 0.00012 * W * H):   # specks: particles and sparks, not something to read
            continue
        solid = ndimage.distance_transform_edt(el).max() > 0.045 * W
        out.append(("panel" if solid else "type", (xs.start / W, ys.start / H, xs.stop / W, ys.stop / H)))
    return out


def work(job):
    frames, (W, H) = job
    from overlay import Overlay
    if not frames:
        return []
    ov = Overlay(W, H)
    res = []
    for n in frames:
        _, front = ov.frame(n / FPS, {})
        if front is not None:
            res += [(n, kind, box) for kind, box in elements(front, W, H)]
    return res


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0


def words(box, W, H):
    """A line's word count from its shape: letters are about 0.55 of the line height wide, a word with its
    space about five and a half letters."""
    h = (box[3] - box[1]) * H
    return max(1, round((box[2] - box[0]) * W / max(0.55 * h, 1) / 5.5))


def read_time(n):
    return 0.4 if n <= 2 else min(3.0, 0.75 * (0.5 + 0.3 * n))


def sheet(cases, W, H):
    from overlay import Overlay
    for old in Path("mv/review").glob("read_*.jpg"):
        old.unlink()
    if not cases:
        return 0
    ov = Overlay(W, H)
    TW = 360
    TH = round(TW * H / W)
    COLS, PER = (5, 15) if H > W else (4, 16)
    for k in range(0, len(cases), PER):
        chunk = cases[k:k + PER]
        rows = (len(chunk) + COLS - 1) // COLS
        out = Image.new("RGB", (COLS * TW, rows * (TH + 16)), (12, 12, 12))
        d = ImageDraw.Draw(out)
        for j, c in enumerate(chunk):
            n = c["n_mid"]
            p = FRAMES / f"{n:05d}.jpg"
            im = (Image.open(p).convert("RGBA").resize((W, H), Image.BICUBIC) if p.exists()
                  else Image.new("RGBA", (W, H), (70, 70, 70, 255)))
            _, front = ov.frame(n / FPS, {})
            if front is not None:
                im.alpha_composite(Image.fromarray(front, "RGBA"))
            im = im.convert("RGB").resize((TW, TH), Image.LANCZOS)
            b = c["box"]
            ImageDraw.Draw(im).rectangle((b[0] * TW - 2, b[1] * TH - 2, b[2] * TW + 2, b[3] * TH + 2),
                                         outline=(255, 230, 0), width=2)
            x, y = (j % COLS) * TW, (j // COLS) * (TH + 16)
            out.paste(im, (x, y + 16))
            d.text((x + 3, y + 2), f"{c['t0']:.2f}s {c['why']}", fill=(255, 220, 120))
        out.save(f"mv/review/read_{k // PER:02d}.jpg", quality=85)
    return (len(cases) + PER - 1) // PER


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="1920x1080", help="the output size")
    ap.add_argument("--step", type=int, default=2, help="check every Nth frame")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    ap.add_argument("--floor", type=float, default=2.0, help="lowest line height, percent of the short side")
    ap.add_argument("--fine-print", action="store_true", help="a style with fine print: floor 1.3")
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything is listed")
    args = ap.parse_args()
    W, H = map(int, args.size.lower().split("x"))
    floor = (1.3 if args.fine_print else args.floor) / 100 * min(W, H) / H
    vertical = H > W * 1.2
    mx, top, bottom = 0.04, (0.08 if vertical else 0.05), (0.14 if vertical else 0.05)
    n0, n1 = int(args.start * FPS), int(min(args.end, DUR) * FPS)
    frames = list(range(n0, n1, args.step))
    k = max(1, min(os.cpu_count() or 4, 12))
    with Pool(k) as p:
        res = p.map(work, [(frames[i::k], (W, H)) for i in range(k)])
    hits = sorted((h for r in res for h in r), key=lambda h: h[0])
    runs, live = [], []
    for n, kind, box in hits:
        live = [r for r in live if n - r["n1"] <= 3 * args.step]
        for r in live:
            if r["n1"] < n and iou(r["box"], box) > 0.3:   # a card fading out turns into its type: one element
                r["n1"], r["box"] = n, box
                r["boxes"].append(box)
                break
        else:
            r = {"n0": n, "n1": n, "kind": kind, "box": box, "boxes": [box]}
            runs.append(r)
            live.append(r)
    cases = []
    for r in runs:
        dur = (r["n1"] - r["n0"] + args.step) / FPS
        cut = r["n0"] <= n0 + args.step or r["n1"] >= n1 - 2 * args.step   # runs past the span checked
        big = max(r["boxes"], key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        hgt = float(np.median([b[3] - b[1] for b in r["boxes"]]))
        why = []
        if r["kind"] == "panel":
            if dur < 1.2 and not cut:
                why.append(f"card up {dur:.2f}s (1.2s to read)")
        else:
            nw = words(big, W, H)
            if dur < read_time(nw) - 0.5 * args.step / FPS and not cut:
                why.append(f"up {dur:.2f}s, ~{nw} words want {read_time(nw):.2f}s")
            if hgt < floor and dur >= 0.5:
                why.append(f"line {hgt * H:.0f}px high (floor {floor * H:.0f}px)")
        if dur >= 0.5:
            near = [b for b in r["boxes"] if b[0] < mx or b[2] > 1 - mx or b[1] < top or b[3] > 1 - bottom]
            if len(near) * args.step / FPS >= 0.5:
                why.append("inside the edge margin")
        if why:
            cases.append({"t0": r["n0"] / FPS, "t1": (r["n1"] + args.step) / FPS, "box": big, "kind": r["kind"],
                          "why": "; ".join(why), "n_mid": r["n0"] + ((r["n1"] - r["n0"]) // (2 * args.step)) * args.step})
    Path("mv/review").mkdir(parents=True, exist_ok=True)
    pages = sheet(cases, W, H)
    print(f"{len(frames)} frames checked, {len(runs)} elements followed: {len(cases)} to look at")
    for c in cases:
        b = c["box"]
        print(f"  {c['t0']:6.2f}-{c['t1']:6.2f}s  {c['kind']:5s} at x {b[0]:.2f}-{b[2]:.2f} y {b[1]:.2f}-{b[3]:.2f}  {c['why']}")
    if pages:
        print(f"review at phone size: mv/review/read_00.jpg .. read_{pages - 1:02d}.jpg")
    sys.exit(1 if cases and args.strict else 0)


if __name__ == "__main__":
    main()
