"""Particles that live in the shot: embers, snow, dust, sparks, rain, drawn on the GPU at a depth in the scene.

Each particle has a place in the frame and a depth (0 far .. 1 near). On a shot with a depth map
(make_depth.py) it is hidden wherever the scene is nearer than it is, so an ember rises behind a tower and in
front of the crowd; on a shot with only a person matte, particles further than `person` (0.6) pass behind the
person. Far particles are smaller and dimmer. They are drawn over the footage and under every graphic and
word, and none is drawn on a face (they fade out toward a head box).

In fx.py:
    import particles as PT
    PARTICLES = [PT.Emitter(count=260, area=(0.0, 1.0, 1.0, 1.05), vel=(0.0, -0.16), spread=(0.03, 0.05),
                            turb=0.035, life=(3.0, 6.0), size=(3, 9), color=(1.0, 0.55, 0.2), end=(1.0, 0.2, 0.05),
                            gain=lambda t, a: 0.4 + 1.2 * a["hat"])]

PARTICLES is a list of emitters, or a function (t, a) -> list, to change them by section. `a` is the dict
fx.uniforms gets (kick, snare, hat, rms, section, kick_level, calm, shot, ...).

Emitter(count, area, vel, spread, gravity, drag, turb, turb_rate, life, size, z, color, end, alpha, stretch,
        blend, burst, gain, seed):
  count      particles alive at any time (or per burst)
  area       (x0, y0, x1, y1) where they are born, in 0..1 of the frame, y down; outside the frame is fine
             (a strip under the bottom edge for embers, above the top for snow)
  vel        (vx, vy) frame heights per second at birth; spread: the random part added to it
  gravity    frame heights per second squared, down positive (snow 0.02, sparks 0.6)
  drag       how fast the birth velocity dies away, per second (0 none; sparks 1.5)
  turb       how far the air pushes a particle sideways and up and down, in frame heights; turb_rate: how
             fast that changes (0.25 slow drift, 1.0 flutter)
  life       (shortest, longest) seconds; each fades in over its first tenth and out over its last third
  size       (smallest, largest) radius in 1080p pixels for a particle at depth 1; far ones are smaller
  z          (far, near) depth range they are spread over; default the whole scene (0.05, 1.0)
  color/end  RGB 0..1 at birth and at death (end defaults to color)
  alpha      overall strength 0..1
  stretch    0 for round particles; above 0 they stretch along their motion into streaks (rain 6, sparks 2)
  blend      "add" (light: embers, sparks, dust in a beam) or "alpha" (matter: snow, ash, petals, confetti)
  burst      None for a steady stream, or a list of song times: `count` particles are born at each
  gain       None, or a function (t, a) -> brightness multiplier (the hi-hat, the section's energy); 0 hides
  person     depth the person stands at on shots with a matte and no depth map (default 0.6)

A particle's whole path is a formula of its age, so a still, a part render and the full render show the same
particles at the same time. Keep the count to what reads: a few hundred is weather, a few thousand is fog.
The particles are overlays like any other: the footage stays the picture.
"""
import numpy as np


def _rnd(i, n, k):
    """Stable random numbers in 0..1 for particle i in its n-th life, channel k."""
    x = np.sin(i * 12.9898 + n * 78.233 + k * 37.719) * 43758.5453
    return x - np.floor(x)


class Emitter:
    def __init__(self, count=200, area=(0.0, 1.0, 1.0, 1.05), vel=(0.0, -0.15), spread=(0.03, 0.05), gravity=0.0,
                 drag=0.0, turb=0.03, turb_rate=0.35, life=(3.0, 6.0), size=(3, 8), z=(0.05, 1.0),
                 color=(1.0, 1.0, 1.0), end=None, alpha=1.0, stretch=0.0, blend="add", burst=None, gain=None,
                 person=0.6, seed=1):
        self.count, self.area, self.vel, self.spread = int(count), area, vel, spread
        self.gravity, self.drag, self.turb, self.turb_rate = gravity, drag, turb, turb_rate
        self.life, self.size, self.z = life, size, z
        self.color, self.end = np.array(color, "f4"), np.array(end if end is not None else color, "f4")
        self.alpha, self.stretch, self.blend, self.burst, self.gain = alpha, stretch, blend, burst, gain
        self.person, self.seed = person, seed

    def _pos(self, i, n, age, t):
        r = lambda k: _rnd(i + self.seed * 131.0, n, k)
        x0 = self.area[0] + (self.area[2] - self.area[0]) * r(1)
        y0 = self.area[1] + (self.area[3] - self.area[1]) * r(2)
        vx = self.vel[0] + self.spread[0] * (r(3) * 2 - 1)
        vy = self.vel[1] + self.spread[1] * (r(4) * 2 - 1)
        # the birth velocity dies away with drag; gravity keeps pulling
        reach = age if self.drag <= 0 else (1 - np.exp(-self.drag * age)) / self.drag
        x = x0 + vx * reach
        y = y0 + vy * reach + 0.5 * self.gravity * age * age
        # the air: two slow waves per axis, each particle in its own phase, growing in over the first second
        w, ph = self.turb_rate * 6.2832, r(5) * 6.2832
        grow = np.minimum(age, 1.0)
        x = x + self.turb * grow * (np.sin(w * t + ph) * 0.6 + np.sin(w * 2.3 * t + ph * 1.7 + y0 * 9) * 0.4)
        y = y + self.turb * 0.5 * grow * (np.sin(w * 1.3 * t + ph * 2.1) * 0.6 + np.sin(w * 2.9 * t + ph + x0 * 7) * 0.4)
        return x, y

    def at(self, t, a=None, asp=16 / 9, heads=(), frame=(1920, 1080)):
        """The particles alive at song time t as a float32 array, one row each:
        x, y (frame 0..1, y down), radius (frame heights), depth, r, g, b, alpha, streak x, streak y, add."""
        g = 1.0 if self.gain is None else float(self.gain(t, a or {}))
        if g <= 0 or self.count <= 0:
            return np.zeros((0, 11), "f4")
        i = np.arange(self.count, dtype="f8")
        life = self.life[0] + (self.life[1] - self.life[0]) * _rnd(i + self.seed * 131.0, 0.0, 6)
        if self.burst is None:
            born = -life * _rnd(i + self.seed * 131.0, 0.0, 7)       # spread over a life, so the stream is steady
            n = np.floor((t - born) / life)
            age = (t - born) - n * life
            live = np.ones(self.count, bool)
        else:
            tb = np.array([b for b in self.burst if b <= t] or [-1e9])[-1]
            n = np.full(self.count, float(sum(1 for b in self.burst if b <= t)))
            age = np.full(self.count, t - tb)
            live = age < life
        x, y = self._pos(i, n, age, t)
        x1, y1 = self._pos(i, n, age + 1 / 48, t + 1 / 48)
        r = lambda k: _rnd(i + self.seed * 131.0, n, k)
        z = self.z[0] + (self.z[1] - self.z[0]) * r(8)
        u = age / life
        fade = np.clip(u / 0.1, 0, 1) * np.clip((1 - u) / 0.33, 0, 1)
        near = 0.35 + 0.65 * z
        rad = (self.size[0] + (self.size[1] - self.size[0]) * r(9)) / 1080.0 * near
        col = self.color[None, :] * (1 - u[:, None]) + self.end[None, :] * u[:, None]
        al = self.alpha * fade * (0.45 + 0.55 * z) * g
        for hx0, hy0, hx1, hy1 in heads:     # nothing on a face: fade out toward every head box
            px, py = x * frame[0], y * frame[1]
            dx = np.maximum(np.maximum(hx0 - px, px - hx1), 0)
            dy = np.maximum(np.maximum(hy0 - py, py - hy1), 0)
            al = al * np.clip((np.hypot(dx, dy) - rad * frame[1]) / (0.03 * frame[1]), 0, 1)
        sx, sy = (x1 - x) * 48 * self.stretch * asp * 0.04, (y1 - y) * 48 * self.stretch * 0.04
        keep = live & (al > 0.003) & (x > -0.1) & (x < 1.1) & (y > -0.1) & (y < 1.1)
        out = np.stack([x, y, rad, z, col[:, 0], col[:, 1], col[:, 2], al, sx, sy,
                        np.full(self.count, 1.0 if self.blend == "add" else 0.0)], 1)[keep]
        return out.astype("f4")


def frame(emitters, t, a, asp, heads, size):
    """Every emitter's particles at t, far ones first, with the person depth for matte-only shots."""
    if callable(emitters):
        emitters = emitters(t, a)
    rows = [e.at(t, a, asp, heads, size) for e in (emitters or [])]
    rows = [r for r in rows if len(r)]
    if not rows:
        return None, 0.6
    p = np.concatenate(rows)
    return p[np.argsort(p[:, 3], kind="stable")], float(min(e.person for e in emitters))


VERT = """
#version 330
in vec2 corner;
in vec4 pz;      // x, y (frame, y down), radius (frame heights), depth
in vec4 pcol;    // rgb, alpha
in vec3 pdir;    // streak x, y (frame heights), additive flag
out vec2 c; out vec4 col; out float z; out float add;
void main(){
  vec2 ctr = vec2(pz.x, 1.0 - pz.y);
  vec2 s = vec2(pdir.x, -pdir.y);
  float len = length(s);
  vec2 ax = len > 1e-5 ? s/len : vec2(0.0, 1.0);
  vec2 off = (ax*corner.y*(pz.z + len) + vec2(ax.y, -ax.x)*corner.x*pz.z)*1.6;
  off.x /= ASP_VALUE;
  gl_Position = vec4((ctr + off)*2.0 - 1.0, 0.0, 1.0);
  c = corner*1.6; col = pcol; z = pz.w; add = pdir.z;
}
"""

FRAG = """
#version 330
uniform sampler2D tAux;     // pass 1: depth, person matte, whether the shot has a depth map
uniform vec2 res;
uniform float person;
in vec2 c; in vec4 col; in float z; in float add;
out vec4 o;
void main(){
  float d = length(c);
  float a = smoothstep(1.6, 0.0, d);
  a = a*a*col.a + smoothstep(0.55, 0.0, d)*col.a*0.6;     // a soft body and a brighter core
  vec4 sc = texture(tAux, gl_FragCoord.xy/res);
  float vis = sc.b > 0.5 ? smoothstep(-0.035, 0.035, z - sc.r)        // nearer than the scene here
                         : 1.0 - sc.g*step(z, person);                // or, matte only: behind the person
  a = clamp(a*vis, 0.0, 1.0);
  o = vec4(col.rgb*a, a*(1.0 - add));
}
"""
