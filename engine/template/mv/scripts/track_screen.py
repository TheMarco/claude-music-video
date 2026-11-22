"""Track a screen, sign or window in a clip, so something can be shown on it (bake_screen.py).

Usage: .venv/bin/python mv/scripts/track_screen.py CODE --quad X0,Y0,X1,Y1,X2,Y2,X3,Y3 [--smooth 0.5|clip]

--quad gives the screen's corners on the clip's first frame, clockwise from top left, as 0..1 of the
frame (read them off a still with a 0.1 grid). The screen has to stand apart from its surroundings in
brightness: a dark screen on a lit building, a lit sign on a dark wall.

Each frame, the screen's region is found where it was on the frame before, and each of its four edges is
fitted as a straight line to the region's outline; the corners are where the lines meet. An edge that
can't be seen (cut by the frame edge, hidden behind someone) is carried from the frame before, moved with
the edges that can. That follows the screen's own outline, so whatever is put on it turns exactly as much
as the building does. Tracking feature points inside or around the screen instead (a homography) drifted
on a drone shot of a tower and turned the inserted panel more than the building. The corners are then
smoothed over time: --smooth 0.5 (seconds, the default) for a handheld or shaky shot, --smooth clip for
one smooth camera move, which fits each corner's path with one cubic over the whole clip.

Writes mv/data/screen_CODE.json ({"fps", "quads": per frame [[x, y] x 4] in 0..1, "seen": edges found per
frame}) and mv/review/screen_CODE.jpg (frames every 0.5 s with the tracked corners), which you check
before baking: the outline should sit on the screen's edge on every frame.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS  # noqa: E402


def frames(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    dec = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           stdout=subprocess.PIPE)
    while True:
        buf = dec.stdout.read(w * h)
        if len(buf) < w * h:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w)
    dec.wait()


def poly_mask(q, shape, grow=0):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(q).astype(np.int32)], 1)
    if grow > 0:
        m = cv2.dilate(m, np.ones((2 * grow + 1, 2 * grow + 1), np.uint8))
    return m


def meet(l1, l2):
    """Intersection of two lines given as (point, direction)."""
    (p, d), (r, e) = l1, l2
    a = np.array([[d[0], -e[0]], [d[1], -e[1]]])
    if abs(np.linalg.det(a)) < 1e-9:
        return None
    t = np.linalg.solve(a, r - p)
    return p + t[0] * d


def side_line(q, j):
    a, b = q[j], q[(j + 1) % 4]
    d = (b - a) / (np.linalg.norm(b - a) + 1e-9)
    return a, d


def track(path, q0, h, w):
    thr = dark = None
    prev = q0.copy()
    out, seen = [], []
    for n, g in enumerate(frames(path)):
        size = min(np.linalg.norm(prev[1] - prev[0]), np.linalg.norm(prev[3] - prev[0]))
        band = max(3, int(0.08 * size))
        if thr is None:   # the screen's brightness against a ring around it, from the first frame
            inside = g[poly_mask(prev, g.shape) > 0]
            ring = g[(poly_mask(prev, g.shape, grow=band * 2) - poly_mask(prev, g.shape)) > 0]
            li, lo = float(np.median(inside)), float(np.median(ring))
            dark, thr = li < lo, (li + lo) / 2
        m = ((g < thr) if dark else (g > thr)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        m &= poly_mask(prev, g.shape, grow=int(band * 1.5))    # keep it from leaking into a dark sky or wall
        cnt, lab = cv2.connectedComponents(m)
        inside = poly_mask(prev, g.shape)
        best, best_n = 0, 0
        for i in range(1, cnt):
            k = int(((lab == i) & (inside > 0)).sum())
            if k > best_n:
                best, best_n = i, k
        if best == 0 or best_n < 0.3 * inside.sum():
            out.append(prev.copy())
            seen.append(0)
            continue
        comp = (lab == best).astype(np.uint8)
        cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        pts = np.vstack([c.reshape(-1, 2) for c in cs]).astype(float)
        pts = pts[(pts[:, 0] > 2) & (pts[:, 0] < w - 3) & (pts[:, 1] > 2) & (pts[:, 1] < h - 3)]   # not the frame edge
        lines = [None] * 4
        for j in range(4):
            a, d = side_line(prev, j)
            L = np.linalg.norm(prev[(j + 1) % 4] - prev[j])
            rel = pts - a
            along = rel @ d
            across = np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0])
            near = pts[(across < band) & (along > 0.1 * L) & (along < 0.9 * L)]
            if len(near) >= max(12, 0.25 * L):
                vx, vy, x0, y0 = cv2.fitLine(near.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
                dd = np.array([vx, vy])
                lines[j] = (np.array([x0, y0]), dd if dd @ d > 0 else -dd)
        found = [j for j in range(4) if lines[j] is not None]
        corners = {}
        for j in range(4):   # corner j sits between side j-1 and side j
            if lines[j - 1] is not None and lines[j] is not None:
                c = meet(lines[j - 1], lines[j])
                if c is not None:
                    corners[j] = c
        if len(corners) >= 2:   # move last frame's quad with the corners that are seen
            k = sorted(corners)
            M, _ = cv2.estimateAffinePartial2D(prev[k].astype(np.float32), np.array([corners[i] for i in k], np.float32))
            guess = cv2.transform(prev[None].astype(np.float32), M)[0].astype(float) if M is not None else prev.copy()
        else:
            guess = prev.copy()
        for j in range(4):
            if lines[j] is None:
                lines[j] = side_line(guess, j)
        q = np.array([meet(lines[j - 1], lines[j]) if meet(lines[j - 1], lines[j]) is not None else guess[j]
                      for j in range(4)])
        if not np.all(np.isfinite(q)) or abs(cv2.contourArea(q.astype(np.float32))) < 0.2 * abs(
                cv2.contourArea(prev.astype(np.float32))):
            q = guess
        out.append(q)
        seen.append(len(found))
        prev = q
    return np.array(out), seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--quad", required=True, help="x0,y0,x1,y1,x2,y2,x3,y3 clockwise from top left, 0..1 of frame 0")
    ap.add_argument("--smooth", default="0.5", help="seconds, or 'clip' for one cubic over the whole clip")
    args = ap.parse_args()
    path = Path("mv/clips") / f"{args.code}.mp4"
    if not path.exists():
        sys.exit(f"no {path}")
    first = next(frames(path))
    h, w = first.shape
    v = [float(x) for x in args.quad.split(",")]
    if len(v) != 8:
        sys.exit("--quad needs 8 numbers")
    q0 = np.array(v).reshape(4, 2) * [w, h]
    Q, seen = track(path, q0, h, w)
    t = np.arange(len(Q))
    if args.smooth == "clip":
        S = np.stack([np.stack([np.polyval(np.polyfit(t, Q[:, k, j], 3), t) for j in range(2)], -1) for k in range(4)], 1)
    else:
        win = max(5, int(float(args.smooth) * FPS) | 1)
        S = savgol_filter(Q, min(win, len(Q) - (1 - len(Q) % 2)), 2, axis=0) if len(Q) >= 5 else Q
    S = S / [w, h]
    Path("mv/data").mkdir(parents=True, exist_ok=True)
    Path(f"mv/data/screen_{args.code}.json").write_text(json.dumps(
        {"fps": FPS, "size": [w, h], "quads": S.round(5).tolist(), "seen": seen}))
    tiles = []
    for n, g in enumerate(frames(path)):
        if n % max(1, FPS // 2):
            continue
        im = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        cv2.polylines(im, [np.round(S[n] * [w, h]).astype(np.int32)], True, (40, 40, 255), max(2, w // 400))
        cv2.putText(im, f"{n / FPS:.1f}s  edges seen {seen[n]}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2)
        tiles.append(cv2.resize(im, (480, int(480 * h / w))))
    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    Path("mv/review").mkdir(parents=True, exist_ok=True)
    cv2.imwrite(f"mv/review/screen_{args.code}.jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
    low = sum(1 for s in seen if s < 2)
    print(f"{args.code}: {len(Q)} frames tracked -> mv/data/screen_{args.code}.json; check mv/review/screen_{args.code}.jpg"
          + (f"; {low} frames with fewer than 2 edges seen (held from the frame before)" if low else ""))


if __name__ == "__main__":
    main()
