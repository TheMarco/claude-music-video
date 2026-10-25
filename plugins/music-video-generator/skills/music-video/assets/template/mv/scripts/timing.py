"""Song timing, loaded from mv/data/song.json (written by analyze_song.py, then checked and edited by hand).

Everything time-based in the pipeline (EDL, compositor, overlays) imports from here, so the beat grid,
sections, drops and letterbox stretches live in one place. A fixed grid comes from bpm and t0; a song
whose tempo drifts gets a "beats" list (beat times in seconds) and beat(k) follows it.
"""
import bisect
import json
import math
from pathlib import Path

_CFG = json.loads((Path("mv") / "data" / "song.json").read_text())

SONG = _CFG["song"]
TITLE = _CFG.get("title", "")
ARTIST = _CFG.get("artist", "")
FPS = int(_CFG.get("fps", 24))
BPM = float(_CFG["bpm"])
BEAT = 60.0 / BPM
T0 = float(_CFG.get("t0", 0.0))
DUR = float(_CFG["duration"])
NFRAMES = int(math.ceil(DUR * FPS))
END = float(_CFG.get("end") or DUR + 1.0)          # end card starts here; past DUR means no end card
DROPS = [float(x) for x in _CFG.get("drops", [])]  # white flash + shockwave
SHOCKS = [(float(a), float(b)) for a, b in _CFG.get("shocks", [[d, 0.09] for d in DROPS])]
LETTERBOX = [(float(a), float(b)) for a, b in _CFG.get("letterbox", [])]
COUNTDOWNS = [float(x) for x in _CFG.get("countdowns", [])]  # 8-beat film-leader countdown start times

# (start, end, name, kick, calm) in seconds; kick 0..1 scales beat pulses, calm marks quiet sections
SECTIONS = [(float(s["start"]), float(s["end"]), s["name"], float(s.get("kick", 0.3)), bool(s.get("calm", False)))
            for s in _CFG["sections"]]


BEATS = [float(b) for b in _CFG.get("beats", [])]
if BEATS:
    T0 = BEATS[0]
    BEAT = (BEATS[-1] - BEATS[0]) / (len(BEATS) - 1)  # average, for durations and easing only


def beat(k):
    """Time in seconds of beat k (fractional k allowed)."""
    if not BEATS:
        return T0 + k * BEAT
    if k <= 0:
        return BEATS[0] + k * (BEATS[1] - BEATS[0])
    i = int(math.floor(k))
    if i >= len(BEATS) - 1:
        return BEATS[-1] + (k - len(BEATS) + 1) * (BEATS[-1] - BEATS[-2])
    return BEATS[i] + (k - i) * (BEATS[i + 1] - BEATS[i])


def beat_at(t):
    """Fractional beat index at time t (inverse of beat)."""
    if not BEATS:
        return (t - T0) / BEAT
    i = bisect.bisect_right(BEATS, t) - 1
    if i < 0:
        return (t - BEATS[0]) / (BEATS[1] - BEATS[0])
    if i >= len(BEATS) - 1:
        return len(BEATS) - 1 + (t - BEATS[-1]) / (BEATS[-1] - BEATS[-2])
    return i + (t - BEATS[i]) / (BEATS[i + 1] - BEATS[i])


def section(t):
    """(name, kick, start, end) of the section at time t."""
    for a, b, name, kick, _ in SECTIONS:
        if a <= t < b:
            return name, kick, a, b
    return "end", 0.0, END, DUR


def is_calm(t):
    for a, b, _, _, calm in SECTIONS:
        if a <= t < b:
            return calm
    return True


def beat_phase(t):
    """Seconds since the most recent beat, and that beat's index."""
    k = math.floor(beat_at(t) + 1e-9)
    return t - beat(k), k
