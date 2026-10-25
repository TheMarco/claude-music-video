"""Analyze the song: tempo, beat grid, sections, drops, end point, and (optionally) lyrics.

Usage: .venv/bin/python mv/scripts/analyze_song.py SONG.mp3 [--title T] [--artist A] [--lyrics] [--language en] [--force]

Writes a draft mv/data/song.json (unless it exists; --force overwrites) and prints a section table.
If the tempo drifts (common in AI-generated songs, which can wander by several BPM), it also
writes a "beats" list that follows the drift; timing.py then uses it instead of a fixed grid.
The draft is a starting point: check the grid with a beat sheet, rename the sections after listening
and reading the lyrics, and adjust drops, countdowns and letterbox stretches by hand.
With --lyrics it also transcribes into mv/data/lyrics.json with mlx-whisper (Apple Silicon) or, failing
that, openai-whisper (pip install openai-whisper).
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np

SR = 22050
HOP = 256
DRIFT_BPM = 1.0   # a tempo trend (or wobble) bigger than this gets a beat map instead of a fixed grid


def onset_env(y):
    """Kick-weighted onset envelope (low-band flux plus general onset strength), masked to loud parts."""
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    f = librosa.fft_frequencies(sr=SR, n_fft=2048)
    low = S[(f > 30) & (f < 150)].sum(0)
    flux = np.maximum(0, np.diff(low, prepend=low[0]))
    onset = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    n = min(len(flux), len(onset))
    env = flux[:n] / (flux.max() + 1e-9) + 0.5 * onset[:n] / (onset.max() + 1e-9)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0][:n]
    return env, env * (rms > np.percentile(rms, 60)), np.arange(n) * HOP / SR, S, f


def best_grid(e, t_env, periods, start, length):
    """Period and phase whose beat grid collects the most onset energy in [start, start + length)."""
    best = (-1.0, periods[0], 0.0)
    for period in periods:
        phases = np.arange(0, period, 0.002)
        k = np.arange(int(length / period) + 1)
        score = np.interp(start + phases[:, None] + k[None, :] * period, t_env, e, right=0).sum(1)
        i = int(np.argmax(score))
        if score[i] > best[0]:
            best = (float(score[i]), float(period), float(start + phases[i]))
    return best


def find_grid(e, t_env, dur):
    ac = librosa.autocorrelate(e - e.mean(), max_size=int(1.2 * SR / HOP))
    lags = np.arange(len(ac)) * HOP / SR
    ok = (lags > 60 / 180) & (lags < 60 / 70)
    cand = lags[ok][np.argmax(ac[ok])]
    # autocorrelation lags are about 1% apart at this tempo, so search a few percent around them
    _, period, phase = best_grid(e, t_env, np.linspace(cand * 0.96, cand * 1.04, 801), 0.0, dur)
    bpm = 60 / period
    if abs(bpm - round(bpm)) < 0.08:  # most produced tracks sit on a whole BPM
        bpm = float(round(bpm))
        _, period, phase = best_grid(e, t_env, [60 / bpm], 0.0, dur)
    return bpm, phase % period


def local_tempo(e, t_env, bpm, dur, win=24.0, step=6.0):
    """Best BPM in sliding windows, to detect tempo drift."""
    out = []
    for a in np.arange(0, max(dur - win, 1), step):
        m = (t_env >= a) & (t_env < a + win)
        if e[m].sum() < 0.05 * e.sum() * win / dur:
            continue  # too quiet to judge
        _, period, _ = best_grid(e, t_env, 60 / np.arange(bpm * 0.96, bpm * 1.04, 0.05), a, win)
        out.append((a + win / 2, 60 / period))
    return np.array(out)


def beat_map(env, t_env, curve):
    """Beat times that follow a tempo curve, via librosa's dynamic-programming tracker."""
    bpm_frames = np.interp(t_env, curve[:, 0], curve[:, 1])
    _, beats = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP, bpm=bpm_frames,
                                       tightness=300, trim=False, units="time")
    return np.asarray(beats, float)


def sections(beats, dur, S, f):
    """Split the song at bar lines where energy changes, labeled calm / mid / peak."""
    t_stft = np.arange(S.shape[1]) * HOP / SR
    rms = np.sqrt((S ** 2).mean(0))
    low = S[(f > 30) & (f < 150)].mean(0)
    bars = list(beats[::4]) + [dur]
    nb = len(bars) - 1
    feats = []
    for i in range(nb):
        m = (t_stft >= bars[i]) & (t_stft < bars[i + 1])
        feats.append((rms[m].mean() if m.any() else 0, low[m].mean() if m.any() else 0))
    feats = np.array(feats)
    feats = feats / (feats.max(0) + 1e-9)
    nov = np.zeros(nb)
    for i in range(2, nb - 1):
        nov[i] = np.abs(feats[i:i + 2].mean(0) - feats[i - 2:i].mean(0)).sum()
    nov *= np.where(np.arange(nb) % 4 == 0, 1.35, 1.0)  # prefer 4-bar phrase lines
    cuts = [0]
    for i in np.argsort(nov)[::-1]:
        if nov[i] < 0.25:
            break
        if all(abs(i - c) >= 4 for c in cuts):
            cuts.append(int(i))
    cuts = sorted(cuts) + [nb]
    out = []
    for a, b in zip(cuts, cuts[1:]):
        level, lowl = feats[a:b, 0].mean(), feats[a:b, 1].mean()
        kind = "peak" if (level > 0.7 and lowl > 0.6) else "calm" if level < 0.4 or lowl < 0.15 else "mid"
        out.append(dict(start_bar=a, end_bar=b, kind=kind, level=round(float(level), 2), low=round(float(lowl), 2)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("--title", default="")
    ap.add_argument("--artist", default="")
    ap.add_argument("--lyrics", action="store_true")
    ap.add_argument("--language", default="en", help="Whisper language code; use the song's language")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    y, _ = librosa.load(args.song, sr=SR, mono=True)
    dur = len(y) / SR
    env, e, t_env, S, f = onset_env(y)
    bpm, t0 = find_grid(e, t_env, dur)
    curve = local_tempo(e, t_env, bpm, dur)
    trend = wobble = 0.0
    if len(curve) >= 3:
        fit = np.polyfit(curve[:, 0], curve[:, 1], 1)
        trend = float(fit[0] * dur)                                   # BPM change across the song
        wobble = float((curve[:, 1] - np.polyval(fit, curve[:, 0])).std())
    beats = t0 + np.arange(int((dur - t0) / (60 / bpm)) + 1) * (60 / bpm)
    grid_score = float(np.interp(beats, t_env, e).mean())
    use_map = abs(trend) > DRIFT_BPM or wobble > 0.8
    if use_map:
        beats = beat_map(env, t_env, curve)
        t0 = float(beats[0])
    segs = sections(beats, dur, S, f)

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    tr = np.arange(len(rms)) * HOP / SR
    last = tr[np.nonzero(rms > 0.25 * rms.max())[0][-1]]
    end = float(beats[np.argmin(np.abs(beats - last))])

    bar_t = list(beats[::4]) + [dur]
    sec_json, drops, counts = [], [], {}
    for i, s in enumerate(segs):
        a = float(bar_t[s["start_bar"]]) if i else 0.0
        b = float(bar_t[s["end_bar"]]) if i < len(segs) - 1 else dur + 1
        k = s["kind"]
        if i == 0:
            name = "intro"
        elif k == "peak" and segs[i - 1]["kind"] != "peak" and s["low"] - segs[i - 1]["low"] > 0.25:
            name = f"drop{len(drops) + 1}"
            drops.append(round(a, 3))
        else:
            counts[k] = counts.get(k, 0) + 1
            name = f"{k}{counts[k]}"
        sec_json.append(dict(name=name, start=round(a, 3), end=round(b, 3),
                             kick={"peak": 1.0, "mid": 0.35, "calm": 0.0}[k], calm=(k == "calm")))
    idx = lambda t: int(np.argmin(np.abs(beats - t)))
    cfg = dict(song=args.song, title=args.title, artist=args.artist, fps=24, bpm=round(bpm, 3), t0=round(t0, 4),
               duration=round(dur, 3), end=round(end, 3), drops=drops,
               shocks=[[d, 0.09] for d in drops],
               countdowns=[round(float(beats[max(idx(d) - 8, 0)]), 3) for d in drops],
               letterbox=[], sections=sec_json)
    if use_map:
        cfg["beats"] = [round(float(b), 4) for b in beats]

    print(f"BPM {bpm:.2f}  beat {60 / bpm:.4f}s  t0 {t0:.4f}s  duration {dur:.2f}s  end {end:.2f}s")
    if len(curve):
        print(f"local tempo {curve[:, 1].min():.2f}-{curve[:, 1].max():.2f} BPM, trend {trend:+.2f}, wobble {wobble:.2f}"
              + (f"  -> DRIFTS: beat map with {len(beats)} beats" if use_map else "  -> steady grid"))
    if grid_score < 0.08:
        print("WEAK BEAT: kicks are faint or the tempo is loose (ballad, rubato). Cut on phrases, lyrics and "
              "energy changes rather than strict beats, and check the grid by ear.")
    print(f"{'name':10} {'start':>8} {'end':>8} {'beat':>6} {'bars':>5}  kind  level  low")
    for s, js in zip(segs, sec_json):
        print(f"{js['name']:10} {js['start']:8.2f} {min(js['end'], dur):8.2f} {idx(js['start']):6d} "
              f"{s['end_bar'] - s['start_bar']:5d}  {s['kind']:5} {s['level']:5.2f} {s['low']:5.2f}")
    print("drops:", drops)

    out = Path("mv/data/song.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.force:
        print(f"{out} exists; not overwritten (use --force). Draft printed above.")
    else:
        out.write_text(json.dumps(cfg, indent=1))
        print("wrote", out)

    if args.lyrics:
        opts = dict(word_timestamps=True, language=args.language, condition_on_previous_text=False)
        try:
            import mlx_whisper
            r = mlx_whisper.transcribe(args.song, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", **opts)
        except ImportError:
            try:
                import whisper
            except ImportError:
                raise SystemExit("to transcribe lyrics: pip install mlx-whisper (Apple Silicon) or openai-whisper")
            r = whisper.load_model("turbo").transcribe(args.song, **opts)
        keep = []
        for s in r["segments"]:
            text = s["text"].strip()
            junk = (s.get("no_speech_prob", 0) > 0.6 or s.get("compression_ratio", 0) > 2.4
                    or text.lower().strip(".! ") in ("thank you", "thanks for watching", "you"))
            keep.append(dict(start=round(s["start"], 2), end=round(s["end"], 2), text=text, suspect=bool(junk),
                             words=[dict(w=w["word"].strip(), start=round(w["start"], 2), end=round(w["end"], 2))
                                    for w in s.get("words", [])]))
        Path("mv/data/lyrics.json").write_text(json.dumps(keep, indent=1))
        for s in keep:
            print(f"{s['start']:7.2f}-{s['end']:7.2f} {'?' if s['suspect'] else ' '} {s['text']}")
        print("wrote mv/data/lyrics.json (lines marked ? are likely hallucinations)")


if __name__ == "__main__":
    main()
