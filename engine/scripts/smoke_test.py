#!/usr/bin/env python3
"""Smoke test for the engine: a synthetic song and test-pattern footage through the whole pipeline.

Usage: PYTHON engine/scripts/smoke_test.py [--keep] [--dir DIR]
PYTHON is an interpreter with engine/template/requirements.txt installed (a project's .venv/bin/python
works). Needs ffmpeg and a GPU with OpenGL 3.3. Run it before pointing ENGINE_REV in SKILL.md at a new
engine commit.

It builds a throwaway project (a 24 s song at 120 BPM with a quiet intro, two test-pattern clips), then
runs conform --check, analyze_song, gridcheck, audio_feats, edl (an edit generated on the grid, with a dissolve and a
double exposure), contact --edl, render --stills (once with the empty fx.py, once with
examples/fx_examples.py), sheet, a full render, beatsheet, qc, heads, facecheck and contrastcheck (with
the empty fx.py and with the examples), a vertical bar-locked part with a narrow_x shot, and concept_dice.
Then the lip-sync tools on a synthetic vocal and a take that stretches one of its pauses (sync_offset
finds both offsets, warp_take re-times the take, and sync_offset finds the result steady at its new
start), align_lyrics with timed section labels on a repeated chorus, and track_screen and bake_screen on
a moving dark quad with known corners. It checks that every step exits cleanly and writes what it should, that the analyzer
finds the tempo, and that the render is as long as the song. It does not test lyrics transcription or
person mattes or depth maps (all three download large models; the depth treatments still compile and run
without a map). --keep leaves the project in place for a look.
"""
import argparse
import json
import re
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
    _o = dict(x="dissolve", xd=1) if _k == 8 else {}
    _shots.append(S("A1" if int(_k // 4) % 2 == 0 else "B1", 0.5 + 0.2 * len(_shots), _b,
                    size="WMCX"[len(_shots) % 4], motif=True, **_o))
    _k += _b
section(0, _shots)
_shots[2][3]["narrow_x"] = 0.2
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


def vocal(path):
    """A made-up vocal: syllables of random pitch, with one long pause at 4.0-4.5 s."""
    rng = np.random.default_rng(7)
    y = np.zeros(int(10.0 * SR))
    t = 0.3
    while t < 9.6:
        if 3.9 < t < 4.5:
            t = 4.5
        d = rng.uniform(0.12, 0.35)
        n = int(d * SR)
        tt = np.arange(n) / SR
        f0 = rng.uniform(120, 400)
        env = np.sin(np.pi * np.arange(n) / n) ** 0.5
        syl = sum(np.sin(2 * np.pi * f0 * h * tt) / h for h in range(1, 6)) * env
        i = int(t * SR)
        y[i:i + n] += 0.25 * syl[:len(y) - i]
        t += d + rng.uniform(0.04, 0.14)
    sf.write(path, y, SR, subtype="PCM_16")
    return y


def screen_clip(path, frames=72, w=640, h=360):
    """A dark quad that drifts, grows and turns on a lit, textured background; returns its true corners."""
    import cv2
    rng = np.random.default_rng(3)
    bg = (170 + 40 * rng.random((h, w))).astype(np.uint8)
    bg = cv2.GaussianBlur(bg, (0, 0), 2)
    truth = []
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                            "-r", "24", "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(path)],
                           stdin=subprocess.PIPE)
    for k in range(frames):
        u = k / (frames - 1)
        c = np.array([260 + 80 * u, 170 - 20 * u])
        a = np.radians(-4 + 10 * u)
        sw, sh = 120 * (1 + 0.3 * u), 90 * (1 + 0.3 * u)
        R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        q = np.array([[-sw, -sh], [sw, -sh], [sw, sh], [-sw, sh]]) / 2 @ R.T + c
        im = bg.copy()
        cv2.fillPoly(im, [np.round(q * 16).astype(np.int32)], 22, lineType=cv2.LINE_AA, shift=4)
        enc.stdin.write(im.tobytes())
        truth.append(q / [w, h])
    enc.stdin.close()
    enc.wait()
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
    run(py, "mv/scripts/render.py", "mv/work/stills/x", "--stills", "10,13,17.5")
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
    need("mv/data/heads.json", "mv/review/heads_00.jpg", "mv/review/heads_count.txt")
    print(run(py, "mv/scripts/facecheck.py", "--size", "960x540"))
    print(run(py, "mv/scripts/contrastcheck.py", "--size", "960x540"))
    shutil.copy(ENGINE / "examples" / "fx_examples.py", scripts / "fx.py")   # placed, outlined captions pass both
    print(run(py, "mv/scripts/facecheck.py", "--size", "960x540", "--start", "3", "--end", "20"))
    print(run(py, "mv/scripts/contrastcheck.py", "--size", "960x540", "--start", "3", "--end", "20"))
    (scripts / "fx.py").write_text(empty_fx)
    if not any("narrow_x" in x for x in json.loads((root / "mv/data/edl.json").read_text())["main"]):
        sys.exit("FAILED: narrow_x didn't reach edl.json")
    run(py, "mv/scripts/render.py", "mv/out/smoke_hook.mp4", "--size", "1080x1920", "--start", "8", "--end", "16")
    need("mv/out/smoke_hook.mp4")
    run(py, ENGINE / "scripts" / "concept_dice.py", "--n", "1", "--seed", "1")

    # Lip sync: a take that follows the vocal from 1.0 s, then stretches the pause at 4.0-4.5 s by 0.4 s.
    y = vocal(root / "vocal.wav")
    take = np.concatenate([y[int(1.0 * SR):int(4.2 * SR)], np.zeros(int(0.4 * SR)), y[int(4.2 * SR):int(9.4 * SR)]])
    sf.write(root / "take.wav", take, SR, subtype="PCM_16")
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=640x360:r=24:d={len(take) / SR:.3f}",
        "-i", "take.wav", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "mv/clips/L1.mp4")
    print(run(py, "mv/scripts/sync_offset.py", "mv/clips/L1.mp4", "--song", "vocal.wav", "--save"))
    m = json.loads((root / "mv/data/mouths.json").read_text())["L1"]
    syncs = sorted([m["sync"]] + [x[2] for x in m.get("also", [])])
    if not (any(abs(x - 0.6) < 0.06 for x in syncs) and any(abs(x - 1.0) < 0.06 for x in syncs)):
        sys.exit(f"FAILED: sync_offset should find the take at sync 1.0 and 0.6, found {syncs}")
    print(run(py, "mv/scripts/warp_take.py", "L1", "1.5", "8.5", "--song", "vocal.wav"))
    out = run(py, "mv/scripts/sync_offset.py", "mv/clips/L1w.mp4", "--song", "vocal.wav")
    print(out)
    start, sim = [float(x) for x in re.search(r"song time ([0-9.]+)s \(similarity ([0-9.]+)", out).groups()]
    if abs(start - 1.5) > 0.05 or sim < 0.6:
        sys.exit(f"FAILED: the warped take should start at 1.5 s and follow the vocal, found {start} at {sim}")
    need("mv/clips/L1w.mp4", "mv/data/warp_L1w.json")

    # Lyrics: a chorus sung twice, the second time half heard; timed labels keep each on its own stretch.
    heard = [{"start": 1.5, "end": 3.0, "text": "la la go", "words": [
                 {"w": "la", "start": 1.5, "end": 1.9}, {"w": "la", "start": 2.0, "end": 2.4}, {"w": "go", "start": 2.5, "end": 3.0}]},
             {"start": 4.5, "end": 6.0, "text": "one two three", "words": [
                 {"w": "one", "start": 4.5, "end": 4.9}, {"w": "two", "start": 5.0, "end": 5.4}, {"w": "three", "start": 5.5, "end": 6.0}]},
             {"start": 8.6, "end": 9.0, "text": "go", "words": [{"w": "go", "start": 8.6, "end": 9.0}]}]
    (root / "mv/data/lyrics_whisper.json").write_text(json.dumps(heard))
    (root / "lyrics.txt").write_text("[chorus @1.0]\nla la go\n[verse @4.0]\none two three\n[chorus @7.5]\nla la go\n")
    print(run(py, "mv/scripts/align_lyrics.py", "lyrics.txt"))
    lines = json.loads((root / "mv/data/lyrics.json").read_text())
    if len(lines) != 3 or lines[2]["start"] < 7.5 or lines[0]["start"] > 2.0:
        sys.exit(f"FAILED: timed labels should keep each chorus in its stretch: {[ln['start'] for ln in lines]}")

    # A screen: track a dark quad with known corners, then bake a panel onto it.
    truth = screen_clip(root / "mv/clips/SC.mp4")
    q0 = ",".join(f"{v:.4f}" for v in truth[0].ravel())
    print(run(py, "mv/scripts/track_screen.py", "SC", "--quad", q0))
    got = np.array(json.loads((root / "mv/data/screen_SC.json").read_text())["quads"])
    err = np.abs(got[:len(truth)] - truth).max()
    if err > 0.012:
        sys.exit(f"FAILED: track_screen is off the true corners by up to {err:.3f} of the frame")
    import cv2
    cv2.imwrite(str(root / "panel.png"), np.full((300, 400, 3), (40, 180, 250), np.uint8))
    print(run(py, "mv/scripts/bake_screen.py", "SC", "--panel", "panel.png"))
    need("mv/clips/SCs.mp4", "mv/review/screen_SC.jpg")

    print(f"OK: every step ran ({root})" if args.keep else "OK: every step ran")
    if not args.keep and not args.dir:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
