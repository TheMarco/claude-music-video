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
Faces (mv/data/heads.json from heads.py; without it these see no faces and say so once):
  ov.heads(t, pad=True)                           head boxes on screen at t, px rects, padded by HEAD_PAD
  ov.touches_face(rect, t)                        True when rect touches an unpadded head box at t
  ov.place(key, t0, t1, bw, bh, xs, prefer, t)    (x, centre y, scale) for a bw x bh block held from t0 to
                                                  t1, clear of every head and every block placed before it:
                                                  one spot for the whole span when there is one, else one
                                                  per shot (it moves on the cut), a wider band and smaller
                                                  sizes before giving up. Cached per key; misses land in
                                                  ov.place_misses, which facecheck.py reports.
  ov.backdrop(rect, t)                            the bare picture under rect at t (heads.py's clean
                                                  frames): {"mean", "low", "high"} relative luminance
                                                  (mean, 10th, 90th percentile), or None without them
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
from timing import FPS, on_frame  # noqa: E402

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
        self._load_heads()

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
        """The section's kick level at t (0 calm .. 1 peak), for gating effects by energy. Like the engine, it
        switches on the frame at or before the section's start, the frame its first cut lands on."""
        from timing import HIT_LEAD, section
        return section(t + HIT_LEAD)[1]

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

    # ---- faces --------------------------------------------------------------
    HEAD_PAD = (0.03, 0.022)               # fraction of width, height: clears text shadows and pop overshoot
    BANDS = ((0.10, 0.80), (0.05, 0.94))   # the feed's safe band, then the wider band a face can force

    def _load_heads(self):
        p, e = Path("mv/data/heads.json"), Path("mv/data/edl.json")
        self._heads = json.loads(p.read_text())["frames"] if p.exists() else None
        self._cuts = sorted({on_frame(s["start"]) for s in json.loads(e.read_text())["main"]}) if e.exists() else []
        self._placed, self._reg, self.place_misses, self._warned = {}, [], [], False

    def heads(self, t, pad=True):
        """Head boxes on screen at frame time t, as (x0, y0, x1, y1) px rects."""
        if self._heads is None:
            if not self._warned:
                print("overlay: no mv/data/heads.json, so nothing is kept clear of faces (run heads.py)")
                self._warned = True
            return []
        px, py = self.HEAD_PAD if pad else (0.0, 0.0)
        return [((b[0] - px) * self.w, (b[1] - py) * self.h, (b[2] + px) * self.w, (b[3] + py) * self.h)
                for b in self._heads.get(str(int(round(t * FPS))), [])]

    @staticmethod
    def _hit(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def touches_face(self, rect, t):
        return any(self._hit(rect, f) for f in self.heads(t, pad=False))

    def _span_heads(self, a, b, extra, key=None):
        """Heads over a..b, plus extra rects and every block already placed for any part of a..b."""
        rects, tt = list(extra), a
        for k2, sched, bw, bh in self._reg:
            if k2 != key:
                rects += [(x, y - bh * k / 2, x + bw * k, y + bh * k / 2)
                          for pa, pb, (x, y, k) in sched if pa < b and a < pb]
        while tt < b:
            rects += self.heads(tt)
            tt += 1.0 / 12
        return rects + self.heads(max(a, b - 1.0 / FPS))

    def _find(self, rects, bw, bh, xs, prefer, bands, scales, keep=None):
        tries = [(k, band) for k in scales for band in bands]
        if keep:
            tries.insert(0, (keep[2], None))
        for k, band in tries:
            w, h = bw * k, bh * k
            if band is None:
                cands, lo, hi = [keep[:2]], -1e9, 1e9
            else:
                lo, hi = band[0] * self.h + h / 2, band[1] * self.h - h / 2
                ys = sorted(np.arange(lo, hi + 1, 8 * self.s), key=lambda y: abs(y - prefer * self.h))
                # a smaller block keeps its side: left edge, centre or right edge, whichever x was
                cands = [(x + (bw - w) * (0.0 if x < 0.15 * self.w else 1.0 if x + bw > 0.85 * self.w else 0.5), y)
                         for y in ys for x in xs]
            for x, yc in cands:
                if lo - 1 <= yc <= hi + 1 and not any(self._hit((x, yc - h / 2, x + w, yc + h / 2), f) for f in rects):
                    return (x, yc, k)
        return None

    def place(self, key, t0, t1, bw, bh, xs, prefer, t=None, extra=(), scales=(1.0, 0.85, 0.72, 0.6), bands=None):
        """(x, centre y, scale) for a block of bw x bh px (its full footprint: shadow, pop overshoot, slide-in
        and anything that grows out of it) shown from t0 to t1. xs: left edges to try, at full size; prefer:
        the centre line wanted, as a fraction of the height; extra: rects to avoid besides heads (other blocks).
        Scale the block by the returned factor; draw it at the position given for the frame's own time t.
        Every placed block is remembered and later ones keep clear of it, so place blocks in the order they
        appear: call each draw function once at every block's start time before the first frame (see
        "Keeping faces clear" in references/compositor.md), or a render that starts mid-song lays out
        differently from the full one."""
        bands = bands or self.BANDS
        if key not in self._placed:
            got = self._find(self._span_heads(t0, t1, extra, key), bw, bh, xs, prefer, bands[:1], scales[:1])
            if got:
                sched = [(t0, t1, got)]
            else:
                cuts = sorted({t0, t1} | {c for c in self._cuts if t0 < c < t1})
                sched, prev = [], None
                for a, b in zip(cuts, cuts[1:]):
                    got = self._find(self._span_heads(a, b, extra, key), bw, bh, xs, prefer, bands, scales, keep=prev)
                    if not got:
                        got = prev or (xs[0], prefer * self.h, scales[-1])
                        self.place_misses.append((key, round(a, 2), round(b, 2)))
                    sched.append((a, b, got))
                    prev = got
            self._placed[key] = sched
            self._reg.append((key, sched, bw, bh))
        tt = t0 if t is None else t
        for a, b, got in self._placed[key]:
            if a <= tt < b:
                return got
        return self._placed[key][-1][2]

    def backdrop(self, rect, t):
        """Luminance of the picture under rect (px) at frame time t, without overlays, from the clean frames
        heads.py wrote: for choosing a block's treatment per shot (light or dark type, a stronger shadow)."""
        n = int(round(t * FPS))
        p = Path("mv/work/heads/frames") / f"{n:05d}.jpg"
        if not hasattr(self, "_bd"):
            self._bd = {}
        if n not in self._bd:
            if not p.exists():
                return None
            if len(self._bd) > 8:
                self._bd.clear()
            c = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32) / 255
            c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
            self._bd[n] = c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722
        L = self._bd[n]
        fh, fw = L.shape
        x0, y0 = max(0, int(rect[0] / self.w * fw)), max(0, int(rect[1] / self.h * fh))
        x1, y1 = min(fw, max(x0 + 1, int(rect[2] / self.w * fw))), min(fh, max(y0 + 1, int(rect[3] / self.h * fh)))
        sub = L[y0:y1, x0:x1]
        if sub.size == 0:
            return None
        return {"mean": float(sub.mean()), "low": float(np.percentile(sub, 10)), "high": float(np.percentile(sub, 90))}

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
