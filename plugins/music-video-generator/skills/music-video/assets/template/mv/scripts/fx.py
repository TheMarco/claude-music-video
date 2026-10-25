"""This video's own effects and graphics. The engine has no style of its own: everything the viewer
sees beyond the graded footage is designed here, for this song (SKILL.md Phase 5), together with
look.py (palettes, grades, finish). Starting empty is deliberate. Don't paste in another video's fx.py.

Usually this includes the title and artist moment, the end card with any credits the footage's
licenses require, and the 3-6 signature overlays from the concept. Some videos need no graphics at all.
Overlays sit on top of the footage; the shaders don't restyle the whole picture except as a short
accent on a hit (SKILL.md Phase 5).

UNIFORMS      {name: default}: extra shader uniforms (float, or a 2/3/4-tuple for vec2/vec3/vec4).
GLSL_COMP     defines vec3 fxComp(vec3 col, vec2 uv, float matte): runs on the composited picture before
              feedback (echo/trails) and overlays. matte is the person matte (0..1), so silhouettes,
              outlines and background-only effects are possible.
GLSL_FINAL    defines vec3 fxFinal(vec3 col, vec2 uv, vec2 p): runs in the final pass after bloom and
              before vignette and grain. uv is the screen position, p the distorted sample position.
              Available GLSL helpers: hash(vec2), gnoise(vec2), mrep(vec2), ASP (output aspect), time.
uniforms(t, a)  returns {name: value} per frame. a has: kick, snare, hat, rms (0..1 envelopes), spec
              (48 bands), pulse (the engine's beat-locked kick envelope), beat (index), phase (seconds
              since the beat), section, kick_level (section), calm, src (shot code), local (seconds into
              the shot), shot (the EDL shot dict, custom per-shot options included), BEAT.
              Returning an engine uniform overrides it for that frame: bloom, glint, halation, grain,
              vignette, ca, punch, flash, invert, scan, letterbox, fade, shockT/shockAmp.
draw_behind(ov, img, t, f, ctx) draws on an RGBA canvas that sits behind the person matte.
draw_front(ov, d, t, f, ctx)    draws over everything with the PIL ImageDraw d.
              ov is the Overlay (overlay.py lists its helpers: fonts, fit, tracked text, layers, lyric
              timing, audio arrays indexed by frame f, kick and snare onsets). ctx has the shot's src,
              label, local time and duration.

Prototype each effect on a still sheet before a full render. references/effects-ideas.md has the
method; assets/examples/fx_examples.py shows the mechanics.
"""
from overlay import F, FS, hash01, keyframes  # noqa: F401  (font folders and helpers)

UNIFORMS = {}

GLSL_COMP = """
vec3 fxComp(vec3 col, vec2 uv, float matte){ return col; }
"""

GLSL_FINAL = """
vec3 fxFinal(vec3 col, vec2 uv, vec2 p){ return col; }
"""


def uniforms(t, a):
    return {}


def draw_behind(ov, img, t, f, ctx):
    pass


def draw_front(ov, d, t, f, ctx):
    pass
