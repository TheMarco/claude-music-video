"""Person matte per frame with rembg (u2net_human_seg), written as a grayscale video.

Usage: .venv/bin/python mv/scripts/make_matte.py CLIP.mp4 [CLIP2.mp4 ...]
Writes <clip>_matte.mp4 next to each clip. For AI clips run it once per clip after download; the
compositor then cuts matching matte segments automatically. Archive shots get mattes per segment
when the EDL shot has matte=True (render.py calls matte_video on the prepared segment).
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_sess = None


def matte_video(clip, out, log=True):
    global _sess
    from rembg import new_session, remove
    if _sess is None:
        _sess = new_session("u2net_human_seg")
    clip, out = Path(clip), Path(out)
    w, h = map(int, subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                             "stream=width,height", "-of", "csv=p=0", str(clip)]).decode().split(",")[:2])
    fps = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=r_frame_rate", "-of", "csv=p=0", str(clip)]).decode().strip()
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(clip), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                            "-r", fps, "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(out)],
                           stdin=subprocess.PIPE)
    for i, f in enumerate(frames):
        m = remove(Image.fromarray(f), session=_sess, only_mask=True, post_process_mask=True)
        enc.stdin.write(np.asarray(m.convert("L"), np.uint8).tobytes())
        if log and i % 48 == 0:
            print(f"{clip.name} {i}/{len(frames)}", flush=True)
    enc.stdin.close()
    enc.wait()
    if log:
        print("wrote", out)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        c = Path(arg)
        matte_video(c, c.with_name(c.stem + "_matte.mp4"))
