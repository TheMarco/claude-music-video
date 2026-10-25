"""Overlay layers, drawn per frame with PIL. The engine draws nothing by itself: every title, word,
caption and graphic comes from this video's fx.py (draw_behind, draw_front), designed for its concept.

Overlay(W, H).frame(t, ctx) returns (behind, front): RGBA uint8 arrays (straight alpha) or None.
"behind" is composited under the person matte, so anything drawn there sits behind the performer;
"front" goes over everything. ctx carries the current shot: src code, label, local time, duration.

Helpers for fx.py, all sized in 1080p units so one design works at 16:9, 9:16, 1:1 and 4:5:
  ov.w, ov.h, ov.s (short side / 1080), ov.wide (aspect > 1.5)
  ov.font((path, index), size)                    cached ImageFont at size * ov.s
  ov.fit((path, index), size, text, track, maxw)  the same, shrunk until the text fits maxw
  ov.tracked(d, xy, text, font, fill, track, anchor="mm"|"lm", stroke=0, stroke_fill=None)
  ov.layer(canvas, fill, mask, alpha)             composite a color/image through an L mask
  ov.gradient(top, bottom)                        full-frame vertical gradient image (cached)
  ov.kick_level(t), ov.letterboxed(t), ov.fi(t)   section energy, letterbox state, frame index
  ov.lines, ov.lyric_at(t)                        lyrics.json lines (suspect ones skipped) and the
                                                  line and word being sung at t
  audio arrays indexed by frame f: ov.spec (48 bands), ov.peaks (falling peak hold), ov.rms, ov.kick,
  ov.snare, ov.hat, ov.wave (256-sample waveform); onset times ov.kicks, ov.snares
Module helpers: hash01(*key) for stable per-frame randomness, keyframes(t, [(t, v), ...]), and F / FS,
the macOS system font folders.
"""
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from look import FINISH  # noqa: E402
from timing import FPS  # noqa: E402

F = "/System/Library/Fonts/"                    # macOS system fonts
FS = "/System/Library/Fonts/Supplemental/"
FONT_DIRS = [Path(F), Path(FS), Path("/Library/Fonts"), Path.home() / "Library/Fonts",
             Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
             Path.home() / ".local/share/fonts", Path("C:/Windows/Fonts")]
_FONT_INDEX = {}


def font_path(path):
    """path if it exists, else a font with the same file name in a system font folder, else a fallback
    (DejaVu Sans, Arial, Helvetica), so fx.py written on one system still renders on another."""
    if Path(path).exists():
        return path
    if not _FONT_INDEX:
        for d in FONT_DIRS:
            if d.is_dir():
                for f in d.rglob("*"):
                    if f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                        _FONT_INDEX.setdefault(f.name.lower(), str(f))
    for name in (Path(path).name, "DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "Helvetica.ttc"):
        if name.lower() in _FONT_INDEX:
            return _FONT_INDEX[name.lower()]
    raise FileNotFoundError(f"font {path} not found, and no fallback font in {[str(d) for d in FONT_DIRS]}")


def hash01(*a):
    return random.Random(hash(a) & 0xFFFFFFFF).random()


def keyframes(t, pts):
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if a <= t < b:
            return va + (vb - va) * (t - a) / (b - a)
    return pts[-1][1]


class Overlay:
    def __init__(self, w, h, feats="mv/data/audio_feats.npz"):
        import fx  # here rather than at the top, so fx.py can import this module's helpers
        self.fx = fx
        self.w, self.h = w, h
        self.s = min(w, h) / 1080
        self.wide = w / h > 1.5
        self._fonts = {}
        self._grad = {}
        self.lines = self._load_lyrics()
        a = np.load(feats)
        self.spec, self.rms, self.kick = a["spec"], a["rms"], a["kick"]
        self.snare, self.hat, self.wave = a["snare"], a["hat"], a["wave"]
        self.peaks = self._peaks(self.spec)
        self.kicks = self._onsets(self.kick, 0.55, 0.22)
        self.snares = self._onsets(self.snare, 0.6, 0.18)

    # ---- precompute -------------------------------------------------------
    @staticmethod
    def _peaks(spec):
        pk = np.zeros_like(spec)
        hold = np.zeros(spec.shape[1])
        for i in range(len(spec)):
            hold = np.maximum(spec[i], hold - 0.018)
            pk[i] = hold
        return pk

    @staticmethod
    def _onsets(env, thr, gap):
        out, last = [], -9.0
        for i in range(1, len(env) - 1):
            t = i / FPS
            if env[i] >= thr and env[i] >= env[i - 1] and env[i] >= env[i + 1] and t - last >= gap:
                out.append(t)
                last = t
        return np.array(out)

    @staticmethod
    def _load_lyrics():
        f = Path("mv/data/lyrics.json")
        return [ln for ln in json.loads(f.read_text()) if not ln.get("suspect")] if f.exists() else []

    # ---- helpers ----------------------------------------------------------
    def fi(self, t):
        return int(min(max(round(t * FPS), 0), len(self.rms) - 1))

    def font(self, spec, size):
        path, idx = spec
        px = int(size * self.s)
        if (spec, px) not in self._fonts:
            self._fonts[(spec, px)] = ImageFont.truetype(font_path(path), px, index=idx)
        return self._fonts[(spec, px)]

    def fit(self, spec, size, text, track, maxw):
        """Font spec at size (1080p units), shrunk until text with tracking fits maxw."""
        path, idx = spec
        px = int(size * self.s)
        while px > 8:
            ck = (spec, px)
            if ck not in self._fonts:
                self._fonts[ck] = ImageFont.truetype(font_path(path), px, index=idx)
            f = self._fonts[ck]
            if sum(f.getlength(c) for c in text) + track * (len(text) - 1) <= maxw:
                return f
            px = int(px * 0.92)
        return self._fonts[ck]

    def tracked(self, d, xy, text, fnt, fill, track, anchor="mm", stroke=0, stroke_fill=None):
        widths = [fnt.getlength(c) for c in text]
        total = sum(widths) + track * (len(text) - 1)
        x, y = xy
        if anchor[0] == "m":
            x -= total / 2
        for c, wd in zip(text, widths):
            d.text((x, y), c, font=fnt, fill=fill, anchor="lm", stroke_width=stroke, stroke_fill=stroke_fill)
            x += wd + track
        return total

    def layer(self, canvas, fill, mask, scale):
        src = fill if isinstance(fill, Image.Image) else Image.new("RGB", canvas.size, fill)
        lay = src.convert("RGBA")
        lay.putalpha(mask.point(lambda v: int(v * scale)))
        canvas.alpha_composite(lay)

    def gradient(self, top, bottom):
        key = (top, bottom)
        if key not in self._grad:
            g = np.linspace(0, 1, self.h)[:, None, None]
            arr = (np.array(top) * (1 - g) + np.array(bottom) * g).astype(np.uint8)
            self._grad[key] = Image.fromarray(np.repeat(arr, self.w, 1), "RGB")
        return self._grad[key]

    def kick_level(self, t):
        """The section's kick level at t (0 calm .. 1 peak), for gating effects by energy."""
        from timing import section
        return section(t)[1]

    def letterboxed(self, t):
        return self.wide and any(a <= t < b for a, b in FINISH["letterbox"])

    def lyric_at(self, t):
        """(line, word_index) being sung at t, or (None, -1). word_index is -1 between words or when
        the line has no word timings."""
        for ln in self.lines:
            if ln["start"] <= t < ln["end"]:
                for i, w in enumerate(ln.get("words", [])):
                    if w["start"] <= t < w["end"]:
                        return ln, i
                return ln, -1
        return None, -1

    # ---- main -------------------------------------------------------------
    def frame(self, t, ctx=None):
        ctx = ctx or {}
        f = self.fi(t)
        behind = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.fx.draw_behind(self, behind, t, f, ctx)
        front = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.fx.draw_front(self, ImageDraw.Draw(front), t, f, ctx)
        b = np.asarray(behind) if behind.getbbox() else None
        fr = np.asarray(front) if front.getbbox() else None
        return b, fr
