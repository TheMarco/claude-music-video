"""Checks that every overlay element stands out from the picture it plays on.

  .venv/bin/python mv/scripts/contrastcheck.py [--size 1920x1080] [--step 2] [--start S] [--end E]
                                               [--large 3.0] [--small 4.5]

Uses the clean frames heads.py wrote (the edit without overlays, mv/work/heads/frames/), scaled up to
--size (the output size: fine print and outlines only resolve there), and draws fx.py's front layer at
that size, so run heads.py first and again after every EDL change. Each sampled frame's
overlay is split into elements: glyphs merged into words and lines, cards, icons. For each element it
takes the element's own luminance (composited, translucency included; its fill, or its outline or a
panel's rim when that reads better) and the luminance right around it on the side that is worse: for a
light element the brighter fifth of its surroundings with its drop shadow (the shadow is what holds it),
for a dark element the darker fifth of the bare picture (its shadow is its own tone). The score is the
contrast ratio, (L1 + 0.05) / (L2 + 0.05). Type with its own outline (a dark stroke round light letters,
or the reverse) scores the outline against the fill instead, since it reads on any picture.

  type over the picture   at least --large (3:1) when large, --small (4.5:1) when under 2.5% of the
                          frame height (fine print, captions), the WCAG levels for large and small text
  a solid panel (a card)  at least 1.5:1 against the typical (median) part of its surroundings, by its fill
                          or its rim (a panel: a solid core wider than 9% of the frame): its own text sits on its own fill, but a card that
                          sinks into the picture reads as loose type

An element under its level for 0.25 s or more is listed with its time, place, kind and worst ratio and
drawn into mv/review/contrast_NN.jpg (the composited frame, element boxed in yellow). Exits 1 when
anything is listed. The usual fixes, per shot: a stronger or wider shadow, a soft dark band behind the
block, an outline, the dark variant of the type on a bright sky, or a darker part of the frame
(ov.backdrop(rect, t) measures the picture under a rect, so fx.py can choose per shot).
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
PANEL_MIN = 1.5
SMALL_H = 0.025
MIN_RUN = 0.25


def luminance(rgb):
    """Relative luminance (0..1) of sRGB values in 0..1."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def ratio(a, b):
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def elements(front, bg, W, H, large, small):
    """[(kind, bbox, ratio, needed)] for every element of this frame's overlay."""
    a = front[..., 3].astype(np.float32) / 255
    comp = front[..., :3].astype(np.float32) / 255 * a[..., None] + bg * (1 - a[..., None])
    L, Lbg = luminance(comp), luminance(bg)
    ink = a > 0.5
    if not ink.any():
        return []
    gy, gx = max(2, round(0.004 * H)), max(3, round(0.025 * W))   # words of a line join, lines stay apart
    lab, n = ndimage.label(ndimage.binary_dilation(ink, np.ones((gy, gx), bool)))
    r1, r2 = 1, max(3, round(0.008 * W))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        ys, xs = sl
        y0, y1 = max(0, ys.start - r2 - 1), min(H, ys.stop + r2 + 1)
        x0, x1 = max(0, xs.start - r2 - 1), min(W, xs.stop + r2 + 1)
        el = (lab[y0:y1, x0:x1] == i) & ink[y0:y1, x0:x1]
        cnt = int(el.sum())
        if cnt < 25:
            continue
        ring = (ndimage.binary_dilation(el, iterations=r2) & ~ndimage.binary_dilation(el, iterations=r1)
                & ~ink[y0:y1, x0:x1])
        if ring.sum() < 10:
            continue
        sub, picture = L[y0:y1, x0:x1], Lbg[y0:y1, x0:x1]
        with_shadow, bare = sub[ring], picture[ring]
        bh, bw = ys.stop - ys.start, xs.stop - xs.start
        # a panel has a solid core far wider than any letter stroke; heavy type does not
        solid = ndimage.distance_transform_edt(el).max() > 0.045 * W
        cands = [float(np.median(sub[el])), float(np.percentile(sub[el], 90))]   # the fill, or an outline
        if solid:   # or a panel's rim
            cands.append(float(np.percentile(sub[el & ~ndimage.binary_erosion(el, iterations=2)], 90)))
        q_hi, q_lo = (50, 50) if solid else (80, 20)   # type: the worst side; a panel: its typical edge
        best = 0.0
        for li in cands:
            # light on the picture: its shadow helps, so measure what is around it; dark on the picture:
            # the shadow is its own tone, so measure the bare picture
            lb = (float(np.percentile(with_shadow, q_hi)) if li >= float(np.median(bare))
                  else float(np.percentile(bare, q_lo)))
            best = max(best, ratio(li, lb))
        if not solid:   # type with its own outline (light fill, dark edge, or the reverse) carries itself
            lo, hi = float(np.percentile(sub[el], 5)), float(np.percentile(sub[el], 95))
            edge = el & ~ndimage.binary_erosion(el)
            inner = sub[el & ~edge]
            em, band = float(np.median(sub[edge])), 0.25 * (hi - lo)
            if inner.size and ((em <= lo + band and (inner >= hi - band).mean() >= 0.2)
                               or (em >= hi - band and (inner <= lo + band).mean() >= 0.2)):
                best = max(best, ratio(hi, lo))
        kind = "panel" if solid else ("small type" if bh < SMALL_H * H else "type")
        need = PANEL_MIN if solid else (small if bh < SMALL_H * H else large)
        out.append((kind, (xs.start / W, ys.start / H, xs.stop / W, ys.stop / H), best, need))
    return out


def work(job):
    frames, large, small, (W, H) = job
    from overlay import Overlay
    if not frames:
        return []
    ov = Overlay(W, H)
    res = []
    for n in frames:
        p = FRAMES / f"{n:05d}.jpg"
        if not p.exists():
            continue
        _, front = ov.frame(n / FPS, {})
        if front is None:
            continue
        bg = np.asarray(Image.open(p).convert("RGB").resize((W, H), Image.BICUBIC), dtype=np.float32) / 255
        for kind, box, r, need in elements(front, bg, W, H, large, small):
            if r < need:
                res.append((n, kind, box, r, need))
    return res


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0


def sheet(runs, W, H):
    from overlay import Overlay
    for old in Path("mv/review").glob("contrast_*.jpg"):
        old.unlink()
    if not runs:
        return 0
    ov = Overlay(W, H)
    TW = 216 if H > W else 320
    TH = round(TW * H / W)
    COLS, PER = (10, 30) if H > W else (6, 24)
    for k in range(0, len(runs), PER):
        chunk = runs[k:k + PER]
        rows = (len(chunk) + COLS - 1) // COLS
        out = Image.new("RGB", (COLS * TW, rows * (TH + 16)), (12, 12, 12))
        d = ImageDraw.Draw(out)
        for j, r in enumerate(chunk):
            n = r["worst_n"]
            im = Image.open(FRAMES / f"{n:05d}.jpg").convert("RGBA").resize((W, H), Image.BICUBIC)
            _, front = ov.frame(n / FPS, {})
            if front is not None:
                im.alpha_composite(Image.fromarray(front, "RGBA"))
            im = im.convert("RGB").resize((TW, TH))
            b = r["box"]
            ImageDraw.Draw(im).rectangle((b[0] * TW - 2, b[1] * TH - 2, b[2] * TW + 2, b[3] * TH + 2),
                                         outline=(255, 230, 0), width=2)
            x, y = (j % COLS) * TW, (j // COLS) * (TH + 16)
            out.paste(im, (x, y + 16))
            d.text((x + 3, y + 2), f"{r['t0']:.2f}s {r['kind']} {r['worst']:.1f}:1", fill=(255, 220, 120))
        out.save(f"mv/review/contrast_{k // PER:02d}.jpg", quality=82)
    return (len(runs) + PER - 1) // PER


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="1920x1080", help="the output size")
    ap.add_argument("--step", type=int, default=2, help="check every Nth frame")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    ap.add_argument("--large", type=float, default=3.0)
    ap.add_argument("--small", type=float, default=4.5)
    args = ap.parse_args()
    if not (FRAMES / "00000.jpg").exists():
        sys.exit("no clean frames in mv/work/heads/frames: run mv/scripts/heads.py first")
    W, H = map(int, args.size.lower().split("x"))
    frames = list(range(int(args.start * FPS), int(min(args.end, DUR) * FPS), args.step))
    k = max(1, min(os.cpu_count() or 4, 12))
    with Pool(k) as p:
        res = p.map(work, [(frames[i::k], args.large, args.small, (W, H)) for i in range(k)])
    hits = sorted((h for r in res for h in r), key=lambda h: h[0])
    runs = []
    for n, kind, box, r, need in hits:
        for run in runs:
            if run["kind"] == kind and 0 < n - run["n1"] <= 3 * args.step and iou(run["box"], box) > 0.3:
                run["n1"], run["box"] = n, box
                if r < run["worst"]:
                    run["worst"], run["worst_n"] = r, n
                break
        else:
            runs.append({"n0": n, "n1": n, "kind": kind, "box": box, "worst": r, "worst_n": n, "need": need})
    runs = [r for r in runs if (r["n1"] - r["n0"] + args.step) / FPS >= MIN_RUN]
    for r in runs:
        r["t0"], r["t1"] = r["n0"] / FPS, (r["n1"] + args.step) / FPS
    Path("mv/review").mkdir(parents=True, exist_ok=True)
    pages = sheet(runs, W, H)
    print(f"{len(frames)} frames checked: {len(runs)} elements short of contrast for {MIN_RUN} s or more")
    for r in runs:
        b = r["box"]
        print(f"  {r['t0']:6.2f}-{r['t1']:6.2f}s  {r['kind']:10s} at x {b[0]:.2f}-{b[2]:.2f} y {b[1]:.2f}-{b[3]:.2f}"
              f"  worst {r['worst']:.1f}:1 (needs {r['need']}:1)")
    if pages:
        print(f"review: mv/review/contrast_00.jpg .. contrast_{pages - 1:02d}.jpg")
    sys.exit(1 if runs else 0)


if __name__ == "__main__":
    main()
