"""Re-time a lip-sync take onto the song, so a take whose timing moves inside a line plays as one shot.

Usage: .venv/bin/python mv/scripts/warp_take.py CODE FROM TO [--out NEWCODE] [--sync T] [--song AUDIO]
                                                [--min-speed 0.55] [--max-speed 1.5]

Generated takes don't always keep the vocal's timing: a take can squeeze a pause, stretch another, or
come in early, so sync_offset.py finds windows that follow the song at different syncs (DRIFT, or
stretches with a sync of their own). Cutting such a take into pieces with their own sync puts a jump in
the middle of a sung line. This plays the one take at a varying speed instead, so every moment of it
lands on the matching moment of the song.

FROM and TO are song seconds: the stretch the new clip covers (one line, or two). The take's own audio is
matched against the song, or against the audio its lipsync_slice.py slice was cut from (the separated
vocal, as sync_offset.py does), in 0.5 s windows, which finds the stretches where the take follows the
song at one offset each. Each stretch plays at normal speed with its own offset, and the speed changes
only in the gaps between them, the pauses, where the mouth is still; it stays between --min-speed and
--max-speed, so the picture never visibly races or crawls. (On a test take this followed the song at
0.47, against 0.27 at the best single sync, 0.31 cut in two pieces, and 0.26 for a frame-by-frame
dynamic time warp, which bends the picture inside the words too.) --sync is where the
take's audio starts in the song when mouths.json has none (sync_offset.py refuses to save a take that
matches badly at any single sync; such a take is often the one that needs this); otherwise its slice's
start in mv/data/slices.json is used.

Writes mv/clips/NEWCODE.mp4 (default CODE + "w"), whose frame 0 is song time FROM: each frame blends the
take's two nearest frames, and the take's audio is re-timed with it, so sync_offset.py can check the
result. CODE_matte.mp4 and CODE_depth.mp4 are warped the same way when they exist. The map goes to
mv/data/warp_NEWCODE.json and "sync": FROM for NEWCODE to mv/data/mouths.json; place it with
S("NEWCODE", 0, beats, sync=FROM). It prints how closely the take follows the song before (at its one
sync) and after, as the mean similarity of 0.25 s windows with voice in them. Watch the result: a warp
that scores no better than the plain sync isn't worth using.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS  # noqa: E402

SR, HOP = 16000, 160
CLIPS, DATA = Path("mv/clips"), Path("mv/data")


def feats(y):
    """The same features as sync_offset.py: log mel energy, 100-6000 Hz, mean removed per band."""
    m = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=1024, hop_length=HOP, n_mels=40, fmin=100, fmax=6000)
    m = np.log1p(30 * m)
    return m - m.mean(1, keepdims=True)


def audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le",
                          "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def follow(ref, take, song_t, clip_t, t0):
    """Mean similarity of 0.25 s windows with voice in them: the take's sound at clip_t(song_t) against the
    reference at song_t, with no search, as the viewer hears and sees it."""
    ts = np.arange(song_t[0], song_t[-1], 1 / SR)
    warped = np.interp(np.interp(ts, song_t, clip_t) * SR, np.arange(len(take)), take)
    r = ref[int(song_t[0] * SR):int(song_t[0] * SR) + len(warped)]
    A, B = feats(warped[:len(r)]), feats(r)
    eB = (np.log1p(30 * librosa.feature.melspectrogram(y=r, sr=SR, n_fft=1024, hop_length=HOP, n_mels=40, fmin=100,
                                                         fmax=6000))).sum(0)
    w = int(0.25 * SR / HOP)
    sims = []
    for k in range(0, min(A.shape[1], B.shape[1]) - w + 1, w):
        if eB[k:k + w].mean() < 0.15 * np.percentile(eB, 90):
            continue   # a pause in the vocal
        a, b = A[:, k:k + w], B[:, k:k + w]
        d = np.linalg.norm(a) * np.linalg.norm(b)
        sims.append(float((a * b).sum() / d) if d > 0 else 0.0)
    return float(np.mean(sims)) if sims else 0.0


MIN_SIM, TOL = 0.5, 0.08


def steady_runs(take, ref, sync, t0, t1):
    """Stretches of the song (from, to, sync) where the take follows it at one offset: 0.5 s windows of the
    take every 0.25 s, each found in the song within 1.5 s of where the take's sync puts it, grouped while
    the offset holds (the same measurement as sync_offset.py). Kept in order, so the map runs forward."""
    W, step = int(0.5 * SR / HOP), int(0.25 * SR / HOP)
    c_lo, c_hi = max(0.0, t0 - sync - 1.5), min(len(take) / SR, t1 - sync + 1.5)
    A = feats(take[int(c_lo * SR):int(c_hi * SR)])
    r_lo = max(0.0, t0 - 3.0)
    R = feats(ref[int(r_lo * SR):int((t1 + 3.0) * SR)])
    e = A.clip(0).sum(0)
    wins = []
    for k in range(0, A.shape[1] - W + 1, step):
        if e[k:k + W].mean() < 0.15 * np.percentile(e, 90):
            continue
        seg = A[:, k:k + W]
        ct = c_lo + k * HOP / SR
        a = max(0, int((ct + sync - 1.5 - r_lo) * SR / HOP))
        b = min(R.shape[1], int((ct + sync + 1.5 - r_lo) * SR / HOP) + W)
        if b - a < W:
            continue
        reg = R[:, a:b]
        dot = sum(fftconvolve(reg[j], seg[j][::-1], mode="valid") for j in range(seg.shape[0]))
        en = np.convolve((reg ** 2).sum(0), np.ones(W), mode="valid")
        sc = dot / (np.sqrt(np.maximum(en, 1e-9)) * (np.linalg.norm(seg) + 1e-9))
        i = int(np.argmax(sc))
        if sc[i] >= MIN_SIM:
            st = r_lo + (a + i) * HOP / SR
            wins.append((ct + 0.25, st + 0.25, st - ct))    # window centres, clip and song
    groups, cur = [], []
    for w in wins:
        if cur and (abs(w[2] - np.median([g[2] for g in cur])) > TOL or w[0] - cur[-1][0] > 0.6):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    runs = []
    for g in groups:
        if len(g) < 2:
            continue
        x = float(np.median([w[2] for w in g]))
        s0, s1 = g[0][1], g[-1][1]
        if s1 < t0 - 0.5 or s0 > t1 + 0.5:
            continue
        if runs and (s0 <= runs[-1][1] or s0 - x <= runs[-1][1] - runs[-1][2]):
            continue   # would run the take backwards: keep the earlier stretch
        runs.append((s0, s1, x))
    return runs


def warp_video(src, dst, clip_t, gray, sound=None):
    """Write dst with one frame per entry of clip_t, blending src's two nearest frames; sound is an optional
    (samples, rate) audio track."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(probe[0]), int(probe[1])
    ch = 1 if gray else 3
    fmt = "gray" if gray else "rgb24"
    dec = subprocess.Popen(["ffmpeg", "-v", "quiet", "-i", str(src), "-f", "rawvideo", "-pix_fmt", fmt, "-"],
                           stdout=subprocess.PIPE)
    tmp = Path(tempfile.mkdtemp())
    vid = tmp / "v.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", fmt, "-s", f"{w}x{h}", "-r",
                            str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12" if gray else "13", "-pix_fmt",
                            "yuv420p", str(vid)], stdin=subprocess.PIPE)
    size = w * h * ch
    have, idx = [], -1          # the last two decoded frames and the index of the newer one

    def frame(i):
        nonlocal idx
        while idx < i:
            buf = dec.stdout.read(size)
            if len(buf) < size:
                break
            have.append(np.frombuffer(buf, np.uint8).reshape(h, w, ch).astype(np.float32))
            del have[:-2]
            idx += 1
        return have[-1] if idx <= i else have[-2]

    for c in clip_t:
        x = max(0.0, c * FPS)
        i0 = int(np.floor(x))
        u = x - i0
        f0 = frame(i0)
        f = f0 if u < 0.02 else f0 * (1 - u) + frame(i0 + 1) * u
        enc.stdin.write(np.clip(f + 0.5, 0, 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.kill()          # the rest of the take isn't needed
    dec.wait()
    dec.stdout.close()
    if sound is None:
        vid.replace(dst)
    else:
        wav = tmp / "a.wav"
        sf.write(wav, sound[0], sound[1])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(vid), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-shortest", str(dst)], check=True)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("t_from", type=float)
    ap.add_argument("t_to", type=float)
    ap.add_argument("--out")
    ap.add_argument("--sync", type=float)
    ap.add_argument("--song")
    ap.add_argument("--min-speed", type=float, default=0.55)
    ap.add_argument("--max-speed", type=float, default=1.5)
    args = ap.parse_args()
    code, out = args.code, args.out or args.code + "w"
    src = CLIPS / f"{code}.mp4"
    if not src.exists():
        sys.exit(f"no {src}")
    load = lambda p: json.loads(p.read_text()) if p.exists() else {}
    mouths, made = load(DATA / "mouths.json"), load(DATA / "slices.json").get(code, {})
    sync = args.sync if args.sync is not None else mouths.get(code, {}).get("sync", made.get("start"))
    if sync is None:
        sys.exit(f"no sync for {code}: give --sync (where the take's audio starts in the song)")
    ref_path = args.song or made.get("audio") or load(DATA / "song.json")["song"]
    take = audio(src)
    if len(take) < SR:
        sys.exit(f"{src} has no usable audio track")
    ref, _ = librosa.load(ref_path, sr=SR, mono=True)
    t0, t1 = args.t_from, args.t_to
    runs = steady_runs(take, ref, sync, t0, t1)
    if not runs:
        sys.exit(f"{code} doesn't follow the song anywhere in {t0:.2f}-{t1:.2f}s (no 0.5 s window matches above "
                 f"{MIN_SIM}); check --sync and --song, or make the take again")
    for r in runs:
        print(f"  song {r[0]:6.2f}-{r[1]:6.2f}s follows the take at sync {r[2]:.2f}")
    # Each steady stretch keeps its own offset; between stretches (the pauses) the speed changes linearly.
    pts = []
    for s0, s1, x in runs:
        pts += [(s0, s0 - x), (s1, s1 - x)]
    ps, pc = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    song_t = t0 + np.arange(int(round((t1 - t0) * FPS))) / FPS
    target = np.interp(song_t, ps, pc)
    target = np.where(song_t < ps[0], song_t - runs[0][2], target)       # before the first stretch: its offset
    target = np.where(song_t > ps[-1], song_t - runs[-1][2], target)     # after the last: its offset
    # Hold the playback speed inside the limits, steering back toward the map where that pulls it off.
    lo, hi = args.min_speed / FPS, args.max_speed / FPS
    clip_t = target.copy()
    for _ in range(60):
        err = target - clip_t
        step = np.clip(np.diff(target) + 0.15 * np.diff(err) + 0.08 * err[1:], lo, hi)
        clip_t = np.concatenate([[target[0]], target[0] + np.cumsum(step)])
    clip_t = np.clip(clip_t, 0.0, len(take) / SR - 1.0 / FPS)
    speed = np.diff(clip_t) * FPS
    best = max((follow(ref, take, song_t, song_t - x, t0), x) for x in np.arange(sync - 1.5, sync + 1.5, 0.02)
               if (song_t - x)[0] >= 0 and (song_t - x)[-1] <= len(take) / SR)
    before, sync = best
    after = follow(ref, take, song_t, clip_t, t0)
    print(f"{code}: song {t0:.2f}-{t1:.2f}s from clip {clip_t[0]:.2f}-{clip_t[-1]:.2f}s; speed {speed.min():.2f}-"
          f"{speed.max():.2f}x (median {np.median(speed):.2f}); off the map by at most "
          f"{np.abs(clip_t - target).max():.3f}s (where the speed limits held it back)")
    print(f"follows the song: {before:.2f} at the best single sync ({sync:.2f}), {after:.2f} warped "
          "(mean similarity of 0.25 s windows with voice in them)")
    if after <= before:
        print("the warp doesn't follow the song better than the plain sync; writing it anyway, but prefer the take as is")
    ts = np.arange(song_t[0], song_t[-1] + 1 / FPS, 1 / SR)    # the take's sound, re-timed like the picture
    sound = np.interp(np.interp(ts, song_t, clip_t) * SR, np.arange(len(take)), take).astype(np.float32)
    warp_video(src, CLIPS / f"{out}.mp4", clip_t, gray=False, sound=(sound, SR))
    made_too = [f"{out}.mp4"]
    for suffix in ("_matte", "_depth"):
        extra = CLIPS / f"{code}{suffix}.mp4"
        if extra.exists():
            warp_video(extra, CLIPS / f"{out}{suffix}.mp4", clip_t, gray=True)
            made_too.append(f"{out}{suffix}.mp4")
    (DATA / f"warp_{out}.json").write_text(json.dumps({"from": code, "song": song_t.round(4).tolist(),
                                                       "clip": clip_t.round(4).tolist()}))
    mouths[out] = {"sync": round(t0, 3), "warped_from": code}
    (DATA / "mouths.json").write_text(json.dumps(mouths, indent=1))
    print(f"wrote mv/clips/{', '.join(made_too)}; mv/data/warp_{out}.json; sync {t0:.2f} for {out} in mouths.json")
    print(f'place it with S("{out}", 0, beats, sync={t0:.2f}); check it with sync_offset.py mv/clips/{out}.mp4')


if __name__ == "__main__":
    main()
