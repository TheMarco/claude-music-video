"""Explaining graphics for fx.py: a library of motion-design devices that show what a line means.

Every line of a song gets one graphic that explains it (references/effects-ideas.md, "What makes an
effect land"): the counter its number implies, the gauge that measures its feeling, the interface its joke
is about, the label that classifies what is in frame. These devices are drawn, timed and placed by the
engine; a video picks them per line, fills them with the line's own facts, and styles them with its own
fonts and accent. Nothing here has a look of its own beyond clean craft: the Style decides.

    from devices import Style, Plan, Counter, Gauge, Chart, Poll, Terminal, Chat, Spec, Flap, Stamp, \\
        Strike, Redact, Progress, Flow, Route, Sticker, Typed, Tags, Callout, Mark, word

    STYLE = Style(accent=(255, 92, 64), sans=(F + "...", 0), bold=(...), mono=(...), display=(...))
    PLAN = Plan(STYLE)
    PLAN.add(Counter("PEOPLE WHO CAN DO THIS", 8_000_000_000, mode="odometer"), word("billion"), 4 * BEAT,
             prefer=0.3)
    PLAN.add(Tags(lambda i, box: "BUILDER 0.98"), 52.0, 54.0)

    def draw_front(ov, d, t, f, ctx):
        PLAN.draw(ov, d._image, t, avoid=rects_of_this_frames_lyrics)

Timing: every device runs from t0 for a duration (seconds; use BEAT multiples, or word() for a sung word's
time) and animates in beats from t0, so it lands on the music. A panel starts rising `lead` seconds before
t0 (0.2 s unless Plan.add says otherwise) and has settled when the word or beat arrives; what it shows
starts moving on t0. A device should stay long enough to read: Plan warns under 1.2 s. Entrances and exits
are a short rise and fade, never a one-frame flash.

Roles and the frame budget (enforced per frame, newest wins): one "hero" (a panel that carries the line),
at most two "cv" marks (labels on people or points), at most two "micro" rows, at most three stickers. Panels are placed with
ov.place against the tracked heads and every block placed before them, and inside the 9:16 safe band;
lay them out once in order of appearance with the video's own blocks (call Plan.draw at every start time
in the layout pass, like any other block; Plan.starts() lists them).

Devices (role, what it explains):
  Counter   hero  a number that counts up or lands digit by digit (odometer): stakes, scale, money, time
  Gauge     hero  a dial whose needle swings to a value: a feeling measured, risk, speed, pressure
  Chart     hero  a line, area or bar chart drawn on the beat with the last point called out: a trend
  Poll      hero  percentage bars that can swing later in the video: opinion, odds, a callback that moves
  Progress  hero  a bar that fills and reports done: loading, copying, a countdown to something
  Terminal  hero  a command typed on sixteenths and its output on beats: the tool, the code, the agent
  Chat      hero  messages arriving with a typing indicator: dialogue, a prompt and its reply
  Spec      hero  a label card with field: value rows and a barcode: a model card, a product, a garment tag
  Flap      hero  a split-flap board flipping to its text: departures, countdowns, a verdict
  Stamp     hero  a rubber stamp slammed on the beat: a verdict (COPIED, DENIED, APPROVED)
  Strike    hero  a value struck through and replaced: before and after, a price drop, a downgrade
  Redact    hero  lines with black bars that wipe on (and can lift later): a secret, a leak
  Flow      hero  boxes joined by arrows that draw on one per beat: a mechanism, a pipeline, cause and effect
  Route     hero  a line that travels between named stops on a map panel: a place, a journey, a supply chain
  Sticker   own   a thing cut out of the video's own footage, slapped on with a white die-cut edge: the
                  object a line names, a collection that grows (up to three at once, beside the hero)
  Typed     micro small mono rows typed in: sources, dates, coordinates, a footnote
  Tags      cv    detection labels on the tracked heads: a classifier's (wrong, funny) verdict on people
  Callout   cv    a pulsing point with a leader to a label: name a thing in frame (locked shots)
  Mark      cv    a hand-drawn circle, box, underline or arrow that draws itself round a thing in frame
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from overlay import F, FS, hash01
from timing import BEAT, beat_at

# ------------------------------------------------------------------------------------------------ style


class Style:
    """Colours and faces shared by every device of a video. Colours are RGB tuples; faces are (path, index)
    specs for ov.font. dark=True draws dark panels with light type; dark=False light paper panels.
    glass=True makes every panel frosted glass: the compositor blurs and bends the footage under it, and the
    panel's fill becomes a tint over that (dark enough that its type still passes contrastcheck.py)."""

    def __init__(self, accent=(255, 92, 64), dark=True, sans=None, bold=None, mono=None, mono_bold=None,
                 display=None, panel=None, ink=None, text=None, muted=None, rim=None, radius=18, glass=False):
        self.accent = tuple(accent)
        self.dark = dark
        self.sans = sans or (FS + "Arial.ttf", 0)
        self.bold = bold or (FS + "Arial Bold.ttf", 0)
        self.mono = mono or (F + "Menlo.ttc", 0)
        self.mono_bold = mono_bold or (F + "Menlo.ttc", 1)
        self.display = display or self.bold
        self.glass = glass   # panels of frosted glass: the footage shows through, blurred and bent at the rim
        self.panel = panel or (((14, 17, 24, 176) if dark else (244, 242, 236, 190)) if glass
                               else ((14, 17, 24, 236) if dark else (244, 242, 236, 242)))
        self.text = text or ((244, 246, 250) if dark else (16, 18, 24))
        self.muted = muted or ((150, 158, 176) if dark else (100, 104, 116))
        self.ink = ink or (10, 12, 18)
        self.rim = rim or ((96, 106, 128) if dark else (190, 186, 176))
        self.radius = radius


def word(text, n=0, after=0.0, path="mv/data/lyrics.json"):
    """Start time of the n-th sung word matching text (case and punctuation ignored) at or after `after`,
    from lyrics.json. Raises KeyError when the word is never sung there, so a typo fails loudly."""
    norm = lambda s: "".join(c for c in s.lower() if c.isalnum() or c == "'")
    want, hits = norm(text), []
    for ln in json.loads(Path(path).read_text()):
        for w in ln.get("words", []):
            if norm(w["w"]) == want and w["start"] >= after:
                hits.append(w["start"])
    hits.sort()
    if len(hits) <= n:
        raise KeyError(f"'{text}' is sung {len(hits)} times after {after}s; asked for number {n}")
    return hits[n]


# ------------------------------------------------------------------------------------------------ helpers

def _ease_out(u):
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def _ease_io(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _spring(u, k=4.5):
    """0 -> 1 with one overshoot that settles (about 6% past the mark at k=4.5): for needles and pops."""
    u = max(u, 0.0)
    return 1 - math.exp(-k * u) * math.cos(1.6 * math.pi * u)


def _beats(t, t0):
    return beat_at(t) - beat_at(t0)


def _tile(w, h):
    return Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))


def _rgba(c, a=255):
    return tuple(c[:3]) + (int(a),)


def _panel(ov, st, tl, header=None):
    """The shared panel: rounded glass, a rim one step lighter, an optional kicker header with an accent
    square and a hairline under it. Returns the y where content starts."""
    s = ov.s
    d = ImageDraw.Draw(tl)
    w, h = tl.size
    d.rounded_rectangle((0, 0, w - 1, h - 1), int(st.radius * s), fill=st.panel,
                        outline=_rgba(st.rim), width=max(2, int(2 * s)))
    if not header:
        return 22 * s
    f = ov.font(st.mono_bold, 19)
    d.rectangle((22 * s, 25 * s, 32 * s, 35 * s), fill=_rgba(st.accent))
    ov.tracked(d, (44 * s, 30 * s), header.upper(), f, _rgba(st.muted), 2 * s, anchor="lm")
    d.line([(22 * s, 52 * s), (w - 22 * s, 52 * s)], fill=_rgba(st.rim, 160), width=max(1, int(s)))
    return 66 * s


def _shadow(img, alpha_mask, xy, strength=0.5, r=16):
    pad = int(r * 3)
    m = Image.new("L", (alpha_mask.size[0] + 2 * pad, alpha_mask.size[1] + 2 * pad), 0)
    m.paste(alpha_mask, (pad, pad))
    m = m.filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * strength))
    lay = Image.new("RGBA", m.size, (0, 0, 0, 0))
    lay.putalpha(m)
    img.alpha_composite(lay, (int(xy[0] - pad), int(xy[1] - pad + r * 0.6)))


def _hit(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _partial(pts, a, b):
    """The part of the polyline pts between the fractions a and b of its length, and the direction (radians)
    it is heading in at its end."""
    seg = [math.dist(p, q) for p, q in zip(pts, pts[1:])]
    total = sum(seg)
    if total <= 0 or b <= a:
        return [], 0.0
    lo_t, hi_t, out, run, ang = a * total, b * total, [], 0.0, 0.0
    for (p, q), ln in zip(zip(pts, pts[1:]), seg):
        lo, hi = max(lo_t, run), min(hi_t, run + ln)
        if ln > 0 and hi > lo:
            at = lambda f: (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
            if not out:
                out.append(at((lo - run) / ln))
            out.append(at((hi - run) / ln))
            ang = math.atan2(q[1] - p[1], q[0] - p[0])
        run += ln
    return out, ang


def _stroke(img, pts, a, b, width, fill, ss=3):
    """Draw the part of polyline pts between the fractions a and b of its length onto img, antialiased, with
    round ends: the draw-on primitive (b rising from 0 to 1 draws the line, a rising after it erases it from
    its start). Returns (tip, direction) for a dot or an arrowhead on the moving end, or None when nothing
    is drawn."""
    part, ang = _partial(pts, max(0.0, a), min(1.0, b))
    if len(part) < 2:
        return None
    pad = width + 2
    x0 = max(0, int(min(x for x, _ in part) - pad))
    y0 = max(0, int(min(y for _, y in part) - pad))
    x1 = min(img.size[0], int(max(x for x, _ in part) + pad) + 1)
    y1 = min(img.size[1], int(max(y for _, y in part) + pad) + 1)
    if x1 <= x0 or y1 <= y0:
        return part[-1], ang
    m = Image.new("L", ((x1 - x0) * ss, (y1 - y0) * ss), 0)
    d = ImageDraw.Draw(m)
    q = [((x - x0) * ss, (y - y0) * ss) for x, y in part]
    d.line(q, fill=255, width=max(1, int(round(width * ss))), joint="curve")
    r = width * ss / 2
    for x, y in (q[0], q[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    m = m.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    al = fill[3] if len(fill) > 3 else 255
    if al < 255:
        m = m.point(lambda v: int(v * al / 255))
    lay = Image.new("RGBA", m.size, tuple(fill[:3]) + (0,))
    lay.putalpha(m)
    img.alpha_composite(lay, (x0, y0))
    return part[-1], ang


def _head(img, tip, ang, size, width, fill):
    """An arrowhead on a stroke's moving end: two short strokes back from the tip."""
    for da in (2.6, -2.6):
        _stroke(img, [tip, (tip[0] + math.cos(ang + da) * size, tip[1] + math.sin(ang + da) * size)], 0.0, 1.0,
                width, fill)


def _round_rect(x0, y0, x1, y1, r, n=6):
    """Outline of a rounded rectangle as a closed polyline, clockwise from the top edge."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return [(x0 + r, y0)] + pts + [(x0 + r, y0)]


def _smooth(pts, n=14):
    """A Catmull-Rom curve through pts, n samples a leg. Returns the curve and the index of each point in it."""
    if len(pts) < 3:
        return list(pts), list(range(len(pts)))
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out, at = [], []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        at.append(len(out))
        for k in range(n):
            u = k / n
            out.append(tuple(0.5 * (2 * p1[j] + (p2[j] - p0[j]) * u + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * u * u
                                    + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * u ** 3) for j in (0, 1)))
    at.append(len(out))
    out.append(tuple(pts[-1]))
    return out, at


# ------------------------------------------------------------------------------------------------ devices

class Device:
    role = "hero"
    W, H = 560, 260        # footprint in 1080p units
    lead = 0.2             # seconds before t0 that the panel starts rising, so it has settled on the word

    def size(self, ov):
        return self.W * ov.s, self.H * ov.s

    def tile(self, ov, st, t, t0, t1):
        raise NotImplementedError


class Counter(Device):
    """A number that counts to `value` over `beats` beats (mode "count"), or lands digit by digit on
    sixteenths after spinning (mode "odometer"). fmt formats the number; unit sits after it; sub is a mono
    line under it (a source, a date, the comparison)."""

    def __init__(self, label, value, start=0, fmt="{:,.0f}", unit="", sub=None, beats=2.0, mode="count", W=580):
        self.label, self.value, self.start, self.fmt = label, value, start, fmt
        self.unit, self.sub, self.beats, self.mode, self.W = unit, sub, beats, mode, W
        self.H = 230 if sub else 190

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        b = _beats(t, t0)
        final = self.fmt.format(self.value)
        if self.mode == "odometer":
            out, j = [], 0
            for i, ch in enumerate(final):
                if ch.isdigit():
                    land = 0.25 * j
                    j += 1
                    out.append((ch, b >= land, b - land))
                else:
                    out.append((ch, True, 9))
        else:
            # one ease-out, so the number is still visibly moving until it lands on the last beat
            v = self.start + (self.value - self.start) * _ease_out(b / max(self.beats, 1e-3))
            out = [(c, True, 9) for c in self.fmt.format(v)]
        maxw = (self.W - 44) * s - (ov.font(st.mono_bold, 30).getlength(self.unit) + 12 * s if self.unit else 0)
        fnt = ov.fit(st.display, 96, final, 0, maxw)
        x, y = 22 * s, y0 + fnt.size * 0.92
        for ch, landed, since in out:
            if landed:
                col = st.accent if since < 0.5 and self.mode == "odometer" else st.text
                d.text((x, y), ch, font=fnt, fill=_rgba(col), anchor="ls")
            else:
                dg = str(int(hash01("odo", x, int(t * 24)) * 10))
                for dy, al in ((-0.08, 90), (0.08, 90), (0.0, 220)):
                    d.text((x, y + dy * fnt.size), dg, font=fnt, fill=_rgba(st.text, al), anchor="ls")
            x += fnt.getlength(ch)
        if self.unit:
            d.text((x + 10 * s, y), self.unit, font=ov.font(st.mono_bold, 30), fill=_rgba(st.accent), anchor="ls")
        done = self.beats if self.mode == "count" else 0.25 * sum(c.isdigit() for c in final)
        if b >= done:   # an accent rule sweeps under the number once it lands
            v = _ease_out((b - done) / 0.5)
            d.line([(22 * s, y + 14 * s), (22 * s + (self.W - 44) * s * v, y + 14 * s)], fill=_rgba(st.accent),
                   width=max(2, int(4 * s)))
        if self.sub:
            d.text((22 * s, y + 46 * s), self.sub, font=ov.font(st.mono, 22), fill=_rgba(st.muted), anchor="ls")
        return tl


class Gauge(Device):
    """A half dial from lo to hi with ticks; the needle swings to `value` with one overshoot over a beat.
    zone=(a, b) paints that range in the accent (the danger or the target)."""
    W, H = 460, 330

    def __init__(self, label, value, lo=0, hi=100, unit="", ticks=5, zone=None, fmt="{:.0f}"):
        self.label, self.value, self.lo, self.hi, self.unit = label, value, lo, hi, unit
        self.ticks, self.zone, self.fmt = ticks, zone, fmt

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        cx, cy, r = self.W * s / 2, y0 + 175 * s, 150 * s
        box = (cx - r, cy - r, cx + r, cy + r)
        d.arc(box, 180, 360, fill=_rgba(st.rim), width=max(3, int(10 * s)))
        frac = lambda v: (v - self.lo) / (self.hi - self.lo)
        if self.zone:
            a, b = (180 + 180 * frac(z) for z in self.zone)
            d.arc(box, a, b, fill=_rgba(st.accent), width=max(3, int(10 * s)))
        fm = ov.font(st.mono, 18)
        for i in range(self.ticks):
            fv = i / (self.ticks - 1)
            ang = math.pi * (1 + fv)
            p0 = (cx + math.cos(ang) * (r - 22 * s), cy + math.sin(ang) * (r - 22 * s))
            p1 = (cx + math.cos(ang) * (r - 8 * s), cy + math.sin(ang) * (r - 8 * s))
            d.line([p0, p1], fill=_rgba(st.muted), width=max(1, int(2 * s)))
            lv = self.lo + (self.hi - self.lo) * fv
            d.text((cx + math.cos(ang) * (r - 44 * s), cy + math.sin(ang) * (r - 44 * s)), self.fmt.format(lv),
                   font=fm, fill=_rgba(st.muted), anchor="mm")
        u = _spring(_beats(t, t0) / 1.0)
        fv = max(-0.02, min(1.02, frac(self.lo) + (frac(self.value) - frac(self.lo)) * u))
        ang = math.pi * (1 + fv)
        tip = (cx + math.cos(ang) * (r - 14 * s), cy + math.sin(ang) * (r - 14 * s))
        d.line([(cx, cy), tip], fill=_rgba(st.accent), width=max(3, int(5 * s)))
        d.ellipse((cx - 10 * s, cy - 10 * s, cx + 10 * s, cy + 10 * s), fill=_rgba(st.text))
        val = self.lo + (self.value - self.lo) * min(1.0, u)
        d.text((cx, cy + 46 * s), self.fmt.format(val) + (" " + self.unit if self.unit else ""),
               font=ov.font(st.display, 44), fill=_rgba(st.text), anchor="mm")
        return tl


class Chart(Device):
    """A chart drawn in beats: kind "line" or "area" draws a point every `per` beats, "bars" raise one bar
    every `per` beats. The last point gets a dot and a chip with its label (mark); note is a mono line."""
    W, H = 600, 380

    def __init__(self, label, points, kind="line", xlabels=None, mark=None, note=None, per=0.5, lo=None, hi=None):
        self.label, self.points, self.kind, self.xlabels = label, list(points), kind, xlabels
        self.mark, self.note, self.per = mark, note, per
        self.lo = min(self.points) if lo is None else lo
        self.hi = max(self.points) if hi is None else hi
        self.H = 400 if note else 360

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        x0, x1 = 34 * s, (self.W - 30) * s
        yb, yt = y0 + 236 * s, y0 + 16 * s
        for g in range(4):
            gy = yb - (yb - yt) * g / 3
            d.line([(x0, gy), (x1, gy)], fill=_rgba(st.rim, 110), width=1)
        n = len(self.points)
        b = _beats(t, t0) / self.per
        shown = min(n, int(b) + 1)
        frac = b - int(b)
        X = lambda i: x0 + (x1 - x0) * (i + 0.5 if self.kind == "bars" else i) / (n if self.kind == "bars" else max(n - 1, 1))
        Y = lambda v: yb - (yb - yt) * (v - self.lo) / max(self.hi - self.lo, 1e-9)
        if self.kind == "bars":
            bw = (x1 - x0) / n * 0.62
            for i in range(shown):
                grow = _ease_out((b - i) / 1.0)
                top = yb - (yb - Y(self.points[i])) * grow
                col = st.accent if i == n - 1 else st.text
                d.rectangle((X(i) - bw / 2, top, X(i) + bw / 2, yb), fill=_rgba(col, 235))
        else:
            pts = [(X(i), Y(v)) for i, v in enumerate(self.points[:shown])]
            if shown < n and pts:   # the line reaches toward the next point inside the beat
                nx, ny = X(shown), Y(self.points[shown])
                e = min(max(frac, 0.0), 1.0)   # steady inside the beat: the line doesn't stall at each point
                pts.append((pts[-1][0] + (nx - pts[-1][0]) * e, pts[-1][1] + (ny - pts[-1][1]) * e))
            if self.kind == "area" and len(pts) > 1:
                d.polygon(pts + [(pts[-1][0], yb), (pts[0][0], yb)], fill=_rgba(st.accent, 70))
            if len(pts) > 1:
                _stroke(tl, pts, 0.0, 1.0, max(2, 4 * s), _rgba(st.accent))
                d = ImageDraw.Draw(tl)
        d.line([(x0, yb), (x1, yb)], fill=_rgba(st.muted), width=max(1, int(2 * s)))
        if self.xlabels:
            fm = ov.font(st.mono, 17)
            for i, lab in enumerate(self.xlabels[:n]):
                if lab:
                    d.text((X(i), yb + 18 * s), str(lab), font=fm, fill=_rgba(st.muted), anchor="mm")
        if shown == n and b >= n - 1 + 0.25:
            lx, ly = X(n - 1), Y(self.points[-1])
            if self.kind == "bars":
                ly = Y(self.points[-1])
            pulse = 1 + 0.25 * math.exp(-((b - n + 1) % 1.0) * 4)
            r = 8 * s * pulse
            d.ellipse((lx - r, ly - r, lx + r, ly + r), fill=_rgba(st.accent))
            if self.mark:
                fm = ov.font(st.mono_bold, 22)
                tw = fm.getlength(self.mark) + 20 * s
                cx = min(lx - tw / 2, x1 - tw)
                cy = max(ly - 50 * s, yt)
                d.rounded_rectangle((cx, cy, cx + tw, cy + 34 * s), int(6 * s), fill=_rgba(st.accent))
                d.text((cx + tw / 2, cy + 17 * s), self.mark, font=fm, fill=_rgba(st.ink), anchor="mm")
        if self.note:
            d.text((22 * s, (self.H - 26) * s), self.note, font=ov.font(st.mono, 20), fill=_rgba(st.muted), anchor="ls")
        return tl


class Poll(Device):
    """Labelled percentage bars. later=[(time, [pcts...]), ...] swings the same poll to new values at those
    song times (a callback that moves with the story); votes is a mono line under the bars."""
    W = 600

    def __init__(self, title, options, later=(), votes=None):
        self.title, self.options, self.later, self.votes = title, list(options), sorted(later), votes
        self.H = 80 + 78 * len(self.options) + (40 if votes else 10)

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.title)
        d = ImageDraw.Draw(tl)
        vals, since, prev = [p for _, p in self.options], t - t0, None
        for tt, pcts in self.later:
            if t >= tt:
                prev, vals, since = vals, list(pcts), t - tt
        u = _ease_out(since / (BEAT * 1.5))
        cur = [p if prev is None else a + (p - a) * u for a, p in zip(prev or vals, vals)]
        if prev is None:
            cur = [p * u for p in vals]
        lead = max(range(len(vals)), key=lambda i: vals[i])
        fl, fp = ov.font(st.bold, 28), ov.font(st.mono_bold, 26)
        for i, ((lab, _), p) in enumerate(zip(self.options, cur)):
            y = y0 + 8 * s + 78 * s * i
            d.text((22 * s, y + 16 * s), lab, font=fl, fill=_rgba(st.text), anchor="lm")
            d.text(((self.W - 22) * s, y + 16 * s), f"{p:.0f}%", font=fp, fill=_rgba(st.text), anchor="rm")
            bx0, bx1 = 22 * s, (self.W - 22) * s
            d.rounded_rectangle((bx0, y + 38 * s, bx1, y + 56 * s), int(9 * s), fill=_rgba(st.rim, 120))
            if p > 0.5:
                d.rounded_rectangle((bx0, y + 38 * s, bx0 + (bx1 - bx0) * p / 100, y + 56 * s), int(9 * s),
                                    fill=_rgba(st.accent if i == lead else st.muted))
        if self.votes:
            d.text((22 * s, (self.H - 22) * s), self.votes, font=ov.font(st.mono, 20), fill=_rgba(st.muted), anchor="ls")
        return tl


class Progress(Device):
    """A bar that fills from start to end percent over `beats` beats, then shows done (a line in accent)."""
    W, H = 600, 170

    def __init__(self, label, done="Done.", start=0, end=100, beats=2.0):
        self.label, self.done, self.start, self.end, self.beats = label, done, start, end, beats

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        _panel(ov, st, tl)
        d = ImageDraw.Draw(tl)
        u = _ease_io(_beats(t, t0) / self.beats)
        p = self.start + (self.end - self.start) * u
        fin = u >= 1.0
        d.text((24 * s, 46 * s), self.done if fin else self.label, font=ov.font(st.bold, 30),
               fill=_rgba(st.accent if fin else st.text), anchor="lm")
        bx0, bx1 = 24 * s, (self.W - 24) * s
        d.rounded_rectangle((bx0, 86 * s, bx1, 108 * s), int(11 * s), fill=_rgba(st.rim, 120))
        d.rounded_rectangle((bx0, 86 * s, bx0 + max(22 * s, (bx1 - bx0) * p / 100), 108 * s), int(11 * s),
                            fill=_rgba(st.accent))
        d.text((24 * s, 140 * s), f"{p:.0f}%", font=ov.font(st.mono_bold, 24), fill=_rgba(st.muted), anchor="lm")
        return tl


class Terminal(Device):
    """A terminal session: ("cmd", text) is typed after the prompt at `cps` characters per beat; ("out",
    text) appears whole on the next beat; an "out" line starting with "!" is drawn in the accent (without
    the "!"). A third item, ("cmd", text, beats), starts that line that many beats after t0 instead (to type
    each command on its own lyric line). title sits in the window bar."""
    W = 680

    def __init__(self, title, lines, prompt="> ", cps=14):
        self.title, self.lines, self.prompt, self.cps = title, list(lines), prompt, cps
        self.H = 70 + 40 * len(self.lines) + 20

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        _panel(ov, st, tl)
        d = ImageDraw.Draw(tl)
        for i in range(3):
            d.ellipse(((24 + 22 * i) * s, 20 * s, (36 + 22 * i) * s, 32 * s), fill=_rgba(st.rim))
        d.text((self.W * s / 2, 26 * s), self.title, font=ov.font(st.mono, 19), fill=_rgba(st.muted), anchor="mm")
        d.line([(0, 48 * s), (self.W * s, 48 * s)], fill=_rgba(st.rim, 140), width=1)
        fm, fb = ov.font(st.mono, 25), ov.font(st.mono_bold, 25)
        b, clock = _beats(t, t0), 0.0
        cursor = None
        for i, line in enumerate(self.lines):
            kind, text = line[0], line[1]
            if len(line) > 2:
                clock = max(clock, float(line[2]))
            y = (78 + 40 * i) * s
            if kind == "cmd":
                need = len(text) / self.cps
                if b < clock:
                    break
                n = int(len(text) * min(1.0, (b - clock) / max(need, 1e-3)))
                d.text((24 * s, y), self.prompt, font=fb, fill=_rgba(st.accent), anchor="ls")
                px = 24 * s + fb.getlength(self.prompt)
                d.text((px, y), text[:n], font=fm, fill=_rgba(st.text), anchor="ls")
                cursor = (px + fm.getlength(text[:n]) + 4 * s, y)
                clock += need
                clock = math.ceil(clock * 4) / 4 + 0.25   # output waits for the next sixteenth
            else:
                if b < clock:
                    break
                hot = text.startswith("!")
                d.text((24 * s, y), text[1:] if hot else text, font=fm, fill=_rgba(st.accent if hot else st.muted),
                       anchor="ls")
                clock = math.floor(clock) + 1.0
                cursor = None
        if cursor and (b * 2) % 1 < 0.6:
            d.rectangle((cursor[0], cursor[1] - 22 * s, cursor[0] + 13 * s, cursor[1] + 3 * s), fill=_rgba(st.text))
        return tl


class Chat(Device):
    """Messages ("in" or "out", text): each one shows a typing indicator for half a beat, then its bubble,
    one per beat from t0. "out" bubbles are the accent."""
    W = 620

    def __init__(self, messages, title=None):
        self.messages, self.title = list(messages), title
        self.H = (70 if title else 24) + 92 * len(self.messages)

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y = _panel(ov, st, tl, self.title)
        d = ImageDraw.Draw(tl)
        b = _beats(t, t0)
        fnt = ov.font(st.sans, 28)
        for i, (side, text) in enumerate(self.messages):
            start = i * 1.0
            if b < start:
                break
            out = side == "out"
            tw = min(fnt.getlength(text), (self.W - 120) * s)
            bw, bh = tw + 40 * s, 64 * s
            bx = (self.W - 22) * s - bw if out else 22 * s
            if b < start + 0.5:   # typing indicator
                for k in range(3):
                    on = int(b * 6 + k) % 3 == 0
                    cx = bx + (24 + 18 * k) * s if not out else (self.W - 70 + 18 * k) * s
                    d.ellipse((cx - 6 * s, y + bh / 2 - 6 * s, cx + 6 * s, y + bh / 2 + 6 * s),
                              fill=_rgba(st.text if on else st.muted))
            else:
                pop = 0.85 + 0.15 * _spring((b - start - 0.5) / 0.6)
                ww, hh = bw * pop, bh * pop
                x0 = bx + (bw - ww) * (1.0 if not out else 0.0)
                d.rounded_rectangle((x0, y, x0 + ww, y + hh), int(22 * s),
                                    fill=_rgba(st.accent if out else st.rim, 255))
                d.text((x0 + 20 * s, y + hh / 2), text, font=fnt, fill=_rgba(st.ink if out else st.text), anchor="lm")
            y += 92 * s
        return tl


class Spec(Device):
    """A label card: a kicker, a title in the display face, field: value rows typed in one per eighth, and
    a barcode. For a model card, a product tag, a garment label, a passport."""
    W = 560

    def __init__(self, kicker, title, rows, barcode=True, code=None):
        self.kicker, self.title, self.rows, self.barcode = kicker, title, list(rows), barcode
        self.code = code
        self.H = 140 + 40 * len(self.rows) + (96 if barcode else 16)

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y = _panel(ov, st, tl, self.kicker)
        d = ImageDraw.Draw(tl)
        fnt = ov.fit(st.display, 52, self.title, 0, (self.W - 44) * s)
        d.text((22 * s, y + fnt.size * 0.85), self.title, font=fnt, fill=_rgba(st.text), anchor="ls")
        y += fnt.size + 26 * s
        b = _beats(t, t0)
        fk, fv = ov.font(st.mono, 23), ov.font(st.mono_bold, 23)
        for i, (k, v) in enumerate(self.rows):
            if b < 0.5 + 0.5 * i:
                break
            d.text((22 * s, y), str(k).upper(), font=fk, fill=_rgba(st.muted), anchor="lm")
            d.text(((self.W - 22) * s, y), str(v), font=fv, fill=_rgba(st.text), anchor="rm")
            d.line([(22 * s, y + 20 * s), ((self.W - 22) * s, y + 20 * s)], fill=_rgba(st.rim, 90), width=1)
            y += 40 * s
        if self.barcode and b >= 0.5 + 0.5 * len(self.rows):
            x, y0 = 22 * s, y + 14 * s
            i = 0
            while x < (self.W - 180) * s:
                wbar = (1 + int(hash01("bar", self.title, i) * 3)) * 2 * s
                if hash01("gap", self.title, i) > 0.35:
                    d.rectangle((x, y0, x + wbar, y0 + 52 * s), fill=_rgba(st.text))
                x += wbar + 2 * s
                i += 1
            code = self.code or f"{int(hash01('code', self.title) * 1e8):08d}"
            d.text(((self.W - 22) * s, y0 + 26 * s), code, font=ov.font(st.mono, 20), fill=_rgba(st.muted), anchor="rm")
        return tl


class Flap(Device):
    """A split-flap board: rows of characters flip through random glyphs and land one cell every 32nd,
    left to right, top to bottom. cols defaults to the longest row."""
    GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def __init__(self, rows, cols=None, label=None):
        self.rows = [r.upper() for r in rows]
        self.cols = cols or max(len(r) for r in self.rows)
        self.label = label
        self.cell = min(64, int(620 / self.cols))
        self.W = self.cols * self.cell + 44
        self.H = (66 if label else 22) + len(self.rows) * int(self.cell * 1.45) + 22

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        cw, ch = self.cell * s, self.cell * 1.32 * s
        fnt = ov.font(st.mono_bold, self.cell * 0.9)
        b = _beats(t, t0)
        k = 0
        for r, row in enumerate(self.rows):
            for c in range(self.cols):
                x = 22 * s + c * cw
                y = y0 + r * self.cell * 1.45 * s
                d.rounded_rectangle((x + 2 * s, y, x + cw - 2 * s, y + ch), int(5 * s), fill=(24, 26, 32, 255))
                target = row[c] if c < len(row) else " "
                land = 0.125 * k
                k += 1
                if b >= land:
                    g = target
                else:
                    g = self.GLYPHS[int(hash01("flap", r, c, int(t * 24)) * len(self.GLYPHS))]
                if g != " ":
                    col = st.accent if 0 <= b - land < 0.25 else (240, 240, 236)
                    d.text((x + cw / 2, y + ch / 2), g, font=fnt, fill=_rgba(col), anchor="mm")
                d.line([(x + 2 * s, y + ch / 2), (x + cw - 2 * s, y + ch / 2)], fill=(8, 9, 12, 255),
                       width=max(1, int(2 * s)))
        return tl


class Stamp(Device):
    """A rubber stamp slammed on the beat: it drops from 1.7x to size in a sixteenth, settles, and holds,
    with worn ink. Set the colour (default the accent) and the angle."""

    def __init__(self, text, angle=-8, color=None, sub=None):
        self.text, self.angle, self.color, self.sub = text.upper(), angle, color, sub
        self.W, self.H = 40 + 46 * len(self.text) + 60, 210

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        col = self.color or st.accent
        inner = _tile(self.W * s * 0.8, self.H * s * 0.62)
        d = ImageDraw.Draw(inner)
        w, h = inner.size
        d.rectangle((3 * s, 3 * s, w - 3 * s, h - 3 * s), outline=_rgba(col), width=max(3, int(7 * s)))
        d.rectangle((14 * s, 14 * s, w - 14 * s, h - 14 * s), outline=_rgba(col), width=max(1, int(3 * s)))
        fnt = ov.fit(st.display, 78, self.text, 0, w - 56 * s)
        d.text((w / 2, h / 2 + (0 if not self.sub else -10 * s)), self.text, font=fnt, fill=_rgba(col), anchor="mm")
        if self.sub:
            d.text((w / 2, h - 30 * s), self.sub, font=ov.font(st.mono_bold, 18), fill=_rgba(col), anchor="mm")
        a = inner.getchannel("A")   # worn ink: knock out a speckle that stays put from frame to frame
        if getattr(self, "_speck", None) is None or self._speck.size != inner.size:
            import random
            rnd = random.Random(hash(self.text) & 0xFFFF)
            self._speck = Image.new("L", inner.size, 255)
            sd = ImageDraw.Draw(self._speck)
            for _ in range(int(inner.size[0] * inner.size[1] / 140)):
                x, y, r = rnd.random() * inner.size[0], rnd.random() * inner.size[1], rnd.random() * 2.2 * s + 0.5
                sd.ellipse((x - r, y - r, x + r, y + r), fill=0)
        inner.putalpha(Image.composite(a, Image.new("L", inner.size, 0), self._speck))
        u = _beats(t, t0) / 0.25
        sc = 1.0 + 0.7 * (1 - _ease_out(u)) if u < 1 else 1.0 + 0.03 * math.exp(-(u - 1) * 3)
        rot = inner.rotate(self.angle, resample=Image.BICUBIC, expand=True)
        rot = rot.resize((max(1, int(rot.size[0] * sc)), max(1, int(rot.size[1] * sc))), Image.BICUBIC)
        if u < 1:
            rot.putalpha(rot.getchannel("A").point(lambda v: int(v * _ease_out(u))))
        tl.alpha_composite(rot, (int((tl.size[0] - rot.size[0]) / 2), int((tl.size[1] - rot.size[1]) / 2)))
        return tl

    lead = 0.0   # a stamp lands on its beat; nothing of it shows before

    def panel(self):
        return False


class Strike(Device):
    """A value struck through on the first beat and replaced: the old one (muted) gets an accent line drawn
    across it, then the new one pops in beside or under it. label is the kicker."""

    def __init__(self, label, old, new, under=False):
        self.label, self.old, self.new, self.under = label, old, new, under
        self.W = 560 if not under else 520
        self.H = 200 if not under else 270

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        b = _beats(t, t0)
        fo = ov.fit(st.display, 64, self.old, 0, (self.W * (0.9 if self.under else 0.45)) * s)
        yo = y0 + fo.size * 0.9
        d.text((22 * s, yo), self.old, font=fo, fill=_rgba(st.muted), anchor="ls")
        ow = fo.getlength(self.old)
        v = _ease_out((b - 1.0) / 0.25)
        if v > 0:
            ym = yo - fo.size * 0.33
            d.line([(16 * s, ym + 6 * s), (16 * s + (ow + 12 * s) * v, ym - 6 * s)], fill=_rgba(st.accent),
                   width=max(3, int(8 * s)))
        if b >= 1.4:
            sc = 0.6 + 0.4 * _spring((b - 1.4) / 0.6)
            fn = ov.fit(st.display, 84 * sc, self.new, 0, (self.W * (0.9 if self.under else 0.48)) * s * sc)
            if self.under:
                d.text((22 * s, yo + fn.size * 1.05), self.new, font=fn, fill=_rgba(st.accent), anchor="ls")
            else:
                d.text(((self.W - 22) * s, yo), self.new, font=fn, fill=_rgba(st.accent), anchor="rs")
        return tl


class Flow(Device):
    """A mechanism as boxes joined by arrows, left to right: nodes are strings or (title, sub) pairs, two to
    five of them. One node lands every `per` beats: its outline draws on over half a beat, the fill follows,
    then the arrow draws out of it and reaches the next node on that node's beat. The active node (default
    the last, the outcome) fills with the accent once it has landed. note is a mono line under the row."""
    W = 720

    def __init__(self, label, nodes, per=1.0, active=-1, note=None):
        self.label, self.per, self.note = label, per, note
        self.nodes = [n if isinstance(n, (tuple, list)) else (n, None) for n in nodes][:5]
        self.active = active % len(self.nodes)
        self.sub = any(sb for _, sb in self.nodes)
        self.H = 66 + (104 if self.sub else 84) + (48 if note else 22)

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        n = len(self.nodes)
        gap = 44 * s
        nw = ((self.W - 44) * s - gap * (n - 1)) / n
        nh = (88 if self.sub else 68) * s
        b = _beats(t, t0)
        lw = max(2, 3 * s)
        for i, (title, sb) in enumerate(self.nodes):
            u = (b - i * self.per) / 0.5          # this node's outline, 0..1 over half a beat
            x = 22 * s + i * (nw + gap)
            box = (x, y0 + 4 * s, x + nw, y0 + 4 * s + nh)
            if u > 0:
                fa = _ease_out((u - 0.5) / 0.7)   # the fill follows the outline
                hot = i == self.active
                if fa > 0:
                    lay = _tile(*tl.size)
                    ImageDraw.Draw(lay).rounded_rectangle(box, int(12 * s), fill=_rgba(st.accent if hot else st.rim,
                                                                                       (255 if hot else 110) * fa))
                    tl.alpha_composite(lay)
                _stroke(tl, _round_rect(*box, 12 * s), 0.0, min(1.0, u), lw, _rgba(st.accent if hot or u < 1 else st.rim))
                ta = _ease_out((u - 0.6) / 0.6)
                if ta > 0:
                    d = ImageDraw.Draw(tl)
                    col = st.ink if hot else st.text
                    ft = ov.fit(st.bold, 28, title, 0, nw - 20 * s)
                    cy = (box[1] + box[3]) / 2 - (12 * s if sb else 0)
                    d.text((x + nw / 2, cy), title, font=ft, fill=_rgba(col, 255 * ta), anchor="mm")
                    if sb:
                        fs = ov.fit(st.mono, 18, sb, 0, nw - 16 * s)
                        d.text((x + nw / 2, cy + 30 * s), sb, font=fs, fill=_rgba(col if hot else st.muted, 255 * ta),
                               anchor="mm")
            if i < n - 1:                         # the arrow leaves when the outline closes, arrives on the next beat
                v = (b - i * self.per - 0.5) / max(self.per - 0.5, 0.25)
                if v > 0:
                    ym = (box[1] + box[3]) / 2
                    got = _stroke(tl, [(box[2] + 7 * s, ym), (box[2] + gap - 9 * s, ym)], 0.0, min(1.0, v), lw,
                                  _rgba(st.accent))
                    if got:
                        _head(tl, got[0], got[1], 11 * s, lw, _rgba(st.accent))
        if self.note:
            ImageDraw.Draw(tl).text((22 * s, (self.H - 24) * s), self.note, font=ov.font(st.mono, 20),
                                    fill=_rgba(st.muted), anchor="ls")
        return tl


class Route(Device):
    """A place as a route on a map panel: stops are (name, (x, y)) with x, y in 0..1 of the map area (y down),
    or names alone, laid out left to right. The line leaves the first stop on t0 and reaches one stop every
    `per` beats with a dot riding its end; each stop's marker and name appear as the line arrives. Once it
    has arrived, a pulse of light runs the route again every two bars. note is a mono line under the map
    (coordinates, a distance, a date)."""
    W = 640

    def __init__(self, label, stops, per=1.0, note=None):
        self.label, self.per, self.note = label, per, note
        n = len(stops)
        self.stops = []
        for i, sp in enumerate(stops):
            if isinstance(sp, str):
                sp = (sp, (0.08 + 0.84 * i / max(n - 1, 1), 0.68 - 0.36 * (i % 2) if n > 2 else 0.62 - 0.24 * i))
            self.stops.append(sp)
        self.H = 66 + 260 + (48 if note else 20)

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y0 = _panel(ov, st, tl, self.label)
        d = ImageDraw.Draw(tl)
        mx0, mx1, my0, my1 = 34 * s, (self.W - 34) * s, y0 + 34 * s, y0 + 226 * s
        for g in range(7):                      # a faint graticule, so the panel reads as a map
            gx = 22 * s + ((self.W - 44) * s) * g / 6
            d.line([(gx, y0), (gx, y0 + 256 * s)], fill=_rgba(st.rim, 60), width=1)
        for g in range(5):
            gy = y0 + 256 * s * g / 4
            d.line([(22 * s, gy), ((self.W - 22) * s, gy)], fill=_rgba(st.rim, 60), width=1)
        pts = [(mx0 + (mx1 - mx0) * x, my0 + (my1 - my0) * y) for _, (x, y) in self.stops]
        curve, at = _smooth(pts)
        seg = [math.dist(p, q) for p, q in zip(curve, curve[1:])]
        cum = [0.0]
        for ln in seg:
            cum.append(cum[-1] + ln)
        total = max(cum[-1], 1e-6)
        b = _beats(t, t0) / self.per
        legs = len(pts) - 1
        k = min(max(int(b), 0), legs - 1) if legs else 0
        u = min(max(b - k, 0.0), 1.0) if b < legs else 1.0
        frac = (cum[at[k]] + (cum[at[k + 1]] - cum[at[k]]) * u) / total if legs and b > 0 else 0.0
        lw = max(3, 5 * s)
        got = _stroke(tl, curve, 0.0, frac, lw, _rgba(st.accent))
        if b >= legs and legs:                  # arrived: a pulse runs the route again every two bars
            ph = ((b - legs) * self.per % 8.0) / 2.0
            if ph < 1.3:
                _stroke(tl, curve, ph - 0.3, ph, lw, _rgba(st.text))
        d = ImageDraw.Draw(tl)
        fm = ov.font(st.mono_bold, 20)
        for i, (name, _) in enumerate(self.stops):
            since = b - i
            if since < 0:
                break
            px, py = pts[i]
            r = (7 + 5 * math.exp(-since * 3)) * s
            d.ellipse((px - r, py - r, px + r, py + r), fill=_rgba(st.panel[:3]), outline=_rgba(st.accent),
                      width=max(2, int(3 * s)))
            tw = fm.getlength(name)
            lx = min(max(px - tw / 2, 24 * s), (self.W - 24) * s - tw)
            ly = py + 26 * s if py < (my0 + my1) / 2 else py - 26 * s
            a = _ease_out(since / 0.4)
            d.text((lx, ly), name, font=fm, fill=_rgba(st.text, 255 * a), anchor="lm",
                   stroke_width=max(2, int(3 * s)), stroke_fill=_rgba(st.panel[:3], 255 * a))
        if got and 0 < b < legs:                # the dot riding the moving end
            (tx, ty), _ = got
            d.ellipse((tx - 9 * s, ty - 9 * s, tx + 9 * s, ty + 9 * s), fill=_rgba(st.text))
        if self.note:
            d.text((22 * s, (self.H - 24) * s), self.note, font=ov.font(st.mono, 20), fill=_rgba(st.muted), anchor="ls")
        return tl


class Sticker(Device):
    """A thing from the video's own footage, cut out and slapped on like a die-cut sticker: a white outline,
    a soft shadow, a slight tilt. src is a source code and `at` a time in that source (seconds); box is the
    thing's (x0, y0, x1, y1) in 0..1 of the frame as the shot shows it (read it off a contact sheet). The
    cut-out is found inside the box (OpenCV GrabCut, no model to fetch) and kept in mv/work/stickers/, so
    look at the first still: when the cut is wrong, tighten the box, or pass image="file.png", a picture with
    its own transparency. size is the longer side in 1080p units; label a chip under it. It drops onto the
    picture in a sixteenth on its beat and holds. Up to three stickers show at once (their own budget), so
    a line can collect them: add each with its own time and the same end."""
    role = "sticker"
    lead = 0.0

    def __init__(self, src=None, at=0.0, box=(0.3, 0.3, 0.7, 0.7), size=300, angle=-6, label=None, outline=10,
                 image=None):
        self.src, self.at, self.box, self.px, self.angle = src, at, box, size, angle
        self.label, self.outline, self.image = label, outline, image
        self.cut = self._cut()
        w, h = self.cut.size
        k = size / max(w, h)
        pad = outline + 26
        self.W = w * k * 1.12 + 2 * pad
        self.H = h * k * 1.12 + 2 * pad + (54 if label else 0)
        self._made = {}

    def _cut(self):
        import hashlib
        import subprocess
        import numpy as np
        key = hashlib.md5(repr((self.src, self.at, self.box, self.image)).encode()).hexdigest()[:12]
        out = Path("mv/work/stickers") / f"{key}.png"
        if out.exists():
            return Image.open(out).convert("RGBA")
        if self.image:
            im = Image.open(self.image).convert("RGBA")
            if im.getchannel("A").getextrema()[0] < 250:      # it brings its own transparency
                im = im.crop(im.getbbox())
                im.thumbnail((640, 640), Image.LANCZOS)
                out.parent.mkdir(parents=True, exist_ok=True)
                im.save(out)
                return im
            frame = im.convert("RGB")
        else:
            from media import crop_for, is_image, src_path
            p = src_path(self.src)
            if is_image(self.src):
                frame = Image.open(p).convert("RGB")
            else:
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{self.at:.3f}", "-i", str(p), "-frames:v", "1",
                                      "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
                if not raw:
                    raise SystemExit(f"Sticker: no frame at {self.at}s in {self.src}")
                import io
                frame = Image.open(io.BytesIO(raw)).convert("RGB")
            x, y, w, h = crop_for(self.src)
            fw, fh = frame.size
            frame = frame.crop((int(x * fw), int(y * fh), int((x + w) * fw), int((y + h) * fh)))
        import cv2
        from scipy import ndimage
        fw, fh = frame.size
        bx0, by0, bx1, by1 = (self.box[0] * fw, self.box[1] * fh, self.box[2] * fw, self.box[3] * fh)
        mx, my = (bx1 - bx0) * 0.15, (by1 - by0) * 0.15       # some surroundings, so the cut knows the background
        rx0, ry0, rx1, ry1 = (int(max(0, bx0 - mx)), int(max(0, by0 - my)), int(min(fw, bx1 + mx)), int(min(fh, by1 + my)))
        reg = frame.crop((rx0, ry0, rx1, ry1))
        sc = min(1.0, 560 / max(reg.size))
        reg_s = reg.resize((max(8, int(reg.size[0] * sc)), max(8, int(reg.size[1] * sc))), Image.LANCZOS)
        arr = np.asarray(reg_s)[:, :, ::-1].copy()
        rect = (int((bx0 - rx0) * sc) + 1, int((by0 - ry0) * sc) + 1,
                max(4, int((bx1 - bx0) * sc) - 2), max(4, int((by1 - by0) * sc) - 2))
        mask = np.zeros(arr.shape[:2], np.uint8)
        try:
            cv2.grabCut(arr, mask, rect, np.zeros((1, 65)), np.zeros((1, 65)), 5, cv2.GC_INIT_WITH_RECT)
            fg = (mask == 1) | (mask == 3)
        except cv2.error:
            fg = np.zeros(arr.shape[:2], bool)
        lab, n = ndimage.label(fg)
        if n:
            sizes = ndimage.sum(fg, lab, range(1, n + 1))
            fg = ndimage.binary_fill_holes(lab == (1 + int(np.argmax(sizes))))
        if fg.sum() < 0.08 * rect[2] * rect[3]:               # nothing found: the box itself, rounded
            fg = np.zeros(arr.shape[:2], bool)
            fg[rect[1]:rect[1] + rect[3], rect[0]:rect[0] + rect[2]] = True
            print(f"Sticker: no clear object in the box on {self.src or self.image}; using the box itself")
        fg = ndimage.binary_opening(fg, iterations=2)
        a = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        cut = reg_s.convert("RGBA")
        cut.putalpha(a)
        cut = cut.crop(cut.getbbox())
        out.parent.mkdir(parents=True, exist_ok=True)
        cut.save(out)
        return cut

    def _sticker(self, ov):
        """The cut-out at this output's size with its white edge and shadow, made once."""
        import numpy as np
        from scipy import ndimage
        s = ov.s
        if s not in self._made:
            k = self.px * s / max(self.cut.size)
            cut = self.cut.resize((max(2, int(self.cut.size[0] * k)), max(2, int(self.cut.size[1] * k))), Image.LANCZOS)
            o = self.outline * s
            pad = int(o + 4)
            canvas = Image.new("RGBA", (cut.size[0] + 2 * pad, cut.size[1] + 2 * pad), (0, 0, 0, 0))
            hard = np.zeros((canvas.size[1], canvas.size[0]), bool)
            hard[pad:pad + cut.size[1], pad:pad + cut.size[0]] = np.asarray(cut.getchannel("A")) > 127
            edge = np.clip(o + 0.75 - ndimage.distance_transform_edt(~hard), 0, 1)
            white = Image.new("RGBA", canvas.size, (250, 250, 246, 0))
            white.putalpha(Image.fromarray((edge * 255).astype(np.uint8)))
            canvas.alpha_composite(white)
            canvas.alpha_composite(cut, (pad, pad))
            self._made[s] = canvas
        return self._made[s]

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        b = _beats(t, t0)
        u = b / 0.25
        sc = 1.0 + 0.5 * (1 - _ease_out(u)) if u < 1 else 1.0 + 0.04 * math.exp(-(u - 1) * 3)
        stk = self._sticker(ov).rotate(self.angle + 6 * (1 - _ease_out(u)), resample=Image.BICUBIC, expand=True)
        if abs(sc - 1) > 1e-3:
            stk = stk.resize((max(1, int(stk.size[0] * sc)), max(1, int(stk.size[1] * sc))), Image.BICUBIC)
        if u < 1:
            stk.putalpha(stk.getchannel("A").point(lambda v: int(v * _ease_out(u * 1.5))))
        body = (self.H - (54 if self.label else 0)) * s
        pos = (int((tl.size[0] - stk.size[0]) / 2), int((body - stk.size[1]) / 2))
        _shadow(tl, stk.getchannel("A"), (pos[0], max(0, pos[1])), 0.55, int(12 * s))
        tl.alpha_composite(stk, (max(0, pos[0]), max(0, pos[1])))
        if self.label and b >= 0.5:
            f = ov.fit(st.mono_bold, 24, self.label, 0, tl.size[0] - 30 * s)
            tw = f.getlength(self.label) + 24 * s
            a = _ease_out((b - 0.5) / 0.4)
            x0, y0 = (tl.size[0] - tw) / 2, body + 2 * s
            chip = _tile(*tl.size)     # the label is a strip of the same white stock, with its own shadow
            ImageDraw.Draw(chip).rounded_rectangle((x0, y0, x0 + tw, y0 + 40 * s), int(8 * s), fill=(250, 250, 246, int(255 * a)),
                                                     outline=_rgba(st.ink, 255 * a), width=max(2, int(3 * s)))
            _shadow(tl, chip.getchannel("A"), (0, 0), 0.55, int(10 * s))
            tl.alpha_composite(chip)
            ImageDraw.Draw(tl).text((tl.size[0] / 2, y0 + 20 * s), self.label, font=f, fill=_rgba(st.ink, 255 * a),
                                    anchor="mm")
        return tl

    def panel(self):
        return False


class Redact(Device):
    """Lines of text with black bars over the words wrapped in [brackets]: the bars wipe on one per
    sixteenth; lift=TIME lifts them at that song time (the reveal)."""
    W = 620

    def __init__(self, label, lines, lift=None):
        self.label, self.lines, self.lift = label, list(lines), lift
        self.H = 80 + 50 * len(self.lines) + 10

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        y = _panel(ov, st, tl, self.label) + 20 * s
        d = ImageDraw.Draw(tl)
        fnt = ov.font(st.mono, 27)
        b = _beats(t, t0)
        k = 0
        lifted = self.lift is not None and t >= self.lift
        for line in self.lines:
            x = 22 * s
            chunks, cur, inside = [], "", False
            for ch in line:
                if ch in "[]":
                    if cur:
                        chunks.append((cur, inside))
                    cur, inside = "", ch == "["
                else:
                    cur += ch
            if cur:
                chunks.append((cur, inside))
            for text, hidden in chunks:
                w = fnt.getlength(text)
                if not hidden or lifted:   # a hidden word never shows until its bar lifts
                    d.text((x, y), text, font=fnt, fill=_rgba(st.text), anchor="lm")
                if hidden:
                    v = _ease_out((b - 0.25 * k) / 0.25)
                    if lifted:
                        v *= 1 - _ease_out((t - self.lift) / (BEAT * 0.5))
                    if v > 0:
                        d.rectangle((x - 3 * s, y - 17 * s, x - 3 * s + (w + 6 * s) * v, y + 17 * s), fill=(6, 6, 8, 255))
                    k += 1
                x += w
            y += 50 * s
        return tl


class Typed(Device):
    """Micro type: up to three short mono rows typed in fast (a character per 64th), no panel: sources,
    dates, coordinates, a footnote. Light type with a dark outline so it reads on any shot."""
    role = "micro"
    lead = 0.0

    def __init__(self, rows, size=22):
        self.rows, self.fs = list(rows)[:3], size
        self.W = 30 + max(len(r) for r in self.rows) * size * 0.62
        self.H = 16 + len(self.rows) * size * 1.5

    def tile(self, ov, st, t, t0, t1):
        s = ov.s
        tl = _tile(self.W * s, self.H * s)
        d = ImageDraw.Draw(tl)
        fnt = ov.font(st.mono, self.fs)
        b = _beats(t, t0)
        start = 0.0
        for i, row in enumerate(self.rows):
            n = int(max(0.0, (b - start) * 16))
            if n <= 0:
                break
            d.text((8 * s, (8 + self.fs * 0.75 + i * self.fs * 1.5) * s), row[:n], font=fnt, fill=_rgba(st.text, 240),
                   anchor="ls", stroke_width=max(2, int(2.5 * s)), stroke_fill=_rgba(st.ink, 240))
            start += len(row) / 16 + 0.25
        return tl

    def panel(self):
        return False


# --- frame devices: draw on the whole frame, anchored to what is in it ----------------------------

class Tags(Device):
    """Detection labels on the tracked heads (heads.py). label(i, box) returns the text for head i (sorted
    left to right) with box its (x0, y0, x1, y1) in 0..1, or None to skip it. One head: a thin box around
    the padded head and the label outside it. Several: a chip above each head with a leader line that stops
    at its padded edge, so nothing lands on a face even where the detector merged two heads."""
    role = "cv"

    def __init__(self, label, score=True):
        self.label, self.score = label, score

    def draw_frame(self, ov, st, img, t, t0, t1, avoid):
        raw, pad = ov.heads(t, pad=False), ov.heads(t)
        if not raw:
            return
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        s = ov.s
        fm = ov.font(st.mono_bold, 22)
        u = min(1.0, (t - t0) / 0.3)
        a = min(1.0, (t - t0) / 0.15) * min(1.0, (t1 - t) / 0.15)
        order = sorted(range(len(raw)), key=lambda i: raw[i][0])
        placed = []
        for rank, i in enumerate(order):
            box = (raw[i][0] / ov.w, raw[i][1] / ov.h, raw[i][2] / ov.w, raw[i][3] / ov.h)
            text = self.label(rank, box)
            if not text:
                continue
            pr = pad[i]
            others = [r for j, r in enumerate(raw) if j != i]
            tw, th = fm.getlength(text) + 18 * s, 36 * s
            lw = max(2, int(3 * s))
            if len(raw) == 1 or not any(_hit(pr, r) for r in others):
                d.rectangle(pr, outline=_rgba(st.accent, 235 * a), width=lw)
                chip = (pr[0], pr[1] - th - 6 * s, pr[0] + tw, pr[1] - 6 * s)
                if chip[1] < 0.05 * ov.h:
                    chip = (pr[0], pr[3] + 6 * s, pr[0] + tw, pr[3] + 6 * s + th)
                lead = None
            else:
                hx = (pr[0] + pr[2]) / 2
                x0 = max(0.03 * ov.w, min(0.97 * ov.w - tw, hx - tw / 2))
                chip = (x0, pr[1] - th - 40 * s, x0 + tw, pr[1] - 40 * s)
                lead = (hx, chip[3], pr[1])
            if chip[1] < 0.04 * ov.h or any(_hit(chip, r) for r in raw) or any(_hit(chip, r) for r in list(avoid) + placed):
                continue
            if lead and any(_hit((lead[0] - 2, lead[1], lead[0] + 2, lead[2]), r) for r in raw):
                continue
            placed.append(chip)
            if lead:
                d.line([(lead[0], lead[1]), (lead[0], lead[2])], fill=_rgba(st.accent, 230 * a), width=lw)
                d.ellipse((lead[0] - 5 * s, lead[2] - 5 * s, lead[0] + 5 * s, lead[2] + 5 * s), fill=_rgba(st.accent, 255 * a))
            d.rectangle(chip, fill=_rgba(st.ink, 230 * a), outline=_rgba(st.accent, 255 * a), width=max(1, int(2 * s)))
            d.text((chip[0] + 9 * s, (chip[1] + chip[3]) / 2), text[:max(1, int(len(text) * u))], font=fm,
                   fill=_rgba(st.accent, 255 * a), anchor="lm")
        img.alpha_composite(lay)
        avoid.extend(placed)


class Callout(Device):
    """A point in the frame (x, y in 0..1, for a locked or slow shot) with a ring that pulses on the beat
    and a leader to a chip with the text; rows are mono lines under it. The chip is placed clear of faces
    and other blocks; the leader is dropped if it would cross a face."""
    role = "cv"

    def __init__(self, xy, text, rows=()):
        self.xy, self.text, self.rows = xy, text, list(rows)

    def draw_frame(self, ov, st, img, t, t0, t1, avoid, key=None):
        s = ov.s
        px, py = self.xy[0] * ov.w, self.xy[1] * ov.h
        if any(_hit((px - 2, py - 2, px + 2, py + 2), r) for r in ov.heads(t, pad=False)):
            return
        fb, fm = ov.font(st.bold, 28), ov.font(st.mono, 20)
        tw = max([fb.getlength(self.text)] + [fm.getlength(r) for r in self.rows]) + 30 * s
        th = (48 + 28 * len(self.rows)) * s
        side = [px + 60 * s] if px < ov.w * 0.55 else [px - 60 * s - tw]
        x0, yc, k = ov.place(key or ("callout", self.xy, self.text), t0, t1, tw, th, side + [0.06 * ov.w, 0.94 * ov.w - tw],
                             py / ov.h, t=t, extra=tuple(avoid), scales=(1.0, 0.85))
        a = min(1.0, (t - t0) / 0.15) * min(1.0, (t1 - t) / 0.15)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        b = _beats(t, t0)
        ring = 10 * s + 26 * s * (b % 1.0)
        d.ellipse((px - ring, py - ring, px + ring, py + ring), outline=_rgba(st.accent, 220 * a * (1 - b % 1.0)),
                  width=max(2, int(3 * s)))
        d.ellipse((px - 7 * s, py - 7 * s, px + 7 * s, py + 7 * s), fill=_rgba(st.accent, 255 * a))
        cx = x0 if x0 > px else x0 + tw * k
        line = [(px, py), (cx, yc)]
        crosses = any(_hit((min(px, cx), min(py, yc), max(px, cx), max(py, yc)), r) for r in ov.heads(t, pad=False))
        grow = _ease_out((t - t0) / 0.25)   # the leader draws out of the point, then the chip opens on its end
        if not crosses:
            _stroke(lay, line, 0.0, grow, max(2, 3 * s), _rgba(st.accent, 230 * a))
            d = ImageDraw.Draw(lay)
        a *= _ease_out((t - t0 - 0.12) / 0.18)
        box = (x0, yc - th * k / 2, x0 + tw * k, yc + th * k / 2)
        d.rectangle(box, fill=_rgba(st.panel[:3], st.panel[3] * a), outline=_rgba(st.accent, 255 * a), width=max(1, int(2 * s)))
        n = int(len(self.text) * min(1.0, max(0.0, t - t0 - 0.12) / 0.3 + 0.1))
        d.text((x0 + 15 * s * k, box[1] + 26 * s * k), self.text[:n], font=ov.font(st.bold, 28 * k),
               fill=_rgba(st.text, 255 * a), anchor="lm")
        for i, r in enumerate(self.rows):
            d.text((x0 + 15 * s * k, box[1] + (56 + 28 * i) * s * k), r, font=ov.font(st.mono, 20 * k),
                   fill=_rgba(st.muted, 255 * a), anchor="lm")
        img.alpha_composite(lay)
        avoid.append(box)


class Mark(Device):
    """A hand-drawn mark that draws itself round a thing in the frame: kind "circle", "box", "underline" or
    "arrow". xy is the thing's centre and size its (width, height), all in 0..1 of the frame; for a locked or
    slow shot, like Callout. The stroke draws on over `beats` beats from t0, holds with a slow boil (three
    drawings of the same line, changing every third frame, like ink animated on threes), and is taken back
    from its start as it leaves. text is a short label outside the mark. An arrow points at xy from the side
    given by `side` ("left", "right", "above", "below"). Nothing is drawn on a frame where it would touch a
    face."""
    role = "cv"

    def __init__(self, xy, size=(0.12, 0.12), kind="circle", text=None, beats=0.5, side="right", boil=True,
                 color=None):
        self.xy, self.size, self.kind, self.text = xy, size, kind, text
        self.beats, self.side, self.boil, self.color = beats, side, boil, color

    def _path(self, ov, k):
        s = ov.s
        cx, cy = self.xy[0] * ov.w, self.xy[1] * ov.h
        rx, ry = self.size[0] * ov.w / 2, self.size[1] * ov.h / 2
        j = lambda i: (hash01("mark", self.xy, k, i) - 0.5) * 2 * 3.0 * s   # the hand: a few px of wobble
        if self.kind == "circle":           # a loop that overshoots its start, a little off-round
            return [(cx + math.cos(a) * rx * (1.05 - 0.07 * i / 52) + j(i // 4),
                     cy + math.sin(a) * ry * (1.05 - 0.07 * i / 52) + j(i // 4 + 99))
                    for i in range(53) for a in [math.radians(-110 + 400 * i / 52)]]
        if self.kind == "box":
            c = [(cx - rx, cy - ry), (cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry - 8 * s)]
            return [(x + j(i), y + j(i + 50)) for i, (x, y) in enumerate(c)]
        if self.kind == "underline":
            return [(cx - rx + 2 * rx * i / 8 + j(i), cy + ry + 6 * s + j(i + 50) * 0.6) for i in range(9)]
        dx, dy = {"left": (-1, 0), "right": (1, 0), "above": (0, -1), "below": (0, 1)}[self.side]
        far = (cx + dx * (rx + 150 * s), cy + dy * (ry + 150 * s))
        near = (cx + dx * (rx + 12 * s), cy + dy * (ry + 12 * s))
        mid = ((far[0] + near[0]) / 2 + dy * 26 * s + j(1), (far[1] + near[1]) / 2 - dx * 26 * s + j(2))
        return _smooth([far, mid, near], 8)[0]

    def draw_frame(self, ov, st, img, t, t0, t1, avoid):
        s = ov.s
        pts = self._path(ov, int(t * 24) // 3 % 3 if self.boil else 0)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        w = 6 * s
        rect = (min(xs) - w, min(ys) - w, max(xs) + w, max(ys) + w)
        if self.kind in ("circle", "box"):   # a ring: only its band can touch a face, not what it surrounds
            band = [(rect[0], rect[1], rect[2], rect[1] + 3 * w), (rect[0], rect[3] - 3 * w, rect[2], rect[3]),
                    (rect[0], rect[1], rect[0] + 3 * w, rect[3]), (rect[2] - 3 * w, rect[1], rect[2], rect[3])]
        else:
            band = [rect]
        heads = ov.heads(t, pad=False)
        if any(_hit(r, h) for r in band for h in heads):
            return
        on = _ease_io(_beats(t, t0) / max(self.beats, 1e-3))
        off = _ease_io(1 - (t1 - t) / 0.25)
        if on <= 0 or off >= 1:
            return
        col = self.color or st.accent
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _stroke(lay, pts, off, on, w + 5 * s, _rgba(st.ink, 235))   # a dark edge holds it on any picture
        got = _stroke(lay, pts, off, on, w, _rgba(col))
        if self.kind == "arrow" and got and on > 0.85:
            _head(lay, got[0], got[1], 26 * s, w + 5 * s, _rgba(st.ink, 235))
            _head(lay, got[0], got[1], 26 * s, w, _rgba(col))
        if self.text and on >= 1:
            f = ov.font(st.bold, 34)
            tw = f.getlength(self.text)
            if self.kind == "arrow":
                tx, ty = pts[0][0] - tw / 2, pts[0][1] + (-34 * s if self.side != "above" else -40 * s)
            else:
                tx, ty = (rect[0] + rect[2] - tw) / 2, rect[3] + 30 * s
                if ty > 0.9 * ov.h:
                    ty = rect[1] - 30 * s
            tx = min(max(tx, 0.04 * ov.w), 0.96 * ov.w - tw)
            box = (tx - 6 * s, ty - 24 * s, tx + tw + 6 * s, ty + 24 * s)
            if not any(_hit(box, h) for h in ov.heads(t)) and not any(_hit(box, r) for r in avoid):
                a = _ease_out((_beats(t, t0) - self.beats) / 0.5) * (1 - off)
                ImageDraw.Draw(lay).text((tx, ty), self.text, font=f, fill=_rgba(st.text, 255 * a), anchor="lm",
                                         stroke_width=max(2, int(4 * s)), stroke_fill=_rgba(st.ink, 255 * a))
                avoid.append(box)
        img.alpha_composite(lay)


# ------------------------------------------------------------------------------------------------ plan

class Plan:
    """The devices of a video, with their times and placement, drawn under the frame budget."""
    BUDGET = {"hero": 1, "cv": 2, "micro": 2, "sticker": 3}

    def __init__(self, style):
        self.style = style
        self.items = []
        self._warned = False

    def add(self, dev, t0, dur, prefer=0.3, xs=None, lead=None):
        """Show dev from t0 for dur seconds. prefer: the centre line wanted (fraction of the height); xs: left
        edges to try as fractions of the width (default: left margin, centre, right margin). lead: seconds
        before t0 that a panel starts rising (default the device's own, 0.2 s for panels), so it has settled
        when the word is sung; what the device shows starts moving on t0."""
        if dur < 1.2 and not self._warned:
            print(f"devices: {type(dev).__name__} at {t0:.2f}s is on screen {dur:.2f}s; give a graphic at least "
                  f"1.2 s to read")
            self._warned = True
        lead = (0.0 if dev.role == "cv" else dev.lead) if lead is None else lead
        self.items.append({"dev": dev, "t0": t0, "t1": t0 + dur, "prefer": prefer, "xs": xs, "id": len(self.items),
                           "show": max(0.0, t0 - lead)})
        return dev

    def starts(self):
        return sorted({it["show"] for it in self.items})

    def active(self, t):
        on = [it for it in self.items if it["show"] <= t < it["t1"]]
        keep = []
        for role, n in self.BUDGET.items():
            mine = sorted((it for it in on if it["dev"].role == role), key=lambda it: it["t0"])
            keep += mine[-n:]
        return sorted(keep, key=lambda it: it["t0"])

    def draw(self, ov, img, t, avoid=()):
        """Draw the devices on screen at t onto img (the front layer), clear of faces, of the rects in avoid
        (this frame's lyric blocks) and of each other. Returns the rects the devices took."""
        st = self.style
        taken = list(avoid)
        out = []
        for it in self.active(t):
            dev = it["dev"]
            if dev.role == "cv":
                before = len(taken)
                if isinstance(dev, Callout):
                    dev.draw_frame(ov, st, img, t, it["t0"], it["t1"], taken, key=("dev", it["id"]))
                else:
                    dev.draw_frame(ov, st, img, t, it["t0"], it["t1"], taken)
                out += taken[before:]
                continue
            bw, bh = dev.size(ov)
            lift = 36 * ov.s
            xs = [f * ov.w for f in it["xs"]] if it["xs"] else [0.06 * ov.w, (ov.w - bw) / 2, 0.94 * ov.w - bw]
            x, yc, k = ov.place(("dev", it["id"]), it["show"], it["t1"], bw, bh + lift, xs, it["prefer"], t=t,
                                extra=tuple(taken))
            rect = (x, yc - bh * k / 2, x + bw * k, yc + bh * k / 2)
            if ov.touches_face(rect, t):
                continue
            tl = dev.tile(ov, st, max(t, it["t0"]), it["t0"], it["t1"])
            if k < 1.0:
                tl = tl.resize((max(1, int(tl.size[0] * k)), max(1, int(tl.size[1] * k))), Image.LANCZOS)
            rise = it["t0"] - it["show"]
            a_in = _ease_out((t - it["show"]) / (rise if rise >= 0.12 else 0.22))
            a = a_in * min(1.0, (it["t1"] - t) / 0.15)
            dy = (1 - a_in) * lift
            if a < 0.999:
                tl.putalpha(tl.getchannel("A").point(lambda v: int(v * a)))
            pos = (int(rect[0]), int(rect[1] + dy))
            if getattr(dev, "panel", lambda: True)():
                _shadow(img, tl.getchannel("A"), pos, 0.5 * a, int(16 * ov.s))
                if st.glass:
                    ov.add_glass((pos[0], pos[1], pos[0] + tl.size[0], pos[1] + tl.size[1]), st.radius * ov.s * k, a, t=t)
            img.alpha_composite(tl, pos)
            taken.append(rect)
            out.append(rect)
        return out
