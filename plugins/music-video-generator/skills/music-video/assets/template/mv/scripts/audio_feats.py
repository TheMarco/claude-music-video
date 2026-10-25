"""Per-video-frame audio features for audio-reactive overlays.

Usage: .venv/bin/python mv/scripts/audio_feats.py
Writes mv/data/audio_feats.npz with, per frame at 24 fps:
  spec  (N, 48) log-spaced band levels 0..1 (smoothed: fast attack, slow release)
  rms   (N,)    loudness 0..1
  kick  (N,)    low-band transient envelope 0..1
  snare (N,)    mid-band transient envelope 0..1
  hat   (N,)    high-band transient envelope 0..1
  wave  (N, 256) waveform snippet around each frame, -1..1
"""
import sys
from pathlib import Path

import librosa
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS, NFRAMES, SONG  # noqa: E402

SR = 44100
y, _ = librosa.load(SONG, sr=SR, mono=True)
hop = SR // FPS  # one STFT column per video frame
S = np.abs(librosa.stft(y, n_fft=4096, hop_length=hop, center=True))[:, :NFRAMES]
if S.shape[1] < NFRAMES:
    S = np.pad(S, ((0, 0), (0, NFRAMES - S.shape[1])))
freqs = librosa.fft_frequencies(sr=SR, n_fft=4096)

edges = np.geomspace(35, 16000, 49)
idx = np.searchsorted(freqs, edges)
bands = np.stack([S[a:max(b, a + 1)].mean(0) for a, b in zip(idx[:-1], idx[1:])], 1)
db = librosa.amplitude_to_db(bands, ref=np.max)
spec = np.clip((db + 60) / 60, 0, 1)
sm = np.zeros_like(spec)
for i in range(1, NFRAMES):  # fast attack, slow release, like a hardware analyzer
    sm[i] = np.maximum(spec[i], sm[i - 1] * 0.82)
sm[0] = spec[0]


def env(lo, hi, decay):
    e = S[(freqs >= lo) & (freqs < hi)].sum(0)
    d = np.maximum(0, np.diff(e, prepend=e[0]))
    d = d / (np.percentile(d, 99.5) + 1e-9)
    out = np.zeros_like(d)
    for i in range(len(d)):
        out[i] = max(min(d[i], 1.0), (out[i - 1] if i else 0) * decay)
    return out


rms = librosa.feature.rms(y=y, frame_length=4096, hop_length=hop)[0][:NFRAMES]
rms = np.pad(rms, (0, max(0, NFRAMES - len(rms))))
rms = rms / rms.max()
wave = np.zeros((NFRAMES, 256), np.float32)
for i in range(NFRAMES):
    c = int(i * hop)
    seg = y[c:c + 2048]
    if len(seg) == 2048:
        wave[i] = seg[::8] / (np.abs(y).max() + 1e-9)
np.savez_compressed("mv/data/audio_feats.npz", spec=sm.astype(np.float32), rms=rms.astype(np.float32),
                    kick=env(30, 120, 0.80).astype(np.float32), snare=env(180, 2500, 0.75).astype(np.float32),
                    hat=env(6000, 16000, 0.70).astype(np.float32), wave=wave)
print("frames", NFRAMES, "spec", sm.shape, "kick mean", env(30, 120, 0.8).mean().round(3))
