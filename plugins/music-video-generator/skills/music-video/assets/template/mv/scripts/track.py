"""Track a point through one shot of the edit, so an overlay can be pinned to the footage: a flare on a
street lamp, a word on a wall, sparks off a hand, light rays from a window.

Usage (from the project root, after edl.py):
  .venv/bin/python mv/scripts/track.py --pick --at SONG_TIME
      writes mv/work/tracks/pick_<time>.jpg: the shot's frame at that time as cut, with a 0..1 grid, to
      read X,Y from
  .venv/bin/python mv/scripts/track.py NAME --at SONG_TIME --point X,Y [--radius 0.05]
      follows the texture around X,Y (corners and edges near it) forwards and backwards through the shot
  .venv/bin/python mv/scripts/track.py NAME --at SONG_TIME --bright [--point X,Y] [--radius 0.08]
      follows the brightest small light (near X,Y if given, else the brightest in the frame), re-centring
      on it every frame: lamps, headlights, flames, the sun

X,Y are positions in the shot's frame as cut (0..1 from the top left of the 16:9 segment, before the
EDL's zoom, pan and shake), the same frame --pick shows. Writes mv/data/tracks/NAME.json and a check
sheet mv/work/tracks/NAME.jpg (eight frames with the point marked: green tracked, red lost). Look at the
sheet before using the track.

In fx.py: ov.track(NAME, ctx) gives (x, y) in output pixels, following the shot's zoom, pan and shake,
or None in other shots and where the track was lost; in uniforms(t, a), a["track"](NAME) gives shader uv.
The track belongs to the shot's cut segment: after changing its in-point, speed, ramp or loop, run
track.py again (until then ov.track returns None for that shot).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from motion import seg_time  # noqa: E402
from render import SEG, SH, SW, build_jobs, prep_one  # noqa: E402
from timing import FPS  # noqa: E402

ROOT = Path("mv")


def shot_at(t):
    edl = json.loads((ROOT / "data" / "edl.json").read_text())
    jobs = build_jobs(edl)
    for job, s in jobs:
        if s in edl["main"] and len(job) == 6 and s["start"] <= t < s["start"] + s["dur"]:
            if s["src"] == "BLACK" or s["src"].startswith("GEN_"):
                sys.exit(f"the shot at {t:.2f}s is {s['src']}: nothing to track")
            if not Path(s["file"]).exists():
                SEG.mkdir(parents=True, exist_ok=True)
                prep_one(job)
            if not Path(s["file"]).exists():
                sys.exit(f"could not cut the segment for {s['src']} at {s['start']:.2f}s (see the ffmpeg error above)")
            return s
    sys.exit(f"no shot at {t:.2f}s in mv/data/edl.json")


def frames(path, gray=True):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt",
                          "gray" if gray else "rgb24", "-"], capture_output=True).stdout
    n = SW * SH * (1 if gray else 3)
    k = len(raw) // n
    return np.frombuffer(raw[:k * n], np.uint8).reshape((k, SH, SW) if gray else (k, SH, SW, 3))


def font(size):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)
    except OSError:
        return ImageFont.load_default(size)


def pick(s, t):
    rgb = frames(s["file"], gray=False)
    f0 = min(int(round(seg_time(s, t - s["start"]) * FPS)), len(rgb) - 1)
    im = Image.fromarray(rgb[f0])
    d = ImageDraw.Draw(im)
    fn = font(18)
    for k in range(1, 10):
        x, y = k * SW // 10, k * SH // 10
        d.line((x, 0, x, SH), fill=(0, 255, 120), width=1)
        d.line((0, y, SW, y), fill=(0, 255, 120), width=1)
        d.text((x + 3, 3), f".{k}", fill=(0, 255, 120), font=fn)
        d.text((3, y + 3), f".{k}", fill=(0, 255, 120), font=fn)
    out = ROOT / "work" / "tracks" / f"pick_{t:.2f}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=88)
    print(out)


def track_features(g, f0, p0, radius):
    """Median motion of the corners near p0, forwards and backwards from frame f0."""
    n = len(g)
    pts = np.full((n, 2), np.nan)
    ok = np.zeros(n, bool)
    pts[f0], ok[f0] = p0, True
    lk = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))

    def seed(img, c):
        mask = np.zeros_like(img)
        cv2.circle(mask, (int(c[0]), int(c[1])), int(radius), 255, -1)
        f = cv2.goodFeaturesToTrack(img, 24, 0.01, 4, mask=mask)
        return f.reshape(-1, 2).astype(np.float32) if f is not None else np.array([c], np.float32)

    for step in (1, -1):
        cur = np.array(p0, np.float32)
        feats = seed(g[f0], cur)
        offs = feats - cur
        i = f0
        while 0 <= i + step < n:
            j = i + step
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(g[i], g[j], feats.reshape(-1, 1, 2), None, **lk)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(g[j], g[i], nxt, None, **lk)
            good = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm(back.reshape(-1, 2) - feats, axis=1) < 1.0)
            if good.sum() < min(3, len(feats)):
                break   # lost: leave the rest of this direction unmarked
            nxt = nxt.reshape(-1, 2)
            cur = np.median(nxt[good] - offs[good], axis=0)
            pts[j], ok[j] = cur, True
            feats, offs = nxt[good], offs[good]
            if (j - f0) % 12 == 0 or len(feats) < 6:   # refresh the corners so the track doesn't thin out
                feats = seed(g[j], cur)
                offs = feats - cur
            i = j
    return pts, ok


def track_bright(g, f0, p0, radius):
    """The brightest small light, followed by re-centring on its brightness every frame."""
    n = len(g)
    blur = [cv2.GaussianBlur(x, (0, 0), 3) for x in g]
    pts = np.full((n, 2), np.nan)
    ok = np.zeros(n, bool)

    def peak(img, c, r):
        x0, y0 = int(max(c[0] - r, 0)), int(max(c[1] - r, 0))
        x1, y1 = int(min(c[0] + r, SW)), int(min(c[1] + r, SH))
        win = img[y0:y1, x0:x1]
        _, mx, _, loc = cv2.minMaxLoc(win)
        return np.array([x0 + loc[0], y0 + loc[1]], float), mx

    c, level = peak(blur[f0], p0 if p0 is not None else (SW / 2, SH / 2), radius if p0 is not None else SW)
    pts[f0], ok[f0] = c, True
    for step in (1, -1):
        cur, vel, i = c.copy(), np.zeros(2), f0
        while 0 <= i + step < n:
            j = i + step
            found, mx = peak(blur[j], cur + vel, radius)
            if mx < 0.6 * level:
                break
            vel = 0.6 * vel + 0.4 * (found - cur)
            cur = found
            pts[j], ok[j] = cur, True
            i = j
    return pts, ok


def smooth(pts, ok):
    out = pts.copy()
    for i in range(len(pts)):
        win = [k for k in range(i - 1, i + 2) if 0 <= k < len(pts) and ok[k]]
        if ok[i] and win:
            out[i] = pts[win].mean(0)
    return out


def check_sheet(name, s, pts, ok):
    rgb = frames(s["file"], gray=False)
    idx = np.linspace(0, len(rgb) - 1, 8).round().astype(int)
    sheet = Image.new("RGB", (4 * 480, 2 * 270))
    fn = font(16)
    for k, i in enumerate(idx):
        im = Image.fromarray(rgb[i]).resize((480, 270))
        d = ImageDraw.Draw(im)
        if not np.isnan(pts[i][0]):
            x, y = pts[i][0] * 480 / SW, pts[i][1] * 270 / SH
            col = (0, 255, 90) if ok[i] else (255, 40, 40)
            d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=col, width=3)
        d.text((6, 4), f"{s['start'] + i / FPS:.2f}s", fill=(255, 220, 90), font=fn)
        sheet.paste(im, ((k % 4) * 480, (k // 4) * 270))
    out = ROOT / "work" / "tracks" / f"{name}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--at", type=float, required=True, help="a song time inside the shot")
    ap.add_argument("--point", help="X,Y in the shot's frame, 0..1 from the top left")
    ap.add_argument("--bright", action="store_true", help="follow the brightest small light")
    ap.add_argument("--radius", type=float, help="search radius as a share of the frame width")
    ap.add_argument("--pick", action="store_true", help="write a gridded frame to read X,Y from")
    args = ap.parse_args()
    s = shot_at(args.at)
    if args.pick:
        return pick(s, args.at)
    if not args.name or not (args.point or args.bright):
        sys.exit("give a NAME and --point X,Y or --bright (or --pick to read X,Y from a frame)")
    g = frames(s["file"])
    if not len(g):
        sys.exit(f"no frames in {s['file']}")
    f0 = min(int(round(seg_time(s, args.at - s["start"]) * FPS)), len(g) - 1)
    p0 = None
    if args.point:
        x, y = (float(v) for v in args.point.split(","))
        p0 = np.array([x * SW, y * SH])
    if args.bright:
        pts, ok = track_bright(g, f0, p0, (args.radius or 0.08) * SW)
    else:
        pts, ok = track_features(g, f0, p0, (args.radius or 0.05) * SW)
    pts = smooth(pts, ok)
    data = {"name": args.name, "src": s["src"], "start": s["start"], "file": Path(s["file"]).name, "fps": FPS,
            "points": [[round(float(p[0]) / SW, 5), round(float(p[1]) / SH, 5), int(k)] if k else [0.5, 0.5, 0]
                       for p, k in zip(pts, ok)]}
    out = ROOT / "data" / "tracks" / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data))
    sheet = check_sheet(args.name, s, pts, ok)
    print(f"{out}: {int(ok.sum())} of {len(ok)} frames tracked "
          f"({s['src']} at {s['start']:.2f}s, {s['dur']:.2f}s)\ncheck: {sheet}")


if __name__ == "__main__":
    main()
