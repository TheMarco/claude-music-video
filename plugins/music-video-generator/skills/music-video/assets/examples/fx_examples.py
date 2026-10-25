"""Worked examples of per-video effects for mv/scripts/fx.py. Read them for the mechanics, then invent
effects that belong to the song you are working on; don't paste these in as a set. All four leave the
footage as footage: three are overlays, one is a one-beat accent.

1. Film light leak that sweeps across the frame on every bar's downbeat (final pass).
2. Drop accent: one beat of heavy chromatic aberration after each drop, by overriding the engine's ca.
3. Rim glow: the person's edge lights up warm on each kick (uses the person matte, composite pass).
4. Embers: sparks rising from the bottom edge, lit by the hi-hats (overlay, front layer).
"""
import math

from PIL import ImageDraw  # noqa: F401  (handy for draw_* hooks)

from timing import BEAT, DROPS

UNIFORMS = {"leak": 0.0, "leakX": 0.5, "rim": 0.0}

GLSL_COMP = """
vec3 fxComp(vec3 col, vec2 uv, float matte){
  // 3. rim glow: the soft edge of the matte (matte near 0.5) lights up
  float edge = clamp(matte*(1.0 - matte)*4.0, 0.0, 1.0);
  return col + rim*edge*vec3(1.0, 0.55, 0.25);
}
"""

GLSL_FINAL = """
vec3 fxFinal(vec3 col, vec2 uv, vec2 p){
  // 1. light leak: a warm soft blob crossing the frame
  vec2 d = vec2((uv.x - leakX)*ASP, (uv.y - 0.65)*1.4);
  float blob = exp(-dot(d, d)*3.0);
  col += leak*blob*vec3(1.0, 0.45, 0.15);
  col = mix(col, 1.0 - (1.0 - col)*(1.0 - vec3(1.0,0.6,0.3)*blob*0.35), leak);
  return col;
}
"""


def uniforms(t, a):
    bar_phase = ((a["beat"] % 4) * a["BEAT"] + a["phase"]) / (4 * a["BEAT"])   # 0..1 across each bar
    out = {
        "leak": 0.0 if a["calm"] else 0.55 * math.exp(-bar_phase * 3.5),
        "leakX": -0.2 + 1.4 * bar_phase,
        "rim": 1.5 * a["kick"] if a["kick_level"] > 0.6 else 0.0,
    }
    for td in DROPS:   # 2. drop accent: overriding an engine uniform for one beat
        if 0 <= t - td < BEAT:
            out["ca"] = 0.03 * (1 - (t - td) / BEAT)
    return out


def draw_front(ov, d, t, f, ctx):
    # 4. embers rising from the bottom, brightness from the hi-hats
    if ov.kick_level(t) < 0.3:
        return
    for i in range(60):
        speed = 60 + 140 * ((i * 37) % 11) / 11
        x = ((i * 0.618034) % 1.0) * ov.w + 30 * ov.s * math.sin(t * 1.3 + i)
        y = ov.h - ((t * speed * ov.s + i * 97) % (ov.h * 0.8))
        r = (1.5 + (i % 3)) * ov.s
        a = int((60 + 190 * ov.hat[f]) * (y / ov.h))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 170, 80, max(0, min(255, a))))


def draw_behind(ov, img, t, f, ctx):
    pass
