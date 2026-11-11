"""Put the real lyric on the transcription's word times.

Usage: .venv/bin/python mv/scripts/align_lyrics.py LYRICS.txt

LYRICS.txt holds the lyric as it is sung, one sung line per row in song order, repeats and spoken lines
written out; blank rows and rows starting with "#" or "[" (section labels) are skipped. Whisper hears
the times well and some words wrong; this keeps its times and replaces its words. The two word
sequences are aligned with difflib: matched words keep their times, replaced runs of equal length map
one to one, other runs are spread evenly over the time Whisper gave them, and words Whisper never heard
are spread over the gap between their neighbours.

Reads mv/data/lyrics.json as written by analyze_song.py --lyrics, keeps that file as
mv/data/lyrics_whisper.json (later runs read it from there), and writes mv/data/lyrics.json in the
same format with the real lines. It prints every line with its times; words after "~" got estimated
times, so check those lines by ear before a lip-sync slice or word-timed type depends on them.
"""
import difflib
import json
import re
import sys
from pathlib import Path

OUT = Path("mv/data/lyrics.json")
WHISPER = Path("mv/data/lyrics_whisper.json")


def norm(w):
    return re.sub(r"[^\w']", "", w.lower())


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    rows = [ln.strip() for ln in Path(sys.argv[1]).read_text().splitlines()]
    lines = [ln for ln in rows if ln and ln[0] not in "#[" and any(norm(w) for w in ln.split())]
    if not WHISPER.exists():
        if not OUT.exists():
            sys.exit("no mv/data/lyrics.json; run analyze_song.py --lyrics first")
        WHISPER.write_text(OUT.read_text())
    heard = [w for seg in json.loads(WHISPER.read_text()) for w in seg.get("words", []) if norm(w["w"])]
    if not heard:
        sys.exit(f"{WHISPER} has no word times")
    true = [(i, w) for i, ln in enumerate(lines) for w in ln.split() if norm(w)]
    a = [norm(w) for _, w in true]
    b = [norm(w["w"]) for w in heard]
    times = [None] * len(true)
    exact = [False] * len(true)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k]["start"], heard[j1 + k]["end"])
                exact[i1 + k] = op == "equal"
        elif op == "replace":
            t0, t1 = heard[j1]["start"], heard[j2 - 1]["end"]
            n = i2 - i1
            for k in range(n):
                times[i1 + k] = (t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)
    k = 0
    while k < len(times):   # words Whisper never heard: spread over the gap between their timed neighbours
        if times[k] is None:
            e = k
            while e < len(times) and times[e] is None:
                e += 1
            t0 = times[k - 1][1] if k > 0 else 0.0
            t1 = times[e][0] if e < len(times) else t0 + 0.4 * (e - k)
            n = e - k
            for m in range(n):
                times[k + m] = (t0 + (t1 - t0) * m / n, t0 + (t1 - t0) * (m + 1) / n)
            k = e
        else:
            k += 1
    out, loose = [], 0
    for i, ln in enumerate(lines):
        idx = [k for k, (li, _) in enumerate(true) if li == i]
        words = [{"w": true[k][1], "start": round(times[k][0], 2), "end": round(times[k][1], 2)} for k in idx]
        miss = [true[k][1] for k in idx if not exact[k]]
        loose += bool(miss)
        out.append({"start": words[0]["start"], "end": words[-1]["end"], "text": ln, "suspect": False,
                    "words": words, "unheard": miss})
        print(f"{words[0]['start']:7.2f}-{words[-1]['end']:7.2f}  {ln}" + (f"   ~ {' '.join(miss)}" if miss else ""))
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}: {len(out)} lines, {loose} with estimated word times (~); Whisper's own lines are in {WHISPER}")


if __name__ == "__main__":
    main()
