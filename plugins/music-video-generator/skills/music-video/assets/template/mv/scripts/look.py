"""This video's look: palettes, grades and the finish applied to every frame. render.py reads it.

Every value here is a decision for this video (SKILL.md Phase 5), made from the user's brief first.
The finish is craft, not identity: grain, glow, contrast and a beat punch are what give a music video
its weight, and they recur whenever the mood calls for them. Pick the STARTS entry that matches the
brief's mood, then tune. "none" is for concepts whose whole finish is built in fx.py; with a pale grade
it reads flat.
For anything the FINISH values can't express, fx.uniforms() can return any engine uniform per frame
(bloom, glint, grain, vignette, ca, punch, flash, letterbox...) and it overrides the value below.
"""
from timing import LETTERBOX, SHOCKS  # noqa: F401  (the analyzer's suggestions, for FINISH below)

# Gradient-map palettes: 5 color stops from shadows to highlights. A grade maps luminance through
# one of these (palette index) and blends it with the original by gm (0 = untouched, 1 = full map).
# Write this video's own maps; these two are only placeholders.
PALETTES = [
    [(.02, .02, .025), (.16, .14, .13), (.50, .45, .40), (.86, .80, .70), (1., .97, .92)],  # 0 neutral film
    [(0., 0., 0.), (.12, .12, .12), (.45, .45, .45), (.85, .85, .85), (1., 1., 1.)],      # 1 black and white
]
GRADES = {  # gm (palette blend), palette index, saturation, contrast, lift, exposure
    "orig": (0.0, 0, 1.0, 1.0, 0.0, 1.0),
    "base": (0.25, 0, 1.05, 1.08, 0.01, 1.0),     # edl.py ARCHIVE_GRADE default: unifies film stocks
    "ai": (0.12, 0, 1.06, 1.08, 0.0, 1.0),        # edl.py AI_GRADE default
    "dim": (0.15, 0, 1.0, 1.12, 0.0, 0.66),       # tames shots that bloom out
    "mono": (1.0, 1, 0.0, 1.15, 0.0, 1.0),
}
SHADOW_TINT = (0.0, 0.0, 0.0)  # color added to shadows in the final pass, e.g. (0.025, 0.0, 0.05) violet

# The finish. Pairs are (AI clips, archive/library shots) unless noted. 0 or [] switches a thing off.
OFF = dict(
    grain=(0.0, 0.0),       # film grain (the clumped, per-dye-layer model); 0.09-0.16 reads as 35-16 mm
    bloom=(0.0, 0.0),       # glow from bright areas
    bloom_kick=0.0,         # bloom added by the beat pulse
    bloom_loud=0.0,         # bloom added by loudness
    bloom_calm=1.0,         # bloom multiplier in calm sections
    halation=(0.0, 0.0),    # red-orange glow around highlights, like film
    glint=(0.0, 0.0),       # star glints on highlights: base, plus this much times the hi-hat envelope
    ca=(0.0, 0.0),          # chromatic aberration: base, plus this much times the beat pulse
    punch=0.0,              # zoom punch-in times the beat pulse (per shot: punch= in the EDL scales it)
    vignette=(0.0, 0.0),    # (normal, calm sections and the intro)
    letterbox=[],           # [(start_s, end_s), ...] 2.39 bars on wide output; LETTERBOX is the analyzer's pick
    drop_flash=0.0,         # white flash on each drop in song.json, 0..1
    shock=0.0,              # shockwave ripple on song.json "shocks", times their amplitude
)
STARTS = {
    # dark, nocturnal, club and EDM: glossy glow that rides the kick
    "club": dict(grain=(0.09, 0.13), bloom=(0.42, 0.55), bloom_kick=0.3, bloom_loud=0.12, bloom_calm=1.25,
                 halation=(0.2, 0.35), ca=(0.0016, 0.006), punch=0.035, vignette=(0.4, 0.55)),
    # warm, retro, moody, cinematic: film grain and halation, a softer pulse
    "film": dict(grain=(0.10, 0.14), bloom=(0.3, 0.38), bloom_kick=0.15, bloom_loud=0.08, bloom_calm=1.15,
                 halation=(0.25, 0.35), ca=(0.001, 0.003), punch=0.02, vignette=(0.45, 0.6)),
    # bright, clean pop: glow and punch without texture
    "clean": dict(grain=(0.0, 0.04), bloom=(0.25, 0.3), bloom_kick=0.2, bloom_loud=0.1,
                  ca=(0.0, 0.002), punch=0.03, vignette=(0.2, 0.3)),
    # lo-fi, punk, harsh: heavy grain, hard punch, fringing on the kick
    "raw": dict(grain=(0.16, 0.2), bloom=(0.1, 0.12), ca=(0.003, 0.01), punch=0.05, vignette=(0.5, 0.6)),
    "none": dict(),
}
FINISH = {**OFF, **STARTS["film"]}   # pick the start from the brief, then tune any value here
