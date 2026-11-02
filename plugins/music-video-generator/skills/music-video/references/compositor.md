# Compositor, look and graphics

## Contents
- Pipeline
- Output sizes
- Sources beyond footage
- Per-shot options (EDL)
- Transitions
- Time: ramps, loops, ghosts
- Song data
- The look (look.py)
- Film grain
- Graphics and text (fx.py drawing)
- Motion
- Tracked points (track.py)
- Shaders and uniforms (fx.py)
- Direction stills (--variant)
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
   16:9 (`media.crop_for`), speed change (motion-blended `framerate` below 0.85x; a ramp is cut at its
   slowest speed and read through the shot's time map in `motion.py`), optional reverse,
   light sharpening on AI clips. AI clips with `<CODE>_matte.mp4`, and archive shots with `matte=True`,
   get a matching matte segment. Segment names hash source, in-point, length, speed, direction and crop,
   so edits only re-cut what changed. Delete a clip's segments in `mv/work/seg/` after replacing the
   clip file itself.
2. **Pass 1.** Per frame: transforms (zoom, pan, rotation, shake, mirror, kaleidoscope), gradient-map
   grade, the transition between shots, OVER-track double exposure (screen/add/lighten/difference),
   then `fxComp` (with the person matte), echo, trail and ghost feedback from the previous frame,
   glitch. The person matte travels in the alpha channel.
3. **Pass 2.** Letterbox bars (if `look.py` asks for them), then the `behind` layer where the person
   matte is empty, then the `front` layer over everything. Both layers come from `fx.py`.
4. **Bloom.** Bright pass, then two blur levels; anamorphic streaks (a long horizontal blur of the
   brightest lights) when the finish or `fx.py` asks for them.
5. **Final.** Punch-in, shockwave, chromatic aberration, bloom and halation, streaks, star glints,
   flash, invert, `fxFinal`, vignette, scanlines, film grain, fade-in. The amounts come from `FINISH`
   in `look.py`.

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
- `ramp=(2.0, 0.25)` into a drop, `loop=0.5` on a snare roll, `ghost=0.7-0.85` on dancers (below).
- `x="whip"`, `"zoom"`, `"matte"` and the other transitions (below).
- OVER track at `op=0.3-0.45`: one film over another.
- Any other keyword is passed through to `fx.py` as `a["shot"]["name"]`, so a concept can add its own
  per-shot controls.

## Transitions

`x=` on a shot is the transition into it from the shot before; `xd=` its length in beats (each kind has
a default). Built in:

| x | what it does | timing | options |
|---|---|---|---|
| `dissolve` | cross-dissolve | from the cut, 2 beats | |
| `dip` | through a colour and back | centred, 1 beat | `xcol=(1, 1, 1)` for white (black default) |
| `whip` | whip pan: both shots smear with motion blur, switching at full speed | centred, 0.5 | `xdir="left"`, `"right"`, `"up"`, `"down"` (the way the picture travels) |
| `zoom` | zoom through with radial blur, out of the next shot | centred, 0.5 | `xc=(x, y)` centre, 0..1 from the top left |
| `luma` | the new shot appears in the old one's shadows first | from the cut, 2 | |
| `burn` | the new shot burns in through the highlights, with a glowing edge | from the cut, 1 | `xcol=` edge colour |
| `matte` | the old shot's person stays while their world turns into the new shot, then fades | from the cut, 2 | old shot needs a matte |
| `matte_in` | the new shot's person appears first in the old world, then their world follows | from the cut, 2 | new shot needs a matte |
| `defocus` | the old shot goes out of focus, the new one comes back in | centred, 1 | |

"Centred" kinds switch shots exactly on the cut, so the switch lands on the beat; the others start on
it and run into the new shot while the old one keeps playing. `x="glitch"` and `x="flash"` remain cut
accents. Matte kinds without a matte fall back to a dissolve (`edl.py` warns).

A video's own transitions: list their names in `fx.py` `TRANSITIONS` (or `{name: "center"}` to switch
on the beat) and write `GLSL_MIX` (`fxMix`, see "Shaders"). `fx_examples.py` has one (a tear).

## Time: ramps, loops, ghosts

- `ramp=` changes the speed inside a shot. Plain numbers spread over the shot (`ramp=(2.0, 0.25)`:
  double speed easing down to quarter speed), or `(beat, speed)` pairs from the shot's start for exact
  placement (`ramp=((0, 1.5), (1, 0.2), (3, 0.2), (4, 2.0))`). Speed 0 freezes. The segment is cut at
  the slowest moving speed, with motion-blended frames below 0.85x, and the fast parts skip frames, which
  reads as a speed ramp should. Very slow minimums make long segments (0.1x cuts ten times the footage).
- `loop=` repeats the shot's first N beats for the whole shot: a stutter on a snare roll or a riser,
  a gesture repeated on the hats. Short loops (a half or quarter beat) work best on movement.
- `ghost=` leaves trails of the person only: their silhouettes from the last frames linger and fade
  (0.6 short, 0.9 long). Needs a matte (AI clip with `_matte.mp4`, or `matte=True`). Dancers, spins,
  hair, anything fast.
- `motion.py` holds the time map (`src_elapsed`, `seg_time`), so contact sheets, tracking and the
  render all agree on which source frame is on screen.

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
  | `streak`, `streak_tint`, `streak_thr` | anamorphic streaks: horizontal flares from the brightest lights (0.3-1.0; tint anamorphic blue by default, warm for fire and tungsten; threshold 0.7-0.9) |

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
`fit(spec, size, text, track, maxw)`, `tracked(...)` for letter-spaced text, `glyphs(text, font, track)`
for letters that move one by one, `streak(d, xy, v, width, fill)` for moving particles,
`track(name, ctx)` and `to_screen(ctx, x, y)` for points in the footage, `layer(canvas, fill, mask,
alpha)` to composite a color or image through a mask, `gradient(top, bottom)`, `kick_level(t)`,
`letterboxed(t)`, `lyric_at(t)`, and the audio arrays. Module helpers: `hash01(*key)` for stable random
values per frame, `keyframes(t, pts, ease)`, the easing curves, `since`, `hit`, `stagger`, and the font
folders `F` and `FS`. `ctx` also carries the shot dict (`ctx["shot"]`) and its `start`.

Draw from `t` and `f` alone. Positions of particles, letters and marks are functions of time, never
state carried from the previous frame: `--stills` renders only a short warm-up before each still, so
anything accumulated frame by frame differs between stills and the full render.

Techniques that work in any video (mechanics, not looks): draw text into an L mask and composite it
with `ov.layer` for gradients and textures inside letters; a blurred dark copy behind text holds it on
bright shots; gate overlays with `ov.kick_level(t)` so calm sections stay clean; keep letterbox-bar text
inside the bar spans from `look.py`.

## Motion

How things move is most of what separates graphics that feel designed from graphics that feel placed.
Mechanics from animation practice, in beats rather than milliseconds:

- **Ease everything that travels.** Entrances decelerate (`ease_out`, `ease_out_expo`; `ease_out_back`
  overshoots and settles, for type that slams in), exits accelerate (`ease_in`) and run about two thirds
  as long, moves between two rests use `ease_in_out`. Constant speed only for rotation and slow drift.
  `keyframes(t, [(t0, v0, ease_out), (t1, v1)])` takes an ease per move; values may be tuples.
- **Speed comes from acceleration**, not from a shorter duration: a short burst and a long settle feels
  faster than the same move at constant speed.
- **Follow-through.** Parts that hang off a moving thing arrive a frame or two later (a shadow, a glow,
  the second line of type); letters staggered over half a beat to a beat read as one gesture (`stagger`).
  Longer cascades read as slow.
- **Anticipation.** Before a big move, a small one the other way: type dips before it rises, the frame
  pulls back before the punch-in. The bar before a drop is the song's anticipation; hold back there.
- **Few things at once.** At any frame, at most about three graphic elements actively moving, and one
  place the eye goes. New elements arrive as old ones leave.
- **Depth.** Layers of particles or graphics at different depths need a speed ratio of 2 or more to read
  as depth (far 0.35, mid 0.7, near 1.4 of the camera's move); more than four layers don't add anything.
  Nearer layers are bigger, faster, softer and brighter; very near, huge particles ruin a shot.
- **Particles as film sees them.** Anything moving fast is a streak, not a dot: `ov.streak` draws the
  length a 180-degree shutter records (speed times half a frame). Relative speeds keep materials apart:
  rain about 7 times faster than snow, ash a little slower than snow, dust almost floating, embers rising.
  Rain and dust show against dark backgrounds and backlight; against a bright sky they disappear.
- **Flashes snap.** A lightning-style flash is 2-4 strokes at least 2 frames apart, each a peak and a
  2-frame decay, with no easing in; one to three per shot, or it reads as a strobe.
- **Envelopes.** `hit(t, times, decay)` gives a 0..1 hit that decays from each time in a list (drops,
  `ov.snares`, lyric word starts); `since(t, times)` gives the seconds since the last one.

## Tracked points (track.py)

`track.py` follows a point through one shot of the edit so an overlay can be pinned to the footage: a
flare on a lamp, sparks off a hand, a word on a wall, light rays from a window.

```bash
.venv/bin/python mv/scripts/track.py --pick --at 63.2                 # gridded frame to read X,Y from
.venv/bin/python mv/scripts/track.py lamp --at 63.2 --bright          # the brightest light in the frame
.venv/bin/python mv/scripts/track.py lamp --at 63.2 --bright --point 0.62,0.3   # the brightest near a point
.venv/bin/python mv/scripts/track.py hand --at 63.2 --point 0.41,0.55 # texture around a point
```

It writes `mv/data/tracks/<name>.json` and a check sheet `mv/work/tracks/<name>.jpg`; look at the sheet
(green tracked, red lost). In `fx.py`, `ov.track("lamp", ctx)` gives the point in output pixels through
the shot's zoom, pan, rotation and shake (and in 9:16), or None in other shots and where the track was
lost; in `uniforms(t, a)`, `a["track"]("lamp")` gives it in shader uv. Fade an overlay out when it
returns None rather than leaving it hanging. The track belongs to the shot's cut segment: after changing
its in-point, speed, ramp or loop, track it again.

## Shaders and uniforms (fx.py)

- `UNIFORMS = {"name": default}` declares extra uniforms (float or 2/3/4-tuples) in both shader passes.
- `GLSL_COMP` defines `vec3 fxComp(vec3 col, vec2 uv, float matte)`, applied to the composited picture
  before echo/trail feedback and overlays; `matte` is the person matte. Matte tricks (a glow or outline
  around the person, light behind them), short accents on hits and, for visualizers, generated
  backgrounds go here. In a music video the footage stays graded footage: picture-wide stylization runs
  for a beat or two at most (SKILL.md Phase 5). It can call `sampleA(q)` (the graded shot at any
  screen position q, for displacement, refraction and echoes of the picture), `sampleB(q)` (the
  incoming shot during a transition), `matteA(q)`, `matteB(q)`, `luma(c)`, and read `tPrev`.
- `GLSL_MIX` defines `vec3 fxMix(vec3 a, vec3 b, float mA, float mB, float u, vec2 uv, float kind)`, the
  picture during one of `TRANSITIONS`: `a` and `b` are the outgoing and incoming shots at `uv`, `mA` and
  `mB` their mattes, `u` the progress 0..1, `kind` the index in `TRANSITIONS`. Use `sampleA`/`sampleB`
  for anything that moves pixels (slices, shatter, ripples, a reveal through a shape from the frame).
- `GLSL_FINAL` defines `vec3 fxFinal(vec3 col, vec2 uv, vec2 p)`, applied after bloom, flash and invert,
  before vignette and grain. It can sample `tComp` (the frame with overlays), `tB1` (tight bloom),
  `tB2` (wide bloom) and `tS` (streaks): light rays marched toward a point through `tB1`, glows and
  flares built from the picture's own light. GLSL helpers available: `hash`, `gnoise`, `mrep`, `ASP`,
  `time`.
- `uniforms(t, a)` returns values per frame. `a` holds `kick`, `snare`, `hat`, `rms` envelopes, `spec`
  (48 bands), `pulse` (the engine's beat-locked kick envelope), `beat` and `phase`, `section` and
  `kick_level`, `calm`, `src`, `local`, `shot` (the EDL shot dict), `BEAT`, `x` and `xu` (the
  transition running and its progress, or None) and `track(name)`. Returning an engine uniform
  (`bloom`, `glint`, `grain`, `vignette`, `ca`, `punch`, `flash`, `invert`, `scan`, `letterbox`,
  `fade`, `shockT`/`shockAmp`, `streak`) overrides it for that frame.

`assets/examples/fx_examples.py` shows the mechanics with seven small effects: a light leak on
downbeats, a one-beat aberration accent on drops, a rim glow on the person on kicks, embers as streaks
lit by hi-hats, a custom transition (a tear), light rays from a tracked lamp, and title letters that land
one by one on the drop. Render stills at 3-6 telling times and look at the sheet before a full render.

## Direction stills (--variant)

`render.py ... --variant A` renders with `mv/scripts/look_A.py` and `fx_A.py` in place of `look.py`
and `fx.py` (either may be missing; the other is used as is). Phase 5 uses it to show one still per
concept before the user picks. A variant's look must define the grade names the EDL uses.

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
