"""Mouth crops over time, for seeing where a performer's mouth moves in a clip.

Usage: .venv/bin/python mv/scripts/mouth_check.py OUT.jpg CODE:T0-T1 [CODE:T0-T1 ...] [--fps 5]
CODE is an AI clip or a code from mv/data/codes.json; T0-T1 is a range in clip seconds. Writes one
row per range (ten crops per row), each crop labeled with its clip time. Use it to find the stretches
where a lipsync take keeps mouthing between lines, or where the user's own performer footage shows
speech, and record the mouth-safe ranges in mv/data/mouths.json.

Faces come from OpenCV's Haar cascades (frontal and profile, both directions). When detection fails
the last face box is reused; a backlit profile is often not detected at all, so check those by eye.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from media import src_path  # noqa: E402

CW, CH, PER_ROW = 200, 150, 10
CASCADES = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
            ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]


def face_box(gray):
    best = None
    for c in CASCADES:
        for flip in (False, True):
            g = cv2.flip(gray, 1) if flip else gray
            for (x, y, w, h) in c.detectMultiScale(g, 1.1, 5, minSize=(gray.shape[0] // 8, gray.shape[0] // 8)):
                if flip:
                    x = gray.shape[1] - x - w
                if best is None or w * h > best[2] * best[3]:
                    best = (x, y, w, h)
    return best


def crops(code, t0, t1, fps):
    cap = cv2.VideoCapture(str(src_path(code)))
    vfps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    tiles, last = [], None
    for t in np.arange(t0, t1, 1 / fps):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * vfps)))
        ok, frame = cap.read()
        if not ok:
            break
        box = face_box(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)) or last
        last = box
        if box is None:
            crop = np.zeros((CH, CW, 3), np.uint8)
        else:
            x, y, w, h = box
            y0, y1 = int(y + 0.55 * h), int(y + 1.05 * h)
            x0, x1 = int(x + 0.15 * w), int(x + 0.85 * w)
            crop = cv2.resize(frame[max(0, y0):y1, max(0, x0):x1], (CW, CH))
        cv2.putText(crop, f"{t:.1f}", (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        tiles.append(crop)
    return tiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("ranges", nargs="+", help="CODE:T0-T1")
    ap.add_argument("--fps", type=float, default=5.0, help="crops per second (4-6 shows mouth shapes)")
    args = ap.parse_args()
    rows = []
    for spec in args.ranges:
        code, rng = spec.split(":")
        t0, t1 = map(float, rng.split("-"))
        tiles = crops(code, t0, t1, args.fps)
        if not tiles:
            print(f"{spec}: no frames")
            continue
        label = np.zeros((CH, 130, 3), np.uint8)
        cv2.putText(label, spec, (2, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        for k in range(0, len(tiles), PER_ROW):
            chunk = tiles[k:k + PER_ROW]
            chunk += [np.zeros_like(chunk[0])] * (PER_ROW - len(chunk))
            rows.append(np.hstack([label] + chunk))
    if not rows:
        sys.exit("nothing to write")
    cv2.imwrite(args.out, np.vstack(rows))
    print(args.out)


if __name__ == "__main__":
    main()
