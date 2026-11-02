"""Worked examples of per-video effects for mv/scripts/fx.py. Read them for the mechanics, then invent
effects that belong to the song you are working on; don't paste these in as a set. All of them leave
the footage as footage: overlays, light, a transition and a one-beat accent.

1. Film light leak that sweeps across the frame on every bar's downbeat (final pass).
2. Drop accent: one beat of heavy chromatic aberration after each drop, by overriding the engine's ca.
3. Rim glow: the person's edge lights up warm on each kick (uses the person matte, composite pass).
4. Embers: rising sparks drawn as motion-blur streaks, lit by the hi-hats (overlay, front layer).
5. A transition of this video's own, x="tear" in the EDL: the old shot rips down a ragged line and
   both halves pull apart over the new one (GLSL_MIX).
6. Light rays from a lamp tracked with track.py ("lamp"), built from the picture's own bloom and
   pulsing with the kick (uniforms from a["track"], final pass).
7. Kinetic type: the title's letters land one by one on the first drop, overshoot and settle, hold for
   a bar, then leave upward faster than they came (glyphs, stagger, easing).
"""
import math

from overlay import FS, ease_in, ease_out_back, stagger
from timing import BEAT, DROPS, TITLE

UNIFORMS = {"leak": 0.0, "leakX": 0.5, "rim": 0.0, "rays": 0.0, "raysXY": (0.5, 0.5)}

GLSL_COMP = """
vec3 fxComp(vec3 col, vec2 uv, float matte){
  // 3. rim glow: the soft edge of the matte (matte near 0.5) lights up
  float edge = clamp(matte*(1.0 - matte)*4.0, 0.0, 1.0);
  return col + rim*edge*vec3(1.0, 0.55, 0.25);
}
"""

TRANSITIONS = ["tear"]

GLSL_MIX = """
vec3 fxMix(vec3 a, vec3 b, float mA, float mB, float u, vec2 uv, float kind){
  // 5. tear: a ragged vertical line; the halves of the old shot slide apart, accelerating like a pull
  float off = u*u*u*0.6;
  float edge = 0.5 + 0.035*gnoise(vec2(uv.y*9.0, 3.1)) + 0.012*gnoise(vec2(uv.y*37.0, 7.7));
  vec2 qL = uv + vec2(off, 0.0), qR = uv - vec2(off, 0.0);
  vec3 c = b;
  float d = 1.0;
  if (qL.x < edge){ c = sampleA(qL); d = edge - qL.x; }
  else if (qR.x >= edge){ c = sampleA(qR); d = qR.x - edge; }
  return c + smoothstep(0.01, 0.0, d)*step(0.002, off)*vec3(1.0, 0.85, 0.6)*(1.0 - u);   // hot torn edge
}
"""

GLSL_FINAL = """
vec3 fxFinal(vec3 col, vec2 uv, vec2 p){
  // 1. light leak: a warm soft blob crossing the frame
  vec2 d = vec2((uv.x - leakX)*ASP, (uv.y - 0.65)*1.4);
  float blob = exp(-dot(d, d)*3.0);
  col += leak*blob*vec3(1.0, 0.45, 0.15);
  col = mix(col, 1.0 - (1.0 - col)*(1.0 - vec3(1.0,0.6,0.3)*blob*0.35), leak);
  // 6. light rays: march from each pixel toward the light through the bloom texture
  if (rays > 0.0){
    vec2 st = (raysXY - p)/28.0, q = p;
    vec3 acc = vec3(0.0);
    float w = 1.0;
    for (int i = 0; i < 28; i++){ q += st; acc += texture(tB1, q).rgb*w; w *= 0.93; }
    col += acc/28.0*rays;
  }
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
    lamp = a["track"]("lamp")   # 6. None outside the tracked shot or where the track was lost
    out["rays"] = 0.0 if lamp is None else 1.4 * (0.5 + a["pulse"])
    out["raysXY"] = lamp or (0.5, 0.5)
    return out


def draw_front(ov, d, t, f, ctx):
    # 4. embers rising from the bottom as short streaks, brightness from the hi-hats
    if ov.kick_level(t) >= 0.3:
        for i in range(60):
            speed = (60 + 140 * ((i * 37) % 11) / 11) * ov.s
            sway = 30 * ov.s * math.cos(t * 1.3 + i) * 1.3      # derivative of the sideways drift
            x = ((i * 0.618034) % 1.0) * ov.w + 30 * ov.s * math.sin(t * 1.3 + i)
            y = ov.h - ((t * speed + i * 97 * ov.s) % (ov.h * 0.8))
            a = int((60 + 190 * ov.hat[f]) * (y / ov.h))
            ov.streak(d, (x, y), (sway, -speed), (1.5 + (i % 3)) * ov.s, (255, 170, 80, max(0, min(255, a))))

    # 7. the title's letters land one by one on the first drop
    if not DROPS:
        return
    td = DROPS[0]
    if not td - 0.05 <= t < td + 4 * BEAT + 0.6:
        return
    fnt = ov.font((FS + "DIN Condensed Bold.ttf", 0), 230)
    word = (TITLE or "TITLE").upper()
    glyphs, total = ov.glyphs(word, fnt, 10 * ov.s)
    x0, base = ov.w / 2 - total / 2, ov.h * 0.6
    for i, (c, x, w) in enumerate(glyphs):
        land = stagger(t, td, i, len(glyphs), 0.6 * BEAT, 0.5 * BEAT, ease_out_back)      # in: decelerate
        leave = stagger(t, td + 4 * BEAT, i, len(glyphs), 0.3 * BEAT, 0.25 * BEAT, ease_in)  # out: faster
        y = base - (1 - land) * 240 * ov.s - leave * 420 * ov.s
        alpha = int(255 * min(1.0, max(0.0, land) * 3) * (1 - leave))
        d.text((x0 + x, y), c, font=fnt, fill=(255, 245, 230, alpha), anchor="ls")


def draw_behind(ov, img, t, f, ctx):
    pass
