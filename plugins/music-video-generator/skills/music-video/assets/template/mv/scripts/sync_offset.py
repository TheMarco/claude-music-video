"""Find where a clip's own audio sits in the song, for placing lipsync clips.

Usage: .venv/bin/python mv/scripts/sync_offset.py CLIP.mp4 [--near SECONDS] [--song song.mp3] [--window 2.0] [--save]
Prints the song time where the clip's audio starts (use it as sync= in the EDL), then the same estimate
for each 2 s window of the clip. Windows that disagree mean the mouth drifts there: start the cut later
or nudge sync for that cut. --near is the song time of the slice you sent to the generator; songs repeat
bars, so searching within 15 s of it avoids locking onto an identical bar elsewhere.
Needs a clip generated with audio (e.g. Seedance with the song slice as reference and audio on).
--save records the start as this take's "sync" in mv/data/mouths.json (keyed by the clip's file name),
where edl.py and vocal_match.py read it: a singing take is shown only at the song time it was recorded for.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import fftconvolve

SR, HOP = 16000, 160  # 10 ms frames

ap = argparse.ArgumentParser()
ap.add_argument("clip")
ap.add_argument("--near", type=float, default=None)
ap.add_argument("--song", default=None)
ap.add_argument("--window", type=float, default=2.0)
ap.add_argument("--save", action="store_true", help="record the start in mv/data/mouths.json")
args = ap.parse_args()
song = args.song or json.loads(Path("mv/data/song.json").read_text())["song"]
wav = subprocess.run(["ffmpeg", "-v", "error", "-i", args.clip, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
c = np.frombuffer(wav, np.float32)
if len(c) < SR:
    sys.exit("clip has no usable audio track")
s, _ = librosa.load(song, sr=SR, mono=True)


def feats(y):
    m = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=SR, n_fft=1024, hop_length=HOP, n_mels=64))
    m = m - m.mean(0, keepdims=True)
    return m / (np.linalg.norm(m, axis=0, keepdims=True) + 1e-9)  # unit vector per frame


FS, FC = feats(s), feats(c)
lo, hi = 0, FS.shape[1]
if args.near is not None:
    lo = max(0, int((args.near - 15) * SR / HOP))
    hi = min(FS.shape[1], int((args.near + 15 + len(c) / SR) * SR / HOP))


def locate(seg):
    """Lag (s) maximizing the mean cosine similarity between clip frames and song frames."""
    n = seg.shape[1]
    region = FS[:, lo:hi]
    if region.shape[1] < n:
        return float("nan"), 0.0
    score = sum(fftconvolve(region[b], seg[b][::-1], mode="valid") for b in range(seg.shape[0])) / n
    i = int(np.argmax(score))
    return (lo + i) * HOP / SR, float(score[i])


start, conf = locate(FC)
print(f"clip audio starts at song time {start:.3f}s (similarity {conf:.2f}; above 0.6 is solid)")
n = int(args.window * SR / HOP)
for k in range(0, FC.shape[1] - n + 1, n):
    t, cf = locate(FC[:, k:k + n])
    print(f"  clip {k * HOP / SR:5.1f}s -> song {t:8.3f}s  implies start {t - k * HOP / SR:8.3f}s  similarity {cf:.2f}")
if args.save:
    mfile = Path("mv/data/mouths.json")
    mouths = json.loads(mfile.read_text()) if mfile.exists() else {}
    mouths.setdefault(Path(args.clip).stem, {})["sync"] = round(start, 3)
    mfile.write_text(json.dumps(mouths, indent=1))
    print(f"saved sync {start:.3f} for {Path(args.clip).stem} in {mfile}")
