"""Find where a clip's own audio sits in the song, for placing lipsync clips.

Usage: .venv/bin/python mv/scripts/sync_offset.py CLIP.mp4 [--near SECONDS] [--song song.mp3] [--window 0.5] [--save]
Prints the song time where the clip's audio starts (use it as sync= in the EDL), then the same estimate
for each 0.5 s window of the clip (searched within 1.5 s of that start), and the stretch of the clip that
follows the song. Two things short windows show and one start time hides: a take that makes up its own
sound for its first second or two and only then locks onto the vocal (EARLY: start the shot where it
locks, or place that stretch with its own sync), and a take whose timing moves inside the line, usually
pauses squeezed or stretched (DRIFT: warp_take.py re-times the take onto the song as one shot; cutting it
into pieces with their own sync reads as a jump). --near is the song time of the slice you sent to the generator; songs repeat
bars, so searching within 15 s of it avoids locking onto an identical bar elsewhere.
Needs a clip generated with audio (e.g. Seedance with the song slice as reference and audio on).
A take made from a lipsync_slice.py slice needs neither option: its entry in mv/data/slices.json gives
the song time to search near and the audio the slice was cut from. When that was the separated vocal,
the take is matched against the vocal, which is the like-for-like comparison (--song STEM does the same
by hand). A similarity under 0.4 means the take's sound is not the song there (the generator re-sang or
garbled the line): nothing is saved, and the take needs a retake.
--save records the start as this take's "sync" in mv/data/mouths.json (keyed by the clip's file name),
where edl.py and vocal_match.py read it: a singing take is shown only at the song time it was recorded for.
It also records "lock", the clip seconds that follow the song at that sync, and "also", stretches that
follow it at a sync of their own ([clip from, clip to, sync]); edl.py warns about shots of the take that
fall outside both.
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
ap.add_argument("--window", type=float, default=0.5)
ap.add_argument("--save", action="store_true", help="record the start in mv/data/mouths.json")
args = ap.parse_args()
sfile = Path("mv/data/slices.json")
made = (json.loads(sfile.read_text()) if sfile.exists() else {}).get(Path(args.clip).stem, {})
if args.near is None and "start" in made:
    args.near = made["start"]
song = args.song or made.get("audio") or json.loads(Path("mv/data/song.json").read_text())["song"]
wav = subprocess.run(["ffmpeg", "-v", "error", "-i", args.clip, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
c = np.frombuffer(wav, np.float32)
if len(c) < SR:
    sys.exit("clip has no usable audio track")
s, _ = librosa.load(song, sr=SR, mono=True)


def feats(y):
    """Log mel energy, 100-6000 Hz (where a voice is), mean removed per band. Loud frames weigh more than
    pauses, so a take's room tone or made-up backing in the gaps doesn't decide the match."""
    m = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=1024, hop_length=HOP, n_mels=40, fmin=100, fmax=6000)
    m = np.log1p(30 * m)
    return m - m.mean(1, keepdims=True)


FC = feats(c)
lo, hi = 0, int(len(s) / HOP)
if args.near is not None:
    lo = max(0, int((args.near - 15) * SR / HOP))
    hi = min(hi, int((args.near + 15 + len(c) / SR) * SR / HOP))
FS = np.zeros((FC.shape[0], int(len(s) / HOP) + 1))
part = feats(s[lo * HOP:hi * HOP])
FS[:, lo:lo + part.shape[1]] = part


def scan(a, b, seg):
    """Cosine similarity between seg and every same-length stretch of the song frames a..b."""
    n = seg.shape[1]
    region = FS[:, a:b]
    if region.shape[1] < n:
        return None
    dot = sum(fftconvolve(region[k], seg[k][::-1], mode="valid") for k in range(seg.shape[0]))
    energy = np.convolve((region ** 2).sum(0), np.ones(n), mode="valid")
    return dot / (np.sqrt(np.maximum(energy, 1e-9)) * (np.linalg.norm(seg) + 1e-9))


def locate(seg):
    """Song time (s) where seg matches best, and the similarity there."""
    score = scan(lo, hi, seg)
    if score is None:
        return float("nan"), 0.0
    i = int(np.argmax(score))
    return (lo + i) * HOP / SR, float(score[i])


start, conf = locate(FC)
print(f"clip audio starts at song time {start:.3f}s (similarity {conf:.2f}; above 0.6 is solid), matched against {song}")
if "start" in made:
    print(f"  its slice started at {made['start']:.3f}s: the take sits {start - made['start']:+.2f}s from it")
n = int(args.window * SR / HOP)
rms = librosa.feature.rms(y=c, frame_length=1024, hop_length=HOP)[0]
loud = np.percentile(rms, 90) if rms.size else 0.0
wins = []   # (clip seconds, implied start, similarity) per window with sound in it
for k in range(0, FC.shape[1] - n + 1, n):
    if rms[k:k + n].mean() < 0.12 * loud:
        continue   # a pause in the take: nothing to match
    w_lo = max(0, int((start - 1.5) * SR / HOP) + k)
    w_hi = min(FS.shape[1], int((start + 1.5) * SR / HOP) + k + n)
    if w_hi - w_lo < n:
        continue
    score = scan(w_lo, w_hi, FC[:, k:k + n])
    i = int(np.argmax(score))
    wins.append((k * HOP / SR, (w_lo + i) * HOP / SR - k * HOP / SR, float(score[i])))
TOL, MIN_SIM = 0.08, 0.5
ok = [abs(st - start) <= TOL and cf >= MIN_SIM for _, st, cf in wins]
print(f"{args.window:g} s windows (clip time: offset from that start / similarity; pauses skipped):")
for j in range(0, len(wins), 8):
    print("  " + "  ".join(f"{ct:5.1f}:{st - start:+.2f}/{cf:.2f}{'' if g else '*'}"
                           for (ct, st, cf), g in zip(wins[j:j + 8], ok[j:j + 8])))
lock, also = None, []
if any(ok):
    a = next(i for i, g in enumerate(ok) if g)
    b = len(ok) - 1 - next(i for i, g in enumerate(reversed(ok)) if g)
    lock = (round(wins[a][0], 2), round(wins[b][0] + args.window, 2))
    print(f"follows the song at this start from clip {lock[0]:.1f}s to {lock[1]:.1f}s (* = a window that doesn't)")
    runs, cur = [], []
    for i, g in enumerate(ok):
        if not g:
            cur.append(i)
        if cur and (g or i == len(ok) - 1):
            runs.append(cur)
            cur = []
    for run in runs:
        where = "EARLY" if run[0] < a else "LATE" if run[0] > b else "DRIFT"
        t0, t1 = wins[run[0]][0], wins[run[-1]][0] + args.window
        offs = [wins[r][1] - start for r in run]
        if where == "EARLY":
            print(f"EARLY: clip {t0:.1f}-{t1:.1f}s doesn't follow the song at this start (the take came in at its own "
                  f"pace, or the model made up a lead-in): start the shot at clip {lock[0]:.1f}s or later")
        elif where == "DRIFT" and len(run) >= 2 and np.mean(np.abs(offs)) > TOL:
            print(f"DRIFT: clip {t0:.1f}-{t1:.1f}s wanders off this start (mean {np.mean(offs):+.2f}s): one sync "
                  "doesn't fit the line; warp_take.py re-times the take onto the song as one shot")
        group = []   # stretches inside the run that follow the song at an offset of their own
        for r in run + [None]:
            fits = (r is not None and wins[r][2] >= MIN_SIM and
                    (not group or abs((wins[r][1] - start) - (wins[group[0]][1] - start)) <= TOL))
            if fits:
                group.append(r)
                continue
            if len(group) >= 2:
                alt = start + float(np.median([wins[g][1] - start for g in group]))
                g0, g1 = round(wins[group[0]][0], 2), round(wins[group[-1]][0] + args.window, 2)
                also.append([g0, g1, round(alt, 3)])
                print(f"  clip {g0:.1f}-{g1:.1f}s follows the song at sync={alt:.2f} ({alt - start:+.2f}s): "
                      "shown there with that sync, or warp_take.py")
            group = [r] if (r is not None and wins[r][2] >= MIN_SIM) else []
if conf < 0.4:
    print("LOW SIMILARITY: this take's sound is not the song here. Listen to the clip; if the line is re-sung or "
          "garbled, make the take again. If the windows follow the song in stretches at different offsets, the take "
          "drifts rather than re-sings: warp_take.py (with --sync) can still use it. Nothing saved.")
    sys.exit(1)
if args.save:
    mfile = Path("mv/data/mouths.json")
    mouths = json.loads(mfile.read_text()) if mfile.exists() else {}
    entry = mouths.setdefault(Path(args.clip).stem, {})
    entry["sync"] = round(start, 3)
    entry.pop("lock", None)
    entry.pop("also", None)
    if lock:
        entry["lock"] = list(lock)
    if also:
        entry["also"] = also
    mfile.write_text(json.dumps(mouths, indent=1))
    print(f"saved sync {start:.3f}" + (f" and lock {lock[0]}-{lock[1]} s" if lock else "") +
          f" for {Path(args.clip).stem} in {mfile}")
