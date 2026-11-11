"""Cut the reference audio for one lip-sync take: a black video carrying a slice of the song's vocal.

Usage: .venv/bin/python mv/scripts/lipsync_slice.py CODE FIRST_WORD_TIME SECONDS [--audio VOCALS.wav] [--plan]
       e.g. lipsync_slice.py V1a 8.14 7 --audio mv/stems/htdemucs_ft/song/vocals.wav

FIRST_WORD_TIME is the song time of the take's first sung word and has to be a word start in
mv/data/lyrics.json (it stops otherwise): take line starts from the transcription, never from dips in
the vocal's loudness. A dip can sit a whole phrase away from the line, and a slice cut there opens
inside the previous line and loses the end of its own. Transcribe the separated vocal for these times
(analyze_song.py --lyrics --vocals STEM); word times from the full mix can be a third of a second off.

The slice starts at the quietest point of the audio between 0.6 and 0.3 s before that word, so the take
opens in a gap, and runs SECONDS (whole seconds for most generators). Nothing in it is muted. It prints
the lines inside the slice with their times in the take, and warns when the slice opens inside a word
or ends before a line does: move the take to another line, or change its length. --plan prints without
writing. Otherwise it writes mv/work/slices/CODE.mp4 (854x480, 24 fps, black) and records the slice in
mv/data/slices.json, where sync_offset.py finds the audio and the song time to search near.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np

SR = 16000
OUT = Path("mv/work/slices")
SLICES = Path("mv/data/slices.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("first_word", type=float)
    ap.add_argument("seconds", type=float)
    ap.add_argument("--audio", default=None, help="the separated vocal (recommended); default: the song")
    ap.add_argument("--plan", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args()
    audio = args.audio or json.loads(Path("mv/data/song.json").read_text())["song"]
    lines = json.loads(Path("mv/data/lyrics.json").read_text())
    words = [w for ln in lines for w in ln.get("words", [])]
    if not words:
        sys.exit("mv/data/lyrics.json has no word times; run analyze_song.py --lyrics (with --vocals STEM)")
    near = min(words, key=lambda w: abs(w["start"] - args.first_word))
    if abs(near["start"] - args.first_word) > 0.15:
        sys.exit(f"no word starts at {args.first_word:.2f} s; the nearest is \"{near['w']}\" at {near['start']:.2f} s. "
                 "Take the time from mv/data/lyrics.json")
    w0 = near["start"]

    a, b = max(0.0, w0 - 0.6), max(0.0, w0 - 0.3)
    if b - a < 0.05:
        start = 0.0
    else:
        y, _ = librosa.load(audio, sr=SR, mono=True, offset=a, duration=b - a)
        win = int(0.01 * SR)
        env = np.convolve(np.abs(y), np.ones(win) / win, mode="same")
        start = round(a + int(np.argmin(env)) / SR, 3)
    end = start + args.seconds

    print(f"{args.code}: song {start:.3f}-{end:.3f} s, first word \"{near['w']}\" {w0 - start:.2f} s into the take")
    ok = True
    if not any(abs(ln["start"] - w0) < 0.05 for ln in lines):
        print(f"  WARNING \"{near['w']}\" is not the first word of a line: a take that opens mid-line starts on a cut word")
        ok = False
    for w in words:
        if w["start"] < start < w["end"] - 0.02:
            print(f"  WARNING opens inside \"{w['w']}\" ({w['start']:.2f}-{w['end']:.2f} s): the take will start on the "
                  "tail of what is sung before it")
            ok = False
    inside = [ln for ln in lines if start - 0.05 <= ln["start"] < end]
    for ln in inside:
        if ln["start"] > end - 0.6:   # whole-second lengths often catch the first sound of the next line
            print(f"  {ln['start'] - start:5.2f}         (the next line starts here: cut away from this take before it)")
            continue
        cut = ln["end"] > end + 0.05
        print(f"  {ln['start'] - start:5.2f}-{min(ln['end'], end) - start:5.2f}  {ln['text']}" + ("   <- CUT OFF" if cut else ""))
        if cut:
            lost = [w["w"] for w in ln.get("words", []) if w["end"] > end + 0.05]
            print(f"  WARNING the slice ends {ln['end'] - end:.2f} s before this line does (lost: {' '.join(lost)}): "
                  f"use {int(np.ceil(ln['end'] + 0.3 - start))} s, or end the take on the line before")
            ok = False
    if not inside:
        print("  WARNING no lyric line starts inside this slice")
        ok = False
    if args.plan:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{args.code}.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=854x480:r=24",
                    "-ss", f"{start:.3f}", "-t", f"{args.seconds:.3f}", "-i", str(audio), "-map", "0:v", "-map", "1:a",
                    "-af", "apad", "-t", f"{args.seconds:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    slices = json.loads(SLICES.read_text()) if SLICES.exists() else {}
    slices[args.code] = dict(start=start, dur=args.seconds, first_word=round(w0, 3), audio=str(audio), clean=ok)
    SLICES.write_text(json.dumps(slices, indent=1))
    print(f"wrote {out}; recorded in {SLICES}")


if __name__ == "__main__":
    main()
