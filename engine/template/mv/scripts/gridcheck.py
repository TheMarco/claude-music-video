"""Check the beat grid in mv/data/song.json before cutting to it.

Usage: .venv/bin/python mv/scripts/gridcheck.py [--start S] [--end E] [--out mv/review/grid_check.wav]

Every cut, pulse and overlay hangs on the grid, so a wrong one (the first beat half a beat off, half or
double the real tempo, a drift the map doesn't follow) spoils the whole video. Two checks:

1. A table per song section: how strongly the song's kicks land on the grid's beats, on the half beats
   between them, on even and odd beats, and the shift (in ms) that would fit that section best. It
   prints a hint when the half beats are as strong as the beats (the first beat may be half a beat off,
   or the real tempo is double), when every second beat is weak (the real tempo may be half), or when a
   section fits better shifted by more than a frame (drift, or a t0 that is off).
2. The song with a click on every beat and a higher click on every bar line, written to OUT for the
   user to listen to. The ear is the judge: the numbers only say where to listen.

Run it after analyze_song.py and again after editing bpm, t0 or beats in song.json by hand.
"""
import argparse
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from analyze_song import SR as ASR, onset_env  # noqa: E402
from timing import BEAT, DUR, FPS, SECTIONS, SONG, beat, beat_at  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    ap.add_argument("--out", default="mv/review/grid_check.wav")
    args = ap.parse_args()

    y, _ = librosa.load(SONG, sr=ASR, mono=True)
    _, e, t_env, _, _ = onset_env(y)
    e = e / (e.mean() + 1e-9)
    at = lambda ts: float(np.interp(ts, t_env, e).mean()) if len(ts) else 0.0
    ks = np.arange(0, int(beat_at(DUR)))
    bt = np.array([beat(k) for k in ks])
    half_t = np.array([beat(k + 0.5) for k in ks])
    shifts = np.arange(-0.5, 0.5, 0.02) * BEAT

    hints = []
    print(f"{'section':12} {'start':>7} {'on':>6} {'half':>6} {'even':>6} {'odd':>6} {'best shift':>10}")
    rows = [(a, min(b, DUR), name) for a, b, name, _, _ in SECTIONS] + [(0.0, DUR, "all")]
    for a, b, name in rows:
        m = (bt >= a) & (bt < b)
        if m.sum() < 4:
            continue
        on, off = at(bt[m]), at(half_t[m])
        even, odd = at(bt[m & (ks % 2 == 0)]), at(bt[m & (ks % 2 == 1)])
        best = float(shifts[int(np.argmax([at(bt[m] + s) for s in shifts]))])
        print(f"{name:12} {a:7.2f} {on:6.2f} {off:6.2f} {even:6.2f} {odd:6.2f} {best * 1000:8.0f}ms")
        fit = at(bt[m] + best)
        if max(on, off, fit) < 0.5:
            continue   # too little kick here to judge
        if off > 0.8 * on and off >= 0.5:
            hints.append(f"{name}: the half beats are as strong as the beats (t0 half a beat off, or the real tempo is double)")
        elif on >= 0.5 and min(even, odd) < 0.3 * max(even, odd):
            hints.append(f"{name}: every second beat is weak (the real tempo may be half; or a kick on 1 and 3 only)")
        if abs(best) > 1.0 / FPS and fit > 1.25 * on:
            hints.append(f"{name}: fits better shifted {best * 1000:+.0f} ms (drift here, or t0 is off)")
    print("\n".join("HINT " + h for h in hints) if hints else "no hints: the kicks sit on the grid")

    sr = 44100
    y, _ = librosa.load(SONG, sr=sr, mono=True, offset=args.start, duration=max(args.end - args.start, 0.1))
    mix = 0.6 * y / (np.abs(y).max() + 1e-9)
    n = int(0.03 * sr)
    tt = np.arange(n) / sr
    for k in ks:
        i = int((beat(k) - args.start) * sr)
        if 0 <= i < len(mix) - n:
            bar = k % 4 == 0
            mix[i:i + n] += (0.5 if bar else 0.35) * np.sin(2 * np.pi * (2400 if bar else 1400) * tt) * np.exp(-tt * 140)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, np.clip(mix, -1, 1), sr, subtype="PCM_16")
    print(f"wrote {out}: clicks on the beats, higher clicks on the bar lines; ask the user to listen")


if __name__ == "__main__":
    main()
