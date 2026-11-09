"""Tile one frame per beat from a full-length render, to see how the picture lands on the beats.

Usage: .venv/bin/python mv/scripts/beatsheet.py VIDEO OUT.jpg SONG_TIME N [STEP]
Starts at the beat nearest SONG_TIME and takes N beats from the song's grid (timing.py, so it follows
any tempo and a drifting beat map), each on the video frame that shows that beat: the frame at or
before it. STEP, when given, is a number of beats between frames (0.5 for half beats, 4 for one frame
per bar). VIDEO has to start at song time 0, so use a full render, not a --start/--end part.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS, beat, beat_at, on_frame  # noqa: E402

if len(sys.argv) < 5:
    sys.exit(__doc__)
video, out, t0, n = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
step = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
k0 = round(beat_at(t0))
half = 0.45 / FPS
times = [on_frame(beat(k0 + i * step)) for i in range(n)]
sel = "+".join(f"between(t,{t - half:.4f},{t + half:.4f})" for t in times)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", f"select='{sel}',scale=480:270,tile=4x{(n + 3) // 4}",
                "-frames:v", "1", "-fps_mode", "vfr", out], check=True)
print(f"{out}: {n} frames from beat {k0} ({times[0]:.2f}s) to {times[-1]:.2f}s")
