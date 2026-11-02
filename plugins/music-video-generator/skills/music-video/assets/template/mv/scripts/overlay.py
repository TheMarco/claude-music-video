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
  ov.glyphs(text, font, track)                    [(char, x, width), ...] and the total width, for
                                                  letters that move one by one
  ov.streak(d, xy, v, width, fill, shutter=0.5)   a moving particle drawn as its motion-blur streak
                                                  (v in pixels per second; 0.5 = a 180-degree shutter)
  ov.track(name, ctx)                             (x, y) in pixels of a point tracked by track.py in the
                                                  current shot, following its zoom, pan and shake; None
                                                  in other shots or where the track is lost
  ov.to_screen(ctx, x, y)                         pixels of any point of the current shot's frame
                                                  (0..1 from the top left of the cut 16:9 segment)
Module helpers: hash01(*key) for stable per-frame randomness, F / FS (the macOS system font folders),
and from motion.py: keyframes(t, pts, ease), the easing curves (ease_out, ease_in, ease_in_out,
ease_out_back, ease_out_expo, ease_in_expo, ease), since, hit and stagger.
Draw everything from t (and f) alone, never from state kept between frames: --stills renders only a
few frames around each still, so anything accumulated frame by frame would differ from the full render.
"""
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from look import FINISH  # noqa: E402
from motion import (ease, ease_in, ease_in_expo, ease_in_out, ease_out, ease_out_back,  # noqa: E402,F401
                    ease_out_expo, hit, keyframes, linear, seg_time, seg_to_screen, since, stagger)
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
        self._tracks = {}

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

    def glyphs(self, text, fnt, track=0.0):
        """([(char, x, width), ...], total width): x of each letter from the start of the text."""
        out, x = [], 0.0
        for c in text:
            w = fnt.getlength(c)
            out.append((c, x, w))
            x += w + track
        return out, x - track if text else 0.0

    def streak(self, d, xy, v, width, fill, shutter=0.5):
        """A moving particle as film sees it: a streak from xy back along its velocity v (pixels per
        second) for shutter / FPS seconds, with a round head. Rain, sparks and debris read as motion
        this way; dots read as specks."""
        x, y = xy
        dx, dy = v[0] * shutter / FPS, v[1] * shutter / FPS
        wd = max(1, int(round(width)))
        d.line((x - dx, y - dy, x, y), fill=fill, width=wd)
        r = width / 2
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    # ---- tracked points (track.py) -----------------------------------------
    def _track(self, name):
        if name not in self._tracks:
            f = Path("mv/data/tracks") / f"{name}.json"
            self._tracks[name] = json.loads(f.read_text()) if f.exists() else None
        return self._tracks[name]

    def track_seg(self, name, shot, local):
        """Tracked point in the shot's cut frame (0..1 from the top left), or None."""
        tr = self._track(name)
        if not tr or not shot or Path(shot.get("file", "")).name != tr["file"]:
            return None
        pts = tr["points"]
        x, y, ok = pts[min(max(int(round(seg_time(shot, local) * tr["fps"])), 0), len(pts) - 1)]
        return (x, y) if ok else None

    def track(self, name, ctx):
        """(x, y) in output pixels of track NAME in the current shot, or None."""
        p = self.track_seg(name, ctx.get("shot"), ctx.get("local", 0.0))
        return None if p is None else self.to_screen(ctx, *p)

    def track_uv(self, name, shot, local):
        """The same in shader uv (0..1, y up), for fx.uniforms via a["track"](name)."""
        p = self.track_seg(name, shot, local)
        if p is None:
            return None
        x, y = seg_to_screen(shot, local, p[0], p[1], self.w / self.h)
        return (x, 1.0 - y)

    def to_screen(self, ctx, x, y):
        sx, sy = seg_to_screen(ctx["shot"], ctx.get("local", 0.0), x, y, self.w / self.h)
        return sx * self.w, sy * self.h

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
