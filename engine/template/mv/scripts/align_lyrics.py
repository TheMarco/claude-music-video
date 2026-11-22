"""Put the real lyric on the transcription's word times.

Usage: .venv/bin/python mv/scripts/align_lyrics.py LYRICS.txt

LYRICS.txt holds the lyric as it is sung, one sung line per row in song order, repeats and spoken lines
written out; blank rows and rows starting with "#" or "[" (section labels) are skipped. Whisper hears
the times well and some words wrong; this keeps its times and replaces its words. The two word
sequences are aligned with difflib: matched words keep their times, replaced runs of equal length map
one to one, other runs are spread evenly over the time Whisper gave them, and words Whisper never heard
are spread over the gap between their neighbours.

Repeated sections (choruses sung three times, a hook that comes back) can pull lines onto the wrong
repeat when Whisper missed or garbled one of them. Give a section label a song time and the alignment
runs per section instead, each against only the words Whisper heard inside its own stretch of the song:
    [chorus 2 @131.4]
A timed label starts a stretch that runs to the next timed label (or the end of the song); untimed labels
inside it stay part of it, and lines before the first timed label get the stretch from 0. Take the times
from Whisper's lines in mv/data/lyrics_whisper.json; a second or so early is fine.

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


def align(lines, heard, floor=0.0):
    """Word times for lines from the words Whisper heard: [(line, [(word, start, end, exact)])]. Unheard words
    before the first heard one get 0.4 s each before it, no earlier than floor."""
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
            n = e - k
            t1 = times[e][0] if e < len(times) else None
            t0 = times[k - 1][1] if k > 0 else max(floor, (t1 if t1 is not None else floor) - 0.4 * n)
            t1 = t1 if t1 is not None else t0 + 0.4 * n
            for m in range(n):
                times[k + m] = (t0 + (t1 - t0) * m / n, t0 + (t1 - t0) * (m + 1) / n)
            k = e
        else:
            k += 1
    return [(ln, [(true[k][1], *times[k], exact[k]) for k, (li, _) in enumerate(true) if li == i])
            for i, ln in enumerate(lines)]


def stretches(rows):
    """The lyric's lines grouped by timed section labels ("[chorus 2 @131.4]"): [(t0, t1, lines)]."""
    groups, t = [[0.0, []]], None
    for ln in rows:
        m = re.match(r"\[[^\]]*@\s*([0-9]+(?:\.[0-9]+)?)\s*\]", ln)
        if m:
            t = float(m.group(1))
            groups.append([t, []])
        elif ln and ln[0] not in "#[" and any(norm(w) for w in ln.split()):
            groups[-1][1].append(ln)
    groups = [g for g in groups if g[1]]
    return [(g[0], nxt[0] if nxt else 1e9, g[1]) for g, nxt in zip(groups, groups[1:] + [None])]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    rows = [ln.strip() for ln in Path(sys.argv[1]).read_text().splitlines()]
    if not WHISPER.exists():
        if not OUT.exists():
            sys.exit("no mv/data/lyrics.json; run analyze_song.py --lyrics first")
        WHISPER.write_text(OUT.read_text())
    heard = [w for seg in json.loads(WHISPER.read_text()) for w in seg.get("words", []) if norm(w["w"])]
    if not heard:
        sys.exit(f"{WHISPER} has no word times")
    parts = stretches(rows)
    if len(parts) > 1:
        print(f"aligning {len(parts)} stretches separately (timed section labels)")
    out, loose = [], 0
    for t0, t1, lines in parts:
        mine = [w for w in heard if t0 <= (w["start"] + w["end"]) / 2 < t1]
        if not mine:
            print(f"  no words heard in {t0:.2f}-{min(t1, 9999):.2f}s: check that stretch's label time")
            mine = [{"w": "", "start": t0, "end": t0}]
        for ln, ws in align(lines, mine, t0):
            words = [{"w": w, "start": round(a, 2), "end": round(b, 2)} for w, a, b, _ in ws]
            miss = [w for w, _, _, ex in ws if not ex]
            loose += bool(miss)
            out.append({"start": words[0]["start"], "end": words[-1]["end"], "text": ln, "suspect": False,
                        "words": words, "unheard": miss})
            print(f"{words[0]['start']:7.2f}-{words[-1]['end']:7.2f}  {ln}" + (f"   ~ {' '.join(miss)}" if miss else ""))
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}: {len(out)} lines, {loose} with estimated word times (~); Whisper's own lines are in {WHISPER}")


if __name__ == "__main__":
    main()
