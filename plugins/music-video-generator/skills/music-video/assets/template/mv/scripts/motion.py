"""Motion helpers shared by the compositor, the overlays and fx.py. No project imports, so every script
can use it.

Easing (u in 0..1 -> 0..1): ease (smooth in and out, the engine's default), ease_in, ease_out,
ease_in_out (cubic), ease_in_expo, ease_out_expo, ease_out_back (overshoots and settles).
Entrances decelerate (ease_out), exits accelerate (ease_in), moves between two rests use ease_in_out.
Only rotation and slow drifts run at constant speed.

keyframes(t, [(t, v), (t, v, ease_out), ...])  value at t; values may be numbers or tuples, and the ease
                                               on a point shapes the move that starts there
since(t, times) -> (seconds since the last time <= t, its index), or (inf, -1)
hit(t, times, decay, attack=0.0) -> 0..1 envelope that jumps at each time and decays (decay in seconds)
stagger(t, start, i, n, each, spread, ease=ease_out) -> progress of item i of n, the items starting
                                               spread seconds apart in total, each taking each seconds

The shot camera and its time map, used by render.py, overlay.py, contact.py and track.py:
shot_xform(seg, local) -> (zoom, offx, offy, rot) of an EDL shot at local seconds into it
seg_to_screen(seg, local, x, y, asp) -> where a point of the cut segment (0..1 from its top left) is
                                        on screen (0..1 from the top left) for output aspect asp
src_elapsed(seg, local) -> source seconds played since the in-point (speed, ramp and loop applied)
seg_time(seg, local)    -> seconds into the prepared segment file
base_speed(seg)         -> the speed the segment file is cut at
"""
import bisect
import math


# ---- easing ---------------------------------------------------------------
def clamp01(u):
    return 0.0 if u <= 0.0 else 1.0 if u >= 1.0 else u


def linear(u):
    return clamp01(u)


def ease(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def ease_in(u):
    u = clamp01(u)
    return u * u * u


def ease_out(u):
    u = clamp01(u)
    return 1 - (1 - u) ** 3


def ease_in_out(u):
    u = clamp01(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def ease_in_expo(u):
    u = clamp01(u)
    return 0.0 if u == 0 else 2 ** (10 * u - 10)


def ease_out_expo(u):
    u = clamp01(u)
    return 1.0 if u == 1 else 1 - 2 ** (-10 * u)


def ease_out_back(u, s=1.70158):
    u = clamp01(u)
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


def _lerp(a, b, u):
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * u for x, y in zip(a, b))
    return a + (b - a) * u


def keyframes(t, pts, ease=None):
    """Value at t from [(t, v), ...] or [(t, v, ease_fn), ...]. A point's ease shapes the move that
    starts at it (default: the ease argument, else linear). Holds the first value before the first point
    and the last after the last."""
    if t <= pts[0][0]:
        return pts[0][1]
    for p, q in zip(pts, pts[1:]):
        a, b = p[0], q[0]
        if a <= t < b:
            fn = p[2] if len(p) > 2 else ease or linear
            return _lerp(p[1], q[1], fn((t - a) / (b - a)))
    return pts[-1][1]


def since(t, times):
    """(seconds since the most recent time <= t, its index), or (inf, -1) before the first."""
    i = bisect.bisect_right(list(times), t) - 1
    return (t - times[i], i) if i >= 0 else (math.inf, -1)


def hit(t, times, decay, attack=0.0):
    """Envelope 0..1 that rises at each time (over attack seconds) and decays with time constant decay."""
    dt, i = since(t + attack, times)
    if i < 0:
        return 0.0
    dt -= attack
    if dt < 0:
        return clamp01(1 + dt / attack) if attack > 0 else 0.0
    return math.exp(-dt / decay)


def stagger(t, start, i, n, each, spread, ease=ease_out):
    """Progress 0..1 of item i of n: items start spread seconds apart in total and each takes each
    seconds. Keep spread within a beat or so; longer cascades read as slow."""
    s = start + (spread * i / (n - 1) if n > 1 else 0.0)
    return ease((t - s) / each) if each > 0 else float(t >= s)


# ---- the shot's camera ------------------------------------------------------
def shot_xform(seg, local):
    """(zoom, offx, offy, rot) of an EDL shot at local seconds: the move from zoom/pan over the shot,
    handheld shake, rotation and spin. render.py sends this to the shader."""
    u = ease(local / max(seg["dur"], 1e-3))
    z0, z1 = seg.get("zoom", (1.0, 1.06))
    p0, p1 = seg.get("pan", ((0, 0), (0, 0)))
    z = z0 + (z1 - z0) * u
    shake = seg.get("shake", 0.0)
    sx = shake * (math.sin(local * 37.0) * 0.6 + math.sin(local * 23.0) * 0.4) * 0.01
    sy = shake * (math.cos(local * 31.0) * 0.6 + math.sin(local * 17.0) * 0.4) * 0.01
    return (z, p0[0] + (p1[0] - p0[0]) * u + sx, p0[1] + (p1[1] - p0[1]) * u + sy,
            seg.get("rot", 0.0) + seg.get("spin", 0.0) * local)


SRC_ASP = 16 / 9


def seg_to_screen(seg, local, x, y, asp):
    """Screen position (0..1 from the top left, may fall outside) of point (x, y) of the cut segment
    (0..1 from its top left), for output aspect asp: the inverse of the shader's xform. Mirrored shots
    map to the visible half; kaleidoscope shots have no single answer and are ignored."""
    z, ox, oy, rot = shot_xform(seg, local)
    if seg.get("mirror") and x > 0.5:
        x = 1 - x
    cx, cy = (x - 0.5 - ox) * z * SRC_ASP, (0.5 - y - oy) * z   # image y down -> shader y up
    cs, sn = math.cos(rot), math.sin(rot)
    px, py = cs * cx - sn * cy, sn * cx + cs * cy
    return px / asp + 0.5, 0.5 - py


# ---- the shot's time --------------------------------------------------------
def _ramp(seg):
    r = seg.get("ramp")
    if not r:
        return None
    return sorted(((float(a), max(0.0, float(s))) for a, s in r), key=lambda p: p[0])


def base_speed(seg):
    """Speed the segment file is cut at: the shot's speed, or for a ramp its slowest moving speed."""
    r = _ramp(seg)
    if not r:
        return seg.get("speed", 1.0)
    moving = [s for _, s in r if s > 0]
    return min(moving) if moving else 1.0


def _integrate(r, tau):
    """Integral of the piecewise-linear speed r = [(time, speed), ...] from 0 to tau (flat outside)."""
    total, prev_t, prev_s = 0.0, 0.0, r[0][1]
    for t, s in r:
        if t <= prev_t:
            prev_s = s
            continue
        if tau <= t:
            s_tau = prev_s + (s - prev_s) * (tau - prev_t) / (t - prev_t)
            return total + (prev_s + s_tau) / 2 * (tau - prev_t)
        total += (prev_s + s) / 2 * (t - prev_t)
        prev_t, prev_s = t, s
    return total + prev_s * (tau - prev_t)


def src_elapsed(seg, local):
    """Source seconds played since the in-point at local seconds into the shot."""
    loop = seg.get("loop")
    if loop:
        local = local % loop
    local = max(local, 0.0)
    r = _ramp(seg)
    if not r:
        return local * seg.get("speed", 1.0)
    return _integrate(r, local)


def seg_time(seg, local):
    """Seconds into the prepared segment file at local seconds into the shot."""
    if not seg.get("ramp") and not seg.get("loop"):
        return max(local, 0.0)
    return src_elapsed(seg, local) / base_speed(seg)


def src_needed(seg, out_dur):
    """Source seconds the shot uses over out_dur seconds of output."""
    loop = seg.get("loop")
    return src_elapsed(seg, min(out_dur, loop - 1e-6) if loop else out_dur)
