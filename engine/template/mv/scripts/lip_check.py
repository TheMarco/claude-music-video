"""Measure a source's picture/audio offset ("av_offset") from the singer's lips, and check lip sync.

Usage:
  .venv/bin/python mv/scripts/lip_check.py CODE SONG_TIME [SONG_TIME ...] [--span 2.5] [--sync S]
  .venv/bin/python mv/scripts/lip_check.py CODE --save OFFSET

For lipsync takes and the user's own performance footage, when a mouth looks off. A source's picture can
run ahead of or behind its own sound after downloads and re-encodes. Set an offset only when the user
sees the source itself play out of sync: an existing music video that plays in sync for the user is
placed with sync=0 and needs none. Whisper's word timings on sung vocals can be a third of a second off,
so read these strips as a guide, not proof.

For each SONG_TIME it transcribes 8 s of the song around it with Whisper (word timings are more
reliable on a short slice than on the whole song) and writes mv/work/lips_<CODE>_<time>.jpg: every
frame of the source around that moment as a mouth crop, labelled with the clip time, the song time the
frame plays at with the current sync and av_offset, and the word being sung at that song time. Words
that start with m, b or p are in capitals: the lips close at their start.

  offset = song time of the word's start - song time label of the frames where the lips close

Positive means the picture runs ahead (the mouth moves before the sound). Add it to the current
av_offset, save the sum with --save, and run again: the lips should now close on the m, b and p words.
Check three points (start, middle, end of the song) on lit, frontal close-ups, and confirm with the user
watching the source. A constant offset is a property of the file; one that changes along the song is
drift, and drifting stretches need their own sync per shot. Automatic mouth-to-vocal correlation is
unreliable on soft or stylized footage.

--save writes "av_offset" under the source's file name in mv/data/mouths.json, so every code that crops
the same file gets it; edl.py applies it to every shot with sync=.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from media import src_path  # noqa: E402
from mouth_check import CASCADES  # noqa: E402

MFILE = Path("mv/data/mouths.json")
CW, CH, PER_ROW = 200, 170, 10


def mouths():
    return json.loads(MFILE.read_text()) if MFILE.exists() else {}


def entry(code, m):
    """The source's mouths.json entry: its file-name entry merged with its code entry."""
    return {**m.get(src_path(code).name, {}), **m.get(code, {})}


def words_around(song, t, half=4.0):
    a = max(0.0, t - half)
    wav = Path("mv/work") / f"lipslice_{t:.2f}.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{2 * half:.3f}", "-i", song,
                    "-ac", "1", "-ar", "16000", str(wav)], check=True)
    opts = dict(word_timestamps=True, language="en", condition_on_previous_text=False)
    try:
        import mlx_whisper
        from models import whisper_dir
        r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=str(whisper_dir()), **opts)
    except ImportError:
        import whisper
        r = whisper.load_model("turbo").transcribe(str(wav), **opts)
    return [dict(w=w["word"].strip(), start=a + w["start"], end=a + w["end"])
            for s in r["segments"] for w in s.get("words", [])]


def follow_face(gray, last):
    """The face nearest the previous one (frontal first, then profiles), so a head turn or a false
    detection elsewhere in the frame doesn't throw the mouth crop off."""
    cands = []
    for i, c in enumerate(CASCADES):
        for flip in (False, True):
            g = cv2.flip(gray, 1) if flip else gray
            for (x, y, w, h) in c.detectMultiScale(g, 1.1, 5, minSize=(gray.shape[0] // 8, gray.shape[0] // 8)):
                cands.append((gray.shape[1] - x - w if flip else x, y, w, h, i))
        if cands and i == 0:
            break
    if not cands:
        return None
    if last is None:
        return max(cands, key=lambda b: b[2] * b[3])[:4]
    lx, ly, lw, lh = last
    near = lambda b: abs(b[0] + b[2] / 2 - lx - lw / 2) + abs(b[1] + b[3] / 2 - ly - lh / 2) + abs(b[2] - lw)
    best = min(cands, key=near)
    return best[:4] if near(best) < 1.5 * lw else None


def strip(code, t, span, sync, off, words, out):
    cap = cv2.VideoCapture(str(src_path(code)))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    c0 = t - span / 2 - sync - off
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(max(0.0, c0) * fps)))
    frames, boxes, last = [], [], None
    for _ in range(int(span * fps)):
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(fr)
        box = follow_face(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), last)
        boxes.append(box)
        last = box or last
    found = [i for i, b in enumerate(boxes) if b is not None]
    if not found:
        print(f"  no face found around clip time {c0:.2f}s: pick a close-up")
        return
    B = np.array([boxes[i] for i in found], float)
    steady = np.stack([np.interp(np.arange(len(boxes)), found, B[:, k]) for k in range(4)], 1)
    k = 9 if len(steady) >= 9 else 1
    steady = np.array([np.median(steady[max(0, i - k // 2):i + k // 2 + 1], 0) for i in range(len(steady))]).astype(int)
    tiles = []
    for i, (fr, (x, y, w, h)) in enumerate(zip(frames, steady)):
        clip_t = max(0.0, c0) + i / fps
        song_t = clip_t + sync + off
        crop = fr[max(0, y + int(0.5 * h)):y + int(1.1 * h), max(0, x + int(0.1 * w)):x + int(0.9 * w)]
        crop = cv2.resize(crop, (CW, CH))
        w_now = next((wd["w"] for wd in words if wd["start"] <= song_t < wd["end"]), "")
        if w_now[:1].lower() in "mbp" and w_now:
            w_now = w_now.upper()
        for j, txt in enumerate((f"c {clip_t:.2f}", f"s {song_t:.2f}", w_now)):
            cv2.putText(crop, txt, (4, 16 + 17 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
            cv2.putText(crop, txt, (4, 16 + 17 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        tiles.append(crop)
    tiles += [np.zeros_like(tiles[0])] * ((-len(tiles)) % PER_ROW)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[r:r + PER_ROW]) for r in range(0, len(tiles), PER_ROW)]))
    print(f"  {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("times", nargs="*", type=float, help="song times of sung words on screen")
    ap.add_argument("--span", type=float, default=2.5, help="seconds of frames per strip")
    ap.add_argument("--sync", type=float, default=None, help="song time where the source's audio starts "
                    "(default: mouths.json, else 0 for a video cut against its own soundtrack)")
    ap.add_argument("--save", type=float, default=None, help="record this av_offset for the source")
    args = ap.parse_args()
    m = mouths()
    name = src_path(args.code).name
    if args.save is not None:
        m.setdefault(name, {})["av_offset"] = round(args.save, 3)
        MFILE.parent.mkdir(parents=True, exist_ok=True)
        MFILE.write_text(json.dumps(m, indent=1))
        print(f"saved av_offset {args.save:.3f} for {name} in {MFILE}; rerun edl.py")
        return
    if not args.times:
        sys.exit("give one or more song times, or --save OFFSET")
    e = entry(args.code, m)
    sync = args.sync if args.sync is not None else float(e.get("sync", 0.0))
    off = float(e.get("av_offset", 0.0))
    song = json.loads(Path("mv/data/song.json").read_text())["song"]
    print(f"{args.code} ({name}): sync {sync:.3f}, current av_offset {off:.3f}")
    for t in args.times:
        words = words_around(song, t)
        print(f"song {t:.2f}s: " + " ".join(
            f"{w['w'].upper() if w['w'][:1].lower() in 'mbp' else w['w']}@{w['start']:.2f}" for w in words))
        strip(args.code, t, args.span, sync, off, words, Path("mv/work") / f"lips_{args.code}_{t:.2f}.jpg")
    print("offset = word start - song time where the lips close; positive: picture ahead. "
          "Save current + offset with --save, then check again.")


if __name__ == "__main__":
    main()
