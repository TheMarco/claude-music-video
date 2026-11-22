"""A screen in the shot that shows this video's own picture: an LED wall on a tower, a billboard, a
monitor, a phone. The screen is tracked through its clip once, and fx.py draws what it shows per frame,
keyed to song time, so a countdown, a score or a line reads right in every shot of it.

Usage:
  .venv/bin/python mv/scripts/screen.py CODE [--at X,Y] [--dark 26]
      Tracks the dark, blank screen in the source CODE (an AI clip or any code in codes.json) and writes
      mv/data/screen_<CODE>.json and a check sheet, mv/review/screen_<CODE>.jpg: 12 frames with the
      tracked outline drawn green where the track holds and red where it doesn't. Look at the sheet
      before using the track, and keep the shots' in-points inside the span it prints.
      --at X,Y   (0..1 of the frame) the screen nearest this point; default: the biggest dark rectangle
                 in the middle half of the frame
      --dark N   luma 0..255 below which a pixel counts as screen (raise it for a grey screen)

The method (from "Tomorrow Just Dropped", where a gold LED countdown ran on a tower's screen): per frame
the screen's top edge and its two side edges are fitted as lines on the dark region's boundary; the bottom
corners are placed along the side edges at the height measured on the first frame that shows the whole
screen, scaled by the top edge's width, because the bottom is the edge that gets clipped by the frame or
merges with dark ground; each corner's path is then smoothed with
a cubic over the clip. Fitting edges instead of a rotated box keeps the panel turning with the building.
A cubic assumes one smooth camera move (an orbit, a push-in, a slow pan), which is what the clip should
be. Frames where the measured screen strays from the smooth path (something passes in front, the AI
morphs the building) are marked not ok.

In edl.py, give each shot of that source screen="NAME"; fx.SCREENS["NAME"](t, shot) returns the picture
for song time t (an RGB numpy array or a PIL image, any size, in the screen's aspect). render.py warps it
onto the screen in every frame it reads, following the shot's in-point, speed and crop, with a soft glow
around it; bloom and the grade then treat it like the rest of the picture. Per-shot screen_inset=0.94
pulls the picture in from the tracked edges so the screen's frame shows; screen_glow=0.35 sets the glow.
Reversed shots (rev=True) are left plain.

led_panel(lines, ...) draws an LED dot-matrix panel for fx.SCREENS: each letter on its own, one dark
dot column between letters and three between words, so letters never run together.
"""
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from media import crop_for, src_path  # noqa: E402

ROOT = Path("mv")
FPS = 24
STRAY = 0.012   # a frame is not ok when a measured corner is further than this (frame widths) from the path


def _measure(frame, dark, prev_c, at):
    """(top-left, top-right, left slope, right slope, bottom corners or None, centroid) of the screen, or
    None. The bottom corners are measured only when the screen's lowest pixel is inside the frame."""
    h, w = frame.shape[:2]
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    m = cv2.morphologyEx((g < dark).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m)
    ref = prev_c if prev_c is not None else (np.array(at) * [w, h] if at is not None else None)
    best = None
    for i in range(1, n):
        bw, area = stats[i][2], stats[i][4]
        cx, cy = cents[i]
        if area < 0.004 * w * h or bw > (0.9 if at is not None else 0.45) * w:
            continue
        if at is None and not (0.25 * w < cx < 0.75 * w):
            continue
        d = 0.0 if ref is None else float(np.hypot(cx - ref[0], cy - ref[1]))
        sc = area / (1 + d / 20)
        if best is None or sc > best[0]:
            best = (sc, i)
    if best is None:
        return None
    i = best[1]
    ys, xs = np.nonzero(lab == i)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    L, R, T, B = [], [], [], []
    for yy in range(int(y0 + 0.12 * (y1 - y0)), int(y1 - 0.12 * (y1 - y0)) + 1):
        row = xs[ys == yy]
        if row.size:
            L.append((yy, row.min()))
            R.append((yy, row.max()))
    for xx in range(int(x0 + 0.15 * (x1 - x0)), int(x1 - 0.15 * (x1 - x0)) + 1):
        col = ys[xs == xx]
        if col.size:
            T.append((xx, col.min()))
            B.append((xx, col.max()))
    if min(len(L), len(T)) < 8:
        return None
    L, R, T, B = (np.array(v, float) for v in (L, R, T, B))
    la, lb = np.polyfit(L[:, 0], L[:, 1], 1)                # x = la*y + lb
    ra, rb = np.polyfit(R[:, 0], R[:, 1], 1)
    ta, tb = np.polyfit(T[:, 0], T[:, 1], 1)                # y = ta*x + tb
    ba, bb = np.polyfit(B[:, 0], B[:, 1], 1)

    def meet(ya, yb, a, b):                                  # a line y = ya*x + yb with a side line
        y = (ya * b + yb) / (1 - ya * a)
        return np.array([a * y + b, y])
    bottom = None if y1 >= h - 3 else (meet(ba, bb, la, lb), meet(ba, bb, ra, rb))
    return meet(ta, tb, la, lb), meet(ta, tb, ra, rb), la, ra, bottom, cents[i]


def track(code, at=None, dark=26):
    cap = cv2.VideoCapture(str(src_path(code)))
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    rows, frames, prev_c = [], [], None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
        r = _measure(f, dark, prev_c, at)
        if r is not None:
            prev_c = r[5]
        rows.append(r)
    if not frames:
        sys.exit(f"{code}: no frames read from {src_path(code)}")
    h, w = frames[0].shape[:2]
    found = np.array([r is not None for r in rows])
    if found.sum() < 4:
        sys.exit(f"{code}: no dark screen found (found in {found.sum()} frames); try --at X,Y or a higher --dark")
    first = next((r for r in rows if r is not None and r[4] is not None), next(r for r in rows if r is not None))
    if first[4] is not None:                                 # the side length, from the fitted bottom edge
        H0 = (np.linalg.norm(first[4][0] - first[0]) + np.linalg.norm(first[4][1] - first[1])) / 2
    else:                                                    # clipped in every frame: down to the frame edge
        H0 = h - 1 - (first[0][1] + first[1][1]) / 2
    W0 = np.linalg.norm(first[1] - first[0])
    raw = np.zeros((len(rows), 4, 2))
    for k, r in enumerate(rows):
        if r is None:
            continue
        tl, tr, la, ra = r[:4]
        Lh = H0 * np.linalg.norm(tr - tl) / W0
        dl = np.array([la, 1.0]) / np.hypot(la, 1.0)
        dr = np.array([ra, 1.0]) / np.hypot(ra, 1.0)
        raw[k] = [tl, tr, tr + dr * Lh, tl + dl * Lh]
    t = np.arange(len(rows))
    deg = min(3, int(found.sum()) - 1)
    smooth = np.zeros_like(raw)
    for c in range(4):
        for j in range(2):
            smooth[:, c, j] = np.polyval(np.polyfit(t[found], raw[found, c, j], deg), t)
    err = np.where(found, np.linalg.norm(raw - smooth, axis=2).max(1), np.inf)
    good = err < STRAY * w
    out = ROOT / "data" / f"screen_{code}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"fps": fps, "size": [w, h], "quads": (smooth / [w, h]).round(5).tolist(),
               "found": found.tolist(), "ok": good.tolist(),
               "err": [round(float(e), 1) if np.isfinite(e) else None for e in err],
               "method": "edges+cubic"}, open(out, "w"))
    a, b = _longest_run(good)
    print(f"{code}: screen found in {found.sum()}/{len(rows)} frames; track holds {good.sum()} frames, "
          f"longest run {a}-{b} = {a / fps:.2f}-{(b + 1) / fps:.2f} s of the source. Keep in-points and "
          f"shot ends inside it. Wrote {out}")
    sheet(code, frames, smooth, good, err, fps)
    return out


def _longest_run(mask):
    best, start = (0, -1), None
    for k, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = k
        elif not v and start is not None:
            if k - start > best[1] - best[0] + 1:
                best = (start, k - 1)
            start = None
    return best


def sheet(code, frames, quads, good, err, fps, n=12, tw=480):
    h, w = frames[0].shape[:2]
    th = int(round(tw * h / w))
    idx = np.linspace(0, len(frames) - 1, min(n, len(frames))).round().astype(int)
    cols = 4
    img = np.zeros((th * ((len(idx) + cols - 1) // cols), tw * cols, 3), np.uint8)
    for k, i in enumerate(idx):
        f = frames[i].copy()
        col = (60, 220, 60) if good[i] else (40, 40, 230)
        cv2.polylines(f, [quads[i].round().astype(np.int32)], True, col, max(2, w // 480), cv2.LINE_AA)
        f = cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA)
        e = "lost" if not np.isfinite(err[i]) else f"{err[i]:.0f}px"
        cv2.putText(f, f"f{i} {i / fps:.2f}s {e}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
                    cv2.LINE_AA)
        img[(k // cols) * th:(k // cols + 1) * th, (k % cols) * tw:(k % cols + 1) * tw] = f
    out = ROOT / "review" / f"screen_{code}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("check sheet:", out)


# ---------------------------------------------------------------- compositing (called by render.py)

_TRACKS, _WARNED = {}, set()


def _warn(key, msg):
    if key not in _WARNED:
        _WARNED.add(key)
        print("screen:", msg)


def _track(code):
    if code not in _TRACKS:
        p = ROOT / "data" / f"screen_{code}.json"
        _TRACKS[code] = json.loads(p.read_text()) if p.exists() else None
    return _TRACKS[code]


def quad_at(seg, k, size):
    """The screen's corners (4x2, segment pixels) in frame k of the shot's segment, or None."""
    tr = _track(seg["src"])
    if tr is None:
        _warn(seg["src"], f"no mv/data/screen_{seg['src']}.json; run screen.py {seg['src']} (shot left plain)")
        return None
    if seg.get("rev"):
        _warn(("rev", seg["src"]), f"{seg['src']}: reversed shots are left plain")
        return None
    q = np.array(tr["quads"], np.float64)
    ft = (seg["in"] + k / FPS * seg.get("speed", 1.0)) * tr["fps"]
    i = int(np.clip(np.floor(ft), 0, len(q) - 1))
    j, u = min(i + 1, len(q) - 1), float(np.clip(ft - i, 0.0, 1.0))
    qq = q[i] * (1 - u) + q[j] * u
    x, y, w, h = crop_for(seg["src"])
    return (qq - [x, y]) / [w, h] * size


def composite(buf, seg, k, draws, size):
    """buf (RGB bytes of segment frame k) with the shot's screen filled by draws[seg["screen"]]."""
    name = seg["screen"]
    draw = draws.get(name)
    if draw is None:
        _warn(name, f'fx.SCREENS has no "{name}" (shot left plain)')
        return buf
    q = quad_at(seg, k, size)
    if q is None:
        return buf
    pic = draw(seg["start"] + k / FPS, seg)
    if pic is None:
        return buf
    pic = np.asarray(pic.convert("RGB")) if hasattr(pic, "convert") else np.ascontiguousarray(np.asarray(pic)[..., :3])
    ph, pw = pic.shape[:2]
    c = q.mean(0)
    q = c + (q - c) * seg.get("screen_inset", 0.94)
    sw, sh = size
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]]), q.astype(np.float32))
    warped = cv2.warpPerspective(pic, H, (sw, sh), flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), H, (sw, sh))
    mask = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32)[..., None] / 255
    glow = cv2.GaussianBlur(warped, (0, 0), 6).astype(np.float32)
    f = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3).astype(np.float32)
    f = f * (1 - mask) + warped.astype(np.float32) * mask + glow * seg.get("screen_glow", 0.35)
    return np.clip(f, 0, 255).astype(np.uint8).tobytes()


# ---------------------------------------------------------------- LED dot-matrix panels

LED_FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


@lru_cache(maxsize=256)
def led_mask(text, cells, font=LED_FONT):
    """text as a 0/1 dot grid `cells` dots high: each letter on its own, one dark column of dots between
    letters and three between words."""
    from overlay import font_path
    f = ImageFont.truetype(font_path(font), 160)
    cap = -f.getbbox("H", anchor="ls")[1]
    scale = cells / cap
    cols = []
    for ch in text:
        if ch == " ":
            cols.append(Image.new("L", (3, cells), 0))
            continue
        bb = f.getbbox(ch, anchor="ls")
        w = max(1, bb[2] - bb[0])
        g = Image.new("L", (w + 4, cap + 4), 0)
        ImageDraw.Draw(g).text((2 - bb[0], cap + 2), ch, font=f, fill=255, anchor="ls")
        g = g.crop((0, 2, w + 4, cap + 2)).resize((max(1, int(round(w * scale))), cells), Image.BOX)
        g = g.point(lambda v: 255 if v > 110 else 0)
        gb = g.getbbox()
        if gb:
            g = g.crop((gb[0], 0, gb[2], cells))
        cols.append(g)
        cols.append(Image.new("L", (1, cells), 0))
    W = sum(c.size[0] for c in cols)
    m = Image.new("L", (max(1, W), cells), 0)
    x = 0
    for c in cols:
        m.paste(c, (x, 0))
        x += c.size[0]
    return np.array(m.crop((0, 0, max(1, W - 1), cells))) > 0


def led_panel(lines, size=(520, 600), color=(255, 200, 96), font=LED_FONT):
    """An LED panel picture for fx.SCREENS. lines [(text, cells), ...] are stacked top to bottom, each in
    a band of the panel's height in proportion to its cells, each at the biggest dot size that fits its
    band and 90% of the width; lit dots have a halo, unlit dots of each line's grid stay dim. Words read
    from 7 cells; a number or a word that carries the line wants 11-15."""
    pw, ph = size
    img = np.zeros((ph, pw, 3), np.uint8)
    halo = tuple(int(v * 0.47) for v in color)
    off = tuple(int(8 + v * 0.06) for v in color)
    total = sum(cells for _, cells in lines)
    top = 0.0
    for text, cells in lines:
        band = ph * cells / total
        m = led_mask(text, cells, font)
        rows_n, cols_n = m.shape
        pitch = min(pw * 0.9 / cols_n, band * 0.78 / rows_n)
        x0, y0 = (pw - cols_n * pitch) / 2, top + (band - rows_n * pitch) / 2
        for cy in range(rows_n):
            for cx in range(cols_n):
                p = (int(x0 + (cx + 0.5) * pitch), int(y0 + (cy + 0.5) * pitch))
                if m[cy, cx]:
                    cv2.circle(img, p, max(1, int(pitch * 0.62)), halo, -1, cv2.LINE_AA)
                    cv2.circle(img, p, max(1, int(pitch * 0.38)), color, -1, cv2.LINE_AA)
                else:
                    cv2.circle(img, p, max(1, int(pitch * 0.22)), off, -1, cv2.LINE_AA)
        top += band
    return img


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("code")
    ap.add_argument("--at", help="X,Y in 0..1 of the frame: the screen nearest this point")
    ap.add_argument("--dark", type=int, default=26)
    a = ap.parse_args()
    track(a.code, at=tuple(float(v) for v in a.at.split(",")) if a.at else None, dark=a.dark)
