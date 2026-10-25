# Compositor, look and graphics

## Contents
- Pipeline
- Output sizes
- Sources beyond footage
- Per-shot options (EDL)
- Song data
- The look (look.py)
- Film grain
- Graphics and text (fx.py drawing)
- Shaders and uniforms (fx.py)
- Audio data
- Lyrics
- Fonts on macOS
- Pitfalls

The engine (`render.py`, `overlay.py`) draws no graphics of its own: with an empty `fx.py` it renders the
graded footage with the finish chosen in `look.py` (the template starts from the "film" finish). Every
graphic, title and overlay is designed per video in `look.py` and `fx.py`.

## Pipeline

`render.py` reads `edl.json`, `song.json` (through `timing.py`), `audio_feats.npz`, `look.py` and `fx.py`.

1. **Segments.** ffmpeg cuts each shot from its source into `mv/work/seg/` at 1280x720/24 fps: crop to
   16:9 (`media.crop_for`), speed change (motion-blended `framerate` below 0.85x), optional reverse,
   light sharpening on AI clips. AI clips with `<CODE>_matte.mp4`, and archive shots with `matte=True`,
   get a matching matte segment. Segment names hash source, in-point, length, speed, direction and crop,
   so edits only re-cut what changed. Delete a clip's segments in `mv/work/seg/` after replacing the
   clip file itself.
2. **Pass 1.** Per frame: transforms (zoom, pan, rotation, shake, mirror, kaleidoscope), gradient-map
   grade, dissolve between shots, OVER-track double exposure (screen/add/lighten/difference), then
   `fxComp` (with the person matte), echo and trail feedback from the previous frame, glitch. The
   person matte travels in the alpha channel.
3. **Pass 2.** Letterbox bars (if `look.py` asks for them), then the `behind` layer where the person
   matte is empty, then the `front` layer over everything. Both layers come from `fx.py`.
4. **Bloom.** Bright pass, then two blur levels.
5. **Final.** Punch-in, shockwave, chromatic aberration, bloom and halation, star glints, flash, invert,
   `fxFinal`, vignette, scanlines, film grain, fade-in. The amounts come from `FINISH` in `look.py`.

Output is H.264 CRF 19 `-preset slow` with the song as AAC 320k. `--stills` renders JPEG frames
instead, with a 0.6 s warm-up before each so echo and trails match the full render.

## Output sizes

`--size WxH` sets the output: 1920x1080 by default, 1080x1920 for Reels/TikTok/Shorts, 1080x1080 or
1080x1350 for feeds. Segments stay 16:9 and the frame shows their middle. Shots with a person matte are
reframed on the person automatically; give other shots `pan=((x, 0), (x, 0))` to reframe (x is a texture
offset; about ±0.34 reaches the edges in 9:16). Letterbox is skipped for non-wide output. Design `fx.py`
graphics in 1080p units times `ov.s` and use `ov.fit` for text, and they hold at every size; check
`ov.wide` where a layout needs to change for narrow frames. Render the vertical version from the same
EDL; adjust only shots that frame badly.

## Sources beyond footage

- Stills (`.jpg`, `.png` in `codes.json`): looped for the shot length; give them `zoom=(1.0, 1.2)` and a
  `pan` for movement.
- Built-in generated backgrounds that pulse with the kick: `GEN_GRID` (a synthwave sun and grid, a
  cliché: avoid unless the concept is about it), `GEN_PLASMA`, `GEN_TUNNEL`. They take grades,
  dissolves, kaleidoscope and the OVER track like any shot.
- New generated backgrounds: give a `BLACK` shot a custom option (`S("BLACK", 0, 8, gen="ink")`), set a
  uniform from `a["shot"].get("gen")` in `fx.uniforms`, and draw the pattern in `fxComp` when it is set.

## Per-shot options (EDL)

All are documented in `edl.py`. Typical uses:
- `speed=0.55-0.7` with `echo=0.3-0.5`: slow motion with ghosting.
- `x="dissolve", xd=1-2`; `x="glitch"` burst on a cut; `x="flash", flash=0.6` white flash on a cut.
- `shake=0.4-0.8` on impacts; `zoom=(1.0, 1.15)` push-ins; `rot`, `spin`.
- `kal=4-6` or `mirror=1` on lights and patterns. Not on faces: mirrored faces look bad.
- `trail=0.5-0.6` on dancers and lights; `glitch=0.25-0.45` continuous; `scan`, `invert`.
- `expo=0.7-0.8` and a dim grade tame overexposed or blooming shots.
- `rev=True` plays a shot backwards (smoke, explosions, water).
- OVER track at `op=0.3-0.45`: one film over another.
- Any other keyword is passed through to `fx.py` as `a["shot"]["name"]`, so a concept can add its own
  per-shot controls.

## Song data

Beat positions come from `timing.py`: a fixed grid (`bpm`, `t0`) or, for songs that drift, the `beats`
map. Use `beat(k)` for the time of beat k and `beat_at(t)` for the beat index at a time; never compute
`t0 + k * BEAT` by hand, because that breaks on drifting songs. `BEAT` is only the average beat length,
fine for easing and dissolve lengths. Also in `timing.py`: `SECTIONS` (start, end, name, kick, calm),
`section(t)`, `is_calm(t)`, `beat_phase(t)`, `DROPS`, `SHOCKS`, `COUNTDOWNS` (8 beats before a drop),
`LETTERBOX` (the analyzer's suggestion), `END` (end card), `TITLE`, `ARTIST`. After `END` the picture is
whatever the EDL has there: `edl.py` appends a BLACK tail when the edit stops at `end`, and `fx.py` can
draw the end card in either pass. Extend the edit past `end` to run footage under the end card.

These are facts about the song. Nothing happens at a drop or countdown unless `look.py` (`drop_flash`,
`shock`) or `fx.py` makes it happen.

## The look (look.py)

- `PALETTES`: gradient maps of 5 color stops, shadows to highlights. The template has two placeholders
  (neutral film, black and white). Write this video's own, one or more; the shader is generated from the
  list.
- `GRADES`: `name: (gm, palette, saturation, contrast, lift, exposure)`; `gm` blends the mapped color
  with the original. Grading archive footage through the same palette as the AI clips is what makes 1944
  Kodachrome and 2026 renders feel like one film. `ARCHIVE_GRADE` and `AI_GRADE` in `edl.py` pick the
  defaults (`"base"`, `"ai"`); per code defaults go in `DEFAULT_GRADES`. `edl.py` stops on a grade name
  that `look.py` doesn't define.
- `SHADOW_TINT`: a color added to the shadows.
- `FINISH`: pairs are (AI clips, archive/library shots). It is built from `OFF` (everything at zero)
  plus one of the `STARTS`, chosen from the brief's mood, then tuned:

  | start | for | what it sets |
  |---|---|---|
  | `club` | dark, nocturnal, club, EDM | glossy bloom riding the kick, halation, 16 mm grain, aberration and punch on the kick |
  | `film` | warm, retro, moody, cinematic | grain, halation, softer bloom and pulse, deeper vignette |
  | `clean` | bright pop | glow and punch, little or no grain |
  | `raw` | lo-fi, punk, harsh | heavy grain, hard punch, fringing on the kick |
  | `none` | a concept that builds its whole finish in `fx.py` | nothing |

  A dark song with a `none` finish and a pale grade reads flat.

  | key | what it does |
  |---|---|
  | `grain` | film grain strength; 0.09-0.16 reads as 35-16 mm |
  | `bloom`, `bloom_kick`, `bloom_loud`, `bloom_calm` | glow from bright areas: base, added by the beat pulse, added by loudness, multiplier in calm sections |
  | `halation` | red-orange glow around highlights |
  | `glint` | star glints on highlights: base, plus amount times the hi-hat |
  | `ca` | chromatic aberration: base, plus amount times the beat pulse |
  | `punch` | punch-in zoom times the beat pulse (per shot `punch=` scales it) |
  | `vignette` | (normal, calm sections and intro) |
  | `letterbox` | list of (start, end) spans with 2.39 bars on wide output; `LETTERBOX` is the analyzer's pick |
  | `drop_flash`, `shock` | white flash and shockwave on the song's drops and shocks |

  Anything the table can't express goes in `fx.uniforms()`, which can return any engine uniform and
  overrides it for that frame (for example, glints off in the intro).
- Shader textures arrive upside down; the layer sampler flips y. Keep that if you touch the shader.

## Film grain

Soft clumps from two octaves of gradient noise at 1.7-2.7 px, a separate grain per color layer (blue
coarsest), strongest in the midtones, fading in deep blacks and clipped highlights, a new pattern every
frame. At 0.13 it measures about 0.018 high-pass standard deviation in dark areas. The earlier version,
square 2-pixel blocks of uniform noise added equally to all channels, was rejected as "digital noise".
When tuning, measure grain on a flat dark area rather than guessing. Whether a video has grain is a
concept decision.

## Graphics and text (fx.py drawing)

`Overlay.frame(t, ctx)` calls `fx.draw_behind(ov, img, t, f, ctx)` and `fx.draw_front(ov, d, t, f, ctx)`.
`img` is an RGBA canvas composited only where the person matte is empty, so anything drawn there sits
behind the performer. `d` is a PIL ImageDraw on the front layer, over everything. `ctx` has the shot's
`src`, `label`, `local` time and `dur`. Nothing is drawn unless `fx.py` draws it: titles, artist name,
credits, words, captions and graphics are all part of the concept.

`ov` helpers (listed in `overlay.py`): `w`, `h`, `s` (short side / 1080), `wide`, `font(spec, size)`,
`fit(spec, size, text, track, maxw)`, `tracked(...)` for letter-spaced text, `layer(canvas, fill, mask,
alpha)` to composite a color or image through a mask, `gradient(top, bottom)`, `kick_level(t)`,
`letterboxed(t)`, `lyric_at(t)`, and the audio arrays. Module helpers: `hash01(*key)` for stable random
values per frame, `keyframes(t, pts)`, and the font folders `F` and `FS`.

Techniques that work in any video (mechanics, not looks): draw text into an L mask and composite it
with `ov.layer` for gradients and textures inside letters; a blurred dark copy behind text holds it on
bright shots; gate overlays with `ov.kick_level(t)` so calm sections stay clean; keep letterbox-bar text
inside the bar spans from `look.py`.

## Shaders and uniforms (fx.py)

- `UNIFORMS = {"name": default}` declares extra uniforms (float or 2/3/4-tuples) in both shader passes.
- `GLSL_COMP` defines `vec3 fxComp(vec3 col, vec2 uv, float matte)`, applied to the composited picture
  before echo/trail feedback and overlays; `matte` is the person matte. Matte tricks (a glow or outline
  around the person, light behind them), short accents on hits and, for visualizers, generated
  backgrounds go here. In a music video the footage stays graded footage: picture-wide stylization runs
  for a beat or two at most (SKILL.md Phase 5).
- `GLSL_FINAL` defines `vec3 fxFinal(vec3 col, vec2 uv, vec2 p)`, applied after bloom, flash and invert,
  before vignette and grain. GLSL helpers available: `hash`, `gnoise`, `mrep`, `ASP`, `time`.
- `uniforms(t, a)` returns values per frame. `a` holds `kick`, `snare`, `hat`, `rms` envelopes, `spec`
  (48 bands), `pulse` (the engine's beat-locked kick envelope), `beat` and `phase`, `section` and
  `kick_level`, `calm`, `src`, `local`, `shot` (the EDL shot dict) and `BEAT`. Returning an engine
  uniform (`bloom`, `glint`, `grain`, `vignette`, `ca`, `punch`, `flash`, `invert`, `scan`, `letterbox`,
  `fade`, `shockT`/`shockAmp`) overrides it for that frame.

`assets/examples/fx_examples.py` shows the mechanics with four small effects (light leak on downbeats,
a one-beat aberration accent on drops, a rim glow on the person on kicks, embers lit by hi-hats).
Render stills at 3-6 telling times and look at the sheet before a full render.

## Audio data

`audio_feats.npz` per frame: `spec` (48 log bands, fast attack and slow release like a hardware
analyzer), `rms`, `kick`, `snare`, `hat` envelopes, `wave` (256-sample waveform). The overlay derives
`peaks` (falling peak hold per band) and the onset times `kicks` and `snares`. Useful mappings are in
`references/effects-ideas.md`; keep calm sections quiet so the loud ones land.

## Lyrics

`ov.lines` holds `mv/data/lyrics.json` without the lines marked suspect: each line has `start`, `end`,
`text` and `words` (each with `w`, `start`, `end` from Whisper). `ov.lyric_at(t)` returns the line and
the index of the word being sung. When the user supplies the text, put it into `lyrics.json` with the
timings from Whisper's lines. Confirm the words with the user before rendering anything that shows them.
How the words look and move is designed per video.

## Fonts

Font specs are `(path, ttc_index)`. Any `.ttf`, `.otf` or `.ttc` path works, including fonts shipped
with the project. When a path doesn't exist (an `fx.py` written on macOS rendering on Linux),
`overlay.font_path` looks for the same file name in the system font folders, then falls back to DejaVu
Sans, Arial or Helvetica. On macOS:

`/System/Library/Fonts/` (`F`): Avenir Next (TTC index 0 Bold, 2 Demi Bold, 5 Medium, 7 Regular,
8 Heavy, 10 Ultra Light), Avenir Next Condensed, Helvetica Neue, SF Mono (`SFNSMono.ttf`), Menlo,
Optima, Apple Symbols, Marker Felt (`MarkerFelt.ttc`).

`/System/Library/Fonts/Supplemental/` (`FS`): Futura (2 Bold, 3 Condensed Medium, 4 Condensed
ExtraBold), Didot, Bodoni 72, Snell Roundhand, DIN Condensed Bold, DIN Alternate Bold, Impact, Rockwell,
Copperplate, Gill Sans, Chalkduster, Courier New, American Typewriter (`AmericanTypewriter.ttc`),
Baskerville, Big Caslon (`BigCaslon.ttf`), Herculanum, Papyrus, Trattatello, Zapfino, Skia, Silom.

List TTC indexes with `ImageFont.truetype(path, 20, index=i).getname()`. Thin tracked Avenir and heavy
Futura are the usual reflex; start elsewhere.

## Pitfalls

- Uniforms that the GLSL compiler optimizes away raise KeyError when set; delete the Python line too.
- Still mode skips frames outside the warm-up windows, so feedback effects only match the full render
  near each still.
- Text drawn into the front layer covers the letterbox; draw letterbox-bar text there on purpose and
  keep other text inside the picture area.
- Very bright archive frames plus bloom wash to white; lower `expo` on the shot instead of global bloom.
- `fx.py` imports `overlay` helpers; `overlay.py` imports `fx` lazily for that reason. Keep it that way.
