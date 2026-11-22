"""Put a picture or a video on a tracked screen (track_screen.py), as a new clip the edit can use.

Usage: .venv/bin/python mv/scripts/bake_screen.py CODE --panel PANEL [--out NEWCODE] [--from SECONDS]
                                                  [--inset 0.94] [--glow 0.35]

PANEL is an image (png, jpg) or a video (mp4, mov). It is warped onto the screen's corners from
mv/data/screen_CODE.json on every frame of mv/clips/CODE.mp4, so it turns, shrinks and leans with the
screen. A video panel plays from --from seconds into it, one panel frame per clip frame, and holds its last
frame if it runs out. --inset pulls the panel in from the tracked edge (0.94 keeps the screen's own frame
showing around it); --glow adds the panel's light around it, as a lit screen spills onto its frame.

Writes mv/clips/NEWCODE.mp4 (default CODE + "s"), and copies CODE_matte.mp4 and CODE_depth.mp4 to
NEWCODE's names when they exist (the screen isn't a person). Use NEWCODE in the EDL like any clip.

When the screen shows something tied to the song (a countdown, the line being sung), make the panel per
shot: render a panel video for the song time the shot plays at, bake one copy per shot (--out with the
shot's start in the name, e.g. W1s1742), and point each shot at its own copy.
"""
import argparse
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS  # noqa: E402

CLIPS = Path("mv/clips")


def size_of(path):
    v = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    return int(v[0]), int(v[1])


def reader(path, skip=0, hold=False):
    w, h = size_of(path)
    dec = subprocess.Popen(["ffmpeg", "-v", "quiet", "-ss", f"{skip:.3f}", "-i", str(path), "-vf", f"fps={FPS}",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    last = None
    while True:
        buf = dec.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        last = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        yield last
    dec.wait()
    while hold and last is not None:   # a panel that runs out holds its last frame
        yield last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--out")
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    ap.add_argument("--inset", type=float, default=0.94)
    ap.add_argument("--glow", type=float, default=0.35)
    args = ap.parse_args()
    src = CLIPS / f"{args.code}.mp4"
    track = Path(f"mv/data/screen_{args.code}.json")
    if not src.exists() or not track.exists():
        sys.exit(f"needs {src} and {track} (track_screen.py)")
    quads = json.loads(track.read_text())["quads"]
    out = args.out or args.code + "s"
    w, h = size_of(src)
    panel = Path(args.panel)
    if panel.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        img = cv2.imread(str(panel), cv2.IMREAD_COLOR)
        if img is None:
            sys.exit(f"can't read {panel}")
        panels = itertools.repeat(img)
    else:
        panels = reader(panel, args.start, hold=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "13", "-pix_fmt", "yuv420p",
                            str(CLIPS / f"{out}.mp4")], stdin=subprocess.PIPE)
    n = 0
    for frame, pan in zip(reader(src), panels):
        if n >= len(quads):
            break
        ph, pw = pan.shape[:2]
        q = np.array(quads[n], np.float32) * [w, h]
        c = q.mean(0)
        q = (c + (q - c) * args.inset).astype(np.float32)
        H = cv2.getPerspectiveTransform(np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]]), q)
        warped = cv2.warpPerspective(pan, H, (w, h), flags=cv2.INTER_AREA).astype(np.float32)
        mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), H, (w, h))
        mask = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32)[..., None] / 255
        f = frame.astype(np.float32) * (1 - mask) + warped * mask
        if args.glow > 0:
            f += cv2.GaussianBlur(warped, (0, 0), max(2.0, 0.01 * w)) * args.glow
        enc.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    made = [f"{out}.mp4"]
    for suffix in ("_matte", "_depth"):
        extra = CLIPS / f"{args.code}{suffix}.mp4"
        if extra.exists():
            shutil.copyfile(extra, CLIPS / f"{out}{suffix}.mp4")
            made.append(f"{out}{suffix}.mp4")
    print(f"{n} frames -> mv/clips/{', '.join(made)}")


if __name__ == "__main__":
    main()
