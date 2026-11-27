#!/usr/bin/env python3
"""Smoke test for the engine: a synthetic song and test-pattern footage through the whole pipeline.

Usage: PYTHON engine/scripts/smoke_test.py [--keep] [--dir DIR]
PYTHON is an interpreter with engine/template/requirements.txt installed (a project's .venv/bin/python
works). Needs ffmpeg and a GPU with OpenGL 3.3. Run it before pointing ENGINE_REV in SKILL.md at a new
engine commit.

It builds a throwaway project (a 24 s song at 120 BPM with a quiet intro, two test-pattern clips), then
runs conform --check, analyze_song, gridcheck, audio_feats, edl (an edit generated on the grid, with a dissolve and a
double exposure, a shot with light shafts and one with a focus pull), contact --edl, render --stills (once with the empty fx.py, once with
examples/fx_examples.py), sheet, a full render, beatsheet, qc, heads, facecheck and contrastcheck (with
the empty fx.py and with the examples), readcheck and the font list, a vertical bar-locked part, a tracked screen (screen.py on a
clip with a dark panel moving through it, then a still with the panel filled), and concept_dice. It checks that every step exits cleanly and writes what it should, that the analyzer
finds the tempo, and that the render is as long as the song. It does not test lyrics transcription or
person mattes or depth maps (all three download large models; the depth treatments still compile and run
without a map). --keep leaves the project in place for a look.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

ENGINE = Path(__file__).resolve().parent.parent
BPM, DUR, SR = 120.0, 24.0, 44100

EDIT = '''
_end = round(beat_at(END), 3)
_shots, _k = [], 0.0
while _k < _end - 1e-6:
    _b = min(4.0 if _k < 16 else 2.0, _end - _k)
    _o = dict(x="dissolve", xd=1) if _k == 8 else dict(depth_fx="shafts", depth_at=(0.7, 0.2)) if _k == 4 else \
        dict(depth_fx="focus", depth_focus=(0.9, 0.3)) if _k == 12 else {}
    _shots.append(S("A1" if int(_k // 4) % 2 == 0 else "B1", 0.5 + 0.2 * len(_shots), _b,
                    size="WMCX"[len(_shots) % 4], motif=True, **_o))
    _k += _b
section(0, _shots)
OVER.append((8, 4, "B1", 2.0, dict(op=0.35, blend="screen")))
'''


def song(path):
    t = np.arange(int(DUR * SR)) / SR
    y = 0.05 * np.sin(2 * np.pi * 220 * t)
    rng = np.random.default_rng(1)
    n = int(0.12 * SR)
    tt = np.arange(n) / SR
    kick = np.sin(2 * np.pi * (110 * np.exp(-tt * 30) + 45) * tt) * np.exp(-tt * 28)
    hat = rng.standard_normal(int(0.03 * SR)) * np.exp(-np.arange(int(0.03 * SR)) / SR * 150)
    beat = 60.0 / BPM
    for k in range(int(DUR / beat)):
        i = int((0.25 + k * beat) * SR)
        loud = 0.25 if k < 16 else 0.9   # four quiet bars, then the kick comes in
        if i + n < len(y):
            y[i:i + n] += loud * kick
        j = i + int(beat / 2 * SR)
        if k >= 16 and j + len(hat) < len(y):
            y[j:j + len(hat)] += 0.15 * hat
    sf.write(path, np.clip(y, -1, 1), SR, subtype="PCM_16")


SCREEN_FX = """

def _magenta(t, shot):
    import numpy as np
    pic = np.zeros((90, 160, 3), np.uint8)
    pic[...] = (255, 0, 255)
    return pic


SCREENS = {"panel": _magenta}
"""


def screen_clip(path, n=48, w=640, h=360):
    """A dark panel drifting across a grey textured wall; returns its true corners per frame."""
    rng = np.random.default_rng(2)
    wall = (110 + 40 * rng.random((h // 8, w // 8))).astype(np.uint8)
    wall = np.kron(wall, np.ones((8, 8), np.uint8))
    base = np.array([[250, 100], [400, 108], [396, 250], [246, 242]], float)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                          "-r", "24", "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                         stdin=subprocess.PIPE)
    import cv2
    truth = []
    for k in range(n):
        q = base + [40 * k / (n - 1), 12 * k / (n - 1)]
        f = wall.copy()
        cv2.fillPoly(f, [q.round().astype(np.int32)], 10)
        p.stdin.write(f.tobytes())
        truth.append(q / [w, h])
    p.stdin.close()
    p.wait()
    return np.array(truth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()
    root = Path(args.dir or tempfile.mkdtemp(prefix="mv_smoke_")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    scripts = root / "mv" / "scripts"

    def run(*cmd):
        print("$", " ".join(str(c) for c in cmd), flush=True)
        r = subprocess.run([str(c) for c in cmd], cwd=root, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"FAILED ({r.returncode}): {' '.join(str(c) for c in cmd)}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        return r.stdout

    def need(*paths):
        for p in paths:
            hits = list(root.glob(p))
            if not hits or not all(h.stat().st_size for h in hits):
                sys.exit(f"FAILED: nothing written at {p}")

    shutil.copytree(ENGINE / "template" / "mv" / "scripts", scripts, dirs_exist_ok=True)
    for d in ("data", "clips", "archive", "review", "work/stills", "out"):
        (root / "mv" / d).mkdir(parents=True, exist_ok=True)
    (root / "footage").mkdir(exist_ok=True)
    song(root / "song.wav")
    for name, src in (("a", "testsrc2"), ("b", "smptebars")):
        run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=s=640x360:r=24:d=14",
            "-pix_fmt", "yuv420p", f"footage/{name}.mp4")
    print(run(py, "mv/scripts/conform.py", "footage/a.mp4", "footage/b.mp4", "--check"))   # clean clips: exit 0
    (root / "mv/data/codes.json").write_text(json.dumps({"A1": "footage/a.mp4", "B1": "footage/b.mp4"}))

    run(py, "mv/scripts/analyze_song.py", "song.wav", "--title", "Smoke", "--artist", "Test", "--force")
    cfg = json.loads((root / "mv/data/song.json").read_text())
    if abs(cfg["bpm"] - BPM) > 1.0:
        sys.exit(f"FAILED: analyzer found {cfg['bpm']} BPM for a {BPM:g} BPM song")
    print(run(py, "mv/scripts/gridcheck.py"))
    need("mv/review/grid_check.wav")
    run(py, "mv/scripts/audio_feats.py")
    need("mv/data/audio_feats.npz")

    edl = scripts / "edl.py"
    lines = edl.read_text().split("\n")
    at = max(i for i, ln in enumerate(lines) if ln.startswith("# ====") and "EDIT" not in ln)
    edl.write_text("\n".join(lines[:at + 1]) + "\n" + EDIT + "\n".join(lines[at + 1:]))
    print(run(py, "mv/scripts/edl.py"))
    need("mv/data/edl.json")
    run(py, "mv/scripts/contact.py", "mv/work/shots", "--edl")
    need("mv/work/shots_*.jpg")

    run(py, "mv/scripts/render.py", "mv/work/stills/s", "--stills", "4,10,16")
    need("mv/work/stills/s_*.jpg")
    run(py, "mv/scripts/sheet.py", "mv/work/stills/s", "mv/work/stills/sheet")
    need("mv/work/stills/sheet_0.jpg")
    empty_fx = (scripts / "fx.py").read_text()
    shutil.copy(ENGINE / "examples" / "fx_examples.py", scripts / "fx.py")
    run(py, "mv/scripts/render.py", "mv/work/stills/x", "--stills", "3,5.5,10,13.8,17.5,21.5")
    need("mv/work/stills/x_*.jpg")
    (scripts / "fx.py").write_text(empty_fx)

    run(py, "mv/scripts/render.py", "mv/out/smoke_v1.mp4")
    need("mv/out/smoke_v1.mp4")
    got = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "mv/out/smoke_v1.mp4"))
    if abs(got - cfg["duration"]) > 0.25:
        sys.exit(f"FAILED: the render is {got:.2f}s, the song {cfg['duration']:.2f}s")
    streams = run("ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", "mv/out/smoke_v1.mp4")
    if "audio" not in streams or "video" not in streams:
        sys.exit(f"FAILED: the render lacks a stream: {streams!r}")
    run(py, "mv/scripts/beatsheet.py", "mv/out/smoke_v1.mp4", "mv/work/beats.jpg", "8", "16")
    need("mv/work/beats.jpg")
    print(run(py, "mv/scripts/qc.py", "mv/out/smoke_v1.mp4", "--ignore-after", cfg["end"]))
    print(run(py, "mv/scripts/heads.py", "--size", "480x270"))
    need("mv/data/heads.json", "mv/review/heads_00.jpg")
    print(run(py, "mv/scripts/facecheck.py", "--size", "960x540"))
    print(run(py, "mv/scripts/contrastcheck.py", "--size", "960x540"))
    shutil.copy(ENGINE / "examples" / "fx_examples.py", scripts / "fx.py")   # placed, outlined captions pass both
    print(run(py, "mv/scripts/facecheck.py", "--size", "960x540", "--start", "3", "--end", "20"))
    print(run(py, "mv/scripts/contrastcheck.py", "--size", "960x540", "--start", "3", "--end", "20"))
    print(run(py, "mv/scripts/readcheck.py", "--size", "960x540"))
    print(run(py, "mv/scripts/fonts.py"))
    (scripts / "fx.py").write_text(empty_fx)
    run(py, "mv/scripts/render.py", "mv/out/smoke_hook.mp4", "--size", "1080x1920", "--start", "8", "--end", "16")
    need("mv/out/smoke_hook.mp4")
    run(py, ENGINE / "scripts" / "concept_dice.py", "--n", "1", "--seed", "1")

    truth = screen_clip(root / "footage/c.mp4")
    codes = json.loads((root / "mv/data/codes.json").read_text())
    (root / "mv/data/codes.json").write_text(json.dumps(dict(codes, C1="footage/c.mp4")))
    print(run(py, "mv/scripts/screen.py", "C1"))
    need("mv/data/screen_C1.json", "mv/review/screen_C1.jpg")
    tr = json.loads((root / "mv/data/screen_C1.json").read_text())
    off = np.abs(np.array(tr["quads"]) - truth[:len(tr["quads"])]) * [640, 360]
    if off.max() > 3 or not all(tr["ok"]):
        sys.exit(f"FAILED: screen track off by up to {off.max():.1f} px, {sum(tr['ok'])}/{len(tr['ok'])} frames ok")
    e = json.loads((root / "mv/data/edl.json").read_text())
    e["main"][0].update(src="C1", screen="panel", grade="orig")
    e["main"][0]["in"] = 0.0
    (root / "mv/data/edl.json").write_text(json.dumps(e))
    (scripts / "fx.py").write_text(empty_fx + SCREEN_FX)
    run(py, "mv/scripts/render.py", "mv/work/stills/scr", "--stills", "1")
    (scripts / "fx.py").write_text(empty_fx)
    from PIL import Image
    still = np.asarray(Image.open(next((root / "mv/work/stills").glob("scr_*.jpg"))).convert("RGB")).astype(float)
    H, W = still.shape[:2]
    cx, cy = (truth[24].mean(0) * [W, H]).round().astype(int)
    r, g, b = still[cy - 5:cy + 5, cx - 5:cx + 5].reshape(-1, 3).mean(0)
    if not (r > g + 60 and b > g + 60):
        sys.exit(f"FAILED: the tracked screen isn't filled at its centre (rgb {r:.0f},{g:.0f},{b:.0f})")

    print(f"OK: every step ran ({root})" if args.keep else "OK: every step ran")
    if not args.keep and not args.dir:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
