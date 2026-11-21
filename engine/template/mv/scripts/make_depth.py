"""Depth map per frame with Depth Anything V2 Small, written as a grayscale video (near is white).

Usage: .venv/bin/python mv/scripts/make_depth.py CLIP.mp4 [CLIP2.mp4 ...] [--short 392]
Writes <clip>_depth.mp4 next to each clip. Run it once per AI clip that a shot's depth treatment or
behind_depth uses (references/compositor.md, "Depth"); the compositor then cuts matching depth segments
automatically, like mattes. Archive shots get depth per segment when the EDL shot has depth=True (render.py
calls depth_video on the prepared segment).

The model runs on CPU through onnxruntime (installed with rembg) at --short pixels on the short side
(a multiple of 14; 392 is about 0.25 s a frame on an M-series Mac). Depth is relative: each clip is
normalized over all its frames (2nd to 98th percentile) and smoothed over time so it doesn't flicker.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
_sess = None


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        from models import depth_path
        _sess = ort.InferenceSession(str(depth_path()), providers=["CPUExecutionProvider"])
    return _sess


def _probe(clip):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(clip)]).decode()
    w, h, fps = out.strip().split(",")[:3]
    return int(w), int(h), fps


def depth_video(clip, out, log=True, short=392, smooth=0.3):
    """Write out: clip's depth per frame (gray, near = 255) at the clip's size."""
    clip, out = Path(clip), Path(out)
    w, h, fps = _probe(clip)
    short = max(14, int(short) // 14 * 14)
    if w >= h:
        ih, iw = short, max(14, int(round(short * w / h / 14)) * 14)
    else:
        iw, ih = short, max(14, int(round(short * h / w / 14)) * 14)
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"scale={iw}:{ih}:flags=bicubic",
                                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, ih, iw, 3)
    sess = _session()
    name = sess.get_inputs()[0].name
    deps = np.empty((len(frames), ih, iw), np.float32)
    for i in range(0, len(frames), 4):
        x = (frames[i:i + 4].astype(np.float32) / 255.0 - MEAN) / STD
        deps[i:i + 4] = sess.run(None, {name: x.transpose(0, 3, 1, 2).copy()})[0][:, :ih, :iw]
        if log and i % 48 == 0:
            print(f"{clip.name} {i}/{len(frames)}", flush=True)
    sample = deps[:, ::4, ::4]
    lo, hi = np.percentile(sample, 2), np.percentile(sample, 98)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{iw}x{ih}",
                            "-r", fps, "-i", "-", "-vf", f"scale={w}:{h}:flags=bicubic", "-c:v", "libx264",
                            "-crf", "12", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    prev = None
    for d in deps:
        d = np.clip((d - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
        prev = d if prev is None else (1 - smooth) * d + smooth * prev   # a little memory: no flicker
        enc.stdin.write((prev * 255 + 0.5).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    if log:
        print("wrote", out)


if __name__ == "__main__":
    args, short = sys.argv[1:], 392
    if "--short" in args:
        k = args.index("--short")
        short = int(args[k + 1])
        del args[k:k + 2]
    sys.path.insert(0, str(Path(__file__).parent))
    for arg in args:
        c = Path(arg)
        depth_video(c, c.with_name(c.stem + "_depth.mp4"), short=short)
