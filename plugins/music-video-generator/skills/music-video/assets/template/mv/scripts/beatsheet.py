"""Tile one frame per beat from a rendered video: beatsheet.py VIDEO OUT T0 N [STEP]"""
import subprocess
import sys

video, out, t0, n = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
step = float(sys.argv[5]) if len(sys.argv) > 5 else 0.48
sel = "+".join(f"between(t,{t0 + k * step - 0.02:.3f},{t0 + k * step + 0.02:.3f})" for k in range(n))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", f"select='{sel}',scale=480:270,tile=4x{(n + 3) // 4}",
                "-frames:v", "1", "-fps_mode", "vfr", out], check=True)
print(out)
