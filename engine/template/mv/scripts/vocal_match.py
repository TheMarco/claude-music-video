"""Check whether a singing take fits where the edit shows it, by comparing the song's vocal.

Usage: .venv/bin/python mv/scripts/vocal_match.py                    every lipsync shot in the edit
       .venv/bin/python mv/scripts/vocal_match.py --pair REC SHOWN DUR
The first form reads mv/data/edl.json and mv/data/mouths.json (each take's recorded "sync" time, saved
by sync_offset.py --save) and, for every shot of a take shown somewhere other than where it was
recorded, compares the vocal at the recorded song time with the vocal where it plays. --pair compares
two song times directly, e.g. a chorus line against its repeat, before deciding anything.

The vocal is separated from the mix with a soft mask (librosa nn_filter), then compared by its loudness
envelope (correlation r) and pitch content (chroma similarity while either is singing). Two genuinely
matching lines have scored r around 0.7; lines phrased differently scored 0.2-0.4 and looked wrong on
screen. A take is only shown where it was recorded; treat a low score as confirmation, not permission.
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np

SR, HOP = 22050, 512
CACHE = Path("mv/work/vocal_feats.npz")


def features(song):
    if CACHE.exists() and CACHE.stat().st_mtime > Path(song).stat().st_mtime:
        f = np.load(CACHE)
        return f["env"], f["chroma"]
    y, _ = librosa.load(song, sr=SR, mono=True)
    S, _ = librosa.magphase(librosa.stft(y, n_fft=2048, hop_length=HOP))
    rep = librosa.decompose.nn_filter(S, aggregate=np.median, metric="cosine",
                                      width=int(librosa.time_to_frames(2, sr=SR, hop_length=HOP)))
    rep = np.minimum(S, rep)
    V = librosa.util.softmask(S - rep, 10 * rep, power=2) * S
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    band = (freqs > 200) & (freqs < 4000)
    env = librosa.amplitude_to_db(V[band].sum(0) + 1e-6)
    env = env - np.percentile(env, 50)
    chroma = librosa.feature.chroma_stft(S=V ** 2, sr=SR, hop_length=HOP)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, env=env, chroma=chroma)
    return env, chroma


def compare(env, chroma, rec, shown, dur):
    fr = lambda t: int(t * SR / HOP)
    a, b, n = fr(rec), fr(shown), max(fr(dur), 2)
    ea, eb = env[a:a + n], env[b:b + n]
    n = min(len(ea), len(eb))
    ea, eb = ea[:n], eb[:n]
    r = float(np.corrcoef(ea, eb)[0, 1]) if n > 1 and ea.std() > 0 and eb.std() > 0 else 0.0
    ca, cb = chroma[:, a:a + n], chroma[:, b:b + n]
    sing = (ea > 3) | (eb > 3)
    cs = (ca * cb).sum(0) / (np.linalg.norm(ca, axis=0) * np.linalg.norm(cb, axis=0) + 1e-9)
    return r, float(cs[sing].mean()) if sing.any() else float("nan"), float((ea > 3).mean()), float((eb > 3).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=3, type=float, metavar=("REC", "SHOWN", "DUR"))
    args = ap.parse_args()
    song = json.loads(Path("mv/data/song.json").read_text())["song"]
    env, chroma = features(song)
    if args.pair:
        r, cs, va, vb = compare(env, chroma, *args.pair)
        print(f"vocal at {args.pair[0]:.2f}s vs {args.pair[1]:.2f}s over {args.pair[2]:.1f}s: "
              f"envelope r={r:.2f}  chroma={cs:.2f}  singing {va:.0%} / {vb:.0%}")
        return
    mfile = Path("mv/data/mouths.json")
    mouths = json.loads(mfile.read_text()) if mfile.exists() else {}
    takes = {k: v["sync"] for k, v in mouths.items() if v.get("sync") is not None}
    if not takes:
        print("no lipsync takes with a recorded sync in mv/data/mouths.json (sync_offset.py --save)")
        return
    for s in json.loads(Path("mv/data/edl.json").read_text())["main"]:
        if s["src"] not in takes:
            continue
        rec = takes[s["src"]] + s["in"]
        if abs(rec - s["start"]) <= 0.05:
            print(f"{s['src']:4} shown {s['start']:7.2f}s  where it was recorded")
            continue
        r, cs, va, vb = compare(env, chroma, rec, s["start"], s["dur"])
        print(f"{s['src']:4} shown {s['start']:7.2f}-{s['start'] + s['dur']:.2f}s, recorded {rec:.2f}s  "
              f"envelope r={r:.2f}  chroma={cs:.2f}  singing {va:.0%} recorded / {vb:.0%} shown")


if __name__ == "__main__":
    main()
