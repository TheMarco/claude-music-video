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
- Keeping faces clear
- Contrast
- Explaining graphics (devices.py)
- Shaders and uniforms (fx.py)
- Depth (make_depth.py)
- Screens in the footage (track_screen.py)
- Audio data
- Lyrics
- Fonts
- Pitfalls

The engine (`render.py`, `overlay.py`) draws no graphics of its own: with an empty `fx.py` it renders the
graded footage with the finish chosen in `look.py` (the template starts from the "film" finish). Every
graphic, title and overlay is designed per video in `look.py` and `fx.py`.

## Pipeline

`render.py` reads `edl.json`, `song.json` (through `timing.py`), `audio_feats.npz`, `look.py` and `fx.py`.

1. **Segments.** ffmpeg cuts each shot from its source into `mv/work/seg/` at 1280x720/24 fps (or
   `look.SEG_SIZE`, "Output sizes"): crop to the segment aspect (`media.crop_for`), speed change
   (motion-blended `framerate` below 0.85x), optional reverse, light sharpening on AI clips. AI clips with
   `<CODE>_matte.mp4` or `<CODE>_depth.mp4`, and archive shots with `matte=True` or `depth=True`, get a
   matching matte or depth segment. Segment names hash source, in-point, length, speed, direction and crop,
   so edits only re-cut what changed. Delete a clip's segments in `mv/work/seg/` after replacing the
   clip file itself.
2. **Pass 1.** Per frame: transforms (zoom, pan, rotation, shake, mirror, kaleidoscope), gradient-map
   grade, dissolve between shots, OVER-track double exposure (screen/add/lighten/difference), the shot's
   depth treatment ("Depth"), then `fxComp` (with the person matte and `DEPTH`), echo and trail feedback
   from the previous frame, glitch. The person matte travels in the alpha channel, together with the
   shot's `behind_depth` key.
3. **Pass 2.** Letterbox bars (if `look.py` asks for them), then the `behind` layer where the person
   matte is empty, then the `front` layer over everything. Both layers come from `fx.py`.
4. **Bloom.** Bright pass, then two blur levels.
5. **Final.** Punch-in, shockwave, chromatic aberration, bloom and halation, star glints, flash, invert,
   `fxFinal`, vignette, scanlines, film grain, fade-in. The amounts come from `FINISH` in `look.py`.

Output is H.264 CRF 19 `-preset slow` with the song as AAC 320k. `--stills` renders JPEG frames
instead, with a 0.6 s warm-up before each so echo and trails match the full render.

## Output sizes

`--size WxH` sets the output: 1920x1080 by default, 1080x1920 for Reels/TikTok/Shorts, 1080x1080 or
1080x1350 for feeds. Segments stay 16:9 and the frame shows their middle, unless the footage itself was
made vertical: then set `SEG_SIZE = (1080, 1920)` in `look.py`, so segments keep the clips' own 9:16 frame
instead of a 16:9 crop of it (sources of another shape are cropped to 9:16). Shots with a person matte are
reframed on the person automatically; give other shots `pan=((x, 0), (x, 0))` to reframe (x is a texture
offset; about ±0.34 reaches the edges in 9:16). The person centring follows the matte, so a two-shot
gets the middle of both people or one of them (a drive shot lost the singer), and a shot carried by a
car or a DJ's decks gets the person instead: give those `narrow_x=x`, the same offset, which only narrow
renders use, or a code's default in `NARROW_X` at the top of `edl.py`. Letterbox is skipped for non-wide output. Design `fx.py`
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
- `depth_fx="relight"`, `"contours"`, `"scan"` or `"haze"` with `depth_rate`, `depth_amt`, `depth_col`, and
  `behind_depth=0.6` on shots with a depth map ("Depth").
- Any other keyword is passed through to `fx.py` as `a["shot"]["name"]`, so a concept can add its own
  per-shot controls.

## Song data

Beat positions come from `timing.py`: a fixed grid (`bpm`, `t0`) or, for songs that drift, the `beats`
map. Use `beat(k)` for the time of beat k and `beat_at(t)` for the beat index at a time; never compute
`t0 + k * BEAT` by hand, because that breaks on drifting songs. `BEAT` is only the average beat length,
fine for easing and dissolve lengths. Also in `timing.py`: `SECTIONS` (start, end, name, kick, calm),
`section(t)`, `is_calm(t)`, `beat_phase(t)`, `DROPS`, `SHOCKS`, `COUNTDOWNS` (8 beats before a drop),
`LETTERBOX` (the analyzer's suggestion), `END` (end card), `TITLE`, `ARTIST`, and `bar_line(t)` (the
bar line nearest t). After `END` the picture is whatever the EDL has there: `edl.py` appends a BLACK
tail when the edit stops at `end`, and `fx.py` can draw the end card in either pass. Extend the edit
past `end` to run footage under the end card.

**The picture never trails the sound.** Viewers notice sound that arrives before its picture sooner
than sound that arrives after it, so cuts, the beat pulse, drop flashes, shocks and section changes
are shown on the video frame at or before their song time: `edl.py` writes cut times on frames
(`on_frame(s)`), and the engine reads beats with `hit_phase(t)` and sections at `t + HIT_LEAD`. In
`fx.py`, anything meant to land with a cut follows the same rule. `a["beat"]`, `a["phase"]`,
`a["section"]`, `a["kick_level"]` and `ov.kick_level(t)` already do; for your own timing, compare `t`
with `on_frame(beat(k))` and look sections up with `section(t + HIT_LEAD)`. A plain `t >= beat(k)` or
`section(t)` switches up to a frame after the cut. Lyrics, audio-reactive values and lipsync shots stay
on song time. An `fx.py` written before this rule (engine 1.1.0 and earlier) can adopt it
with four lines after its `from timing import ...` line, which has to import `beat` and `section`:

```python
from timing import HIT_LEAD, on_frame
_song_beat, _song_section = beat, section
def beat(k): return on_frame(_song_beat(k))
def section(t): return _song_section(t + HIT_LEAD)
```

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

## Keeping faces clear

Nothing drawn in front sits on a face, at any frame it is on screen (SKILL.md, working rules). The engine
tracks the heads and places the blocks; `fx.py` uses that for every block it draws.

**Tracking.** `heads.py` renders the edit with no overlays (`render.py --clean`), finds faces and heads on
every frame of that render and writes `mv/data/heads.json`: per frame, boxes from the hair to the chin, in
0..1 of the frame. Because it reads the rendered picture, the boxes follow every crop, zoom, pan, speed
change and reverse as they play. On macOS it uses Apple's Vision framework, faces plus body pose, so a
head turned away or seen from behind still gets a box; elsewhere OpenCV's Haar cascades, which find
frontal and profile faces only. A box is held for four frames either side inside its shot and never
crosses a cut, and the cut is the frame the renderer cuts on (`on_frame` of the shot's start), not the
EDL time; otherwise the first frame of every shot inherits the last shot's heads.

The detector misses heads and invents others, and the review sheets (`mv/review/heads_NN.jpg`, every
shot every 0.25 s with a 0.1 grid) are where both show. Misses: heads seen from behind or from above, a
figure small in a wide, a head half out of frame, motion blur, a face lit only by a rim light, a helmet,
a mask or a visor (missed on every frame, so nothing on the sheets changes: `mv/review/heads_count.txt`
lists the heads found per shot, and a two-shot with one head shows there). Inventions:
a chain, a statue, a reflection. Fix them in `mv/data/heads_manual.json` (`add`, `clear`, `drop`, in
heads.py's docstring) and run `heads.py --rebuild`. Crowd faces count when the detector finds them
(boxes from 3% of the frame height). An older face pass that ran Haar on the source clips with hand-set
bands missed a back view and a small dancer and put cards on both heads.

**Placing.** `ov.place(key, t0, t1, bw, bh, xs, prefer, t=t)` returns `(x, y, k)`: the left edge, the
centre line and a scale for a block of `bw` by `bh` px shown from `t0` to `t1`. It first looks for one
position clear of every head over the whole span inside the feed's safe band (10-80% of the height),
trying each left edge in `xs` and moving out from `prefer` (a fraction of the height). Failing that it
places the block shot by shot, so it moves on a cut, where the move doesn't show, and per shot it tries
the wider band (5-94%) and then 85%, 72% and 60% of the size. A block with no spot left is listed in
`ov.place_misses`. Heads get a margin of `HEAD_PAD` (3% of the width, 2.2% of the height) on top of
their boxes.

- Pass the full footprint: the text or card with its shadow, the pop-in overshoot, any slide-in, and
  what grows out of the block (pasted copies, a credit block under the title).
- Lay out in order of appearance. Placed blocks are remembered and later ones keep clear of them, so on
  the first `draw_front` call run each draw function once at every block's start time, in time order,
  drawing nothing; a render or a check that starts mid-song then lays out like the full render.
  `examples/fx_examples.py` (example 5) has the pattern.
- Draw at the position for the frame's own time (`t=t`): the position can change at a cut.
- Lines of one sentence share one key and one span, so they keep one size and place.
- A close-up whose face fills the frame may leave no room at any size. End the block before the face
  grows, move it to the next shot or leave the shot clear; text under the chin is the last resort.
- Guard before drawing: skip the block on a frame where `ov.touches_face(rect, t)` is true. With right
  boxes it never fires.
- Fine print, particles and anything else drawn per frame check `ov.heads(t)` too: an item that would
  touch a head is left out of that frame.

**Checking.** `facecheck.py --size <output size>` draws the overlay of every frame and lists the frames
where overlay pixels (above 15% opacity) fall inside a head box, and the blocks that found no clear spot.
It exits 1 when it lists anything, and a render that fails it is not shown to the user. It can only check
heads that have boxes, so the sheets come first.

## Contrast

Every element drawn in front has to read against the picture it lands on, on every shot it spans.
`contrastcheck.py --size <output size>` measures it from heads.py's clean frames. It splits each frame's
overlay into elements (the words of a line joined, lines and cards apart), and scores each element's
luminance against the luminance right around it as a contrast ratio, (L1 + 0.05) / (L2 + 0.05):

- Light type is measured against the brighter fifth of its surroundings with its shadow (the shadow is
  what holds it), dark type against the darker fifth of the bare picture. Type needs 3:1 when large and
  4.5:1 when under 2.5% of the frame height, the WCAG levels for large and small text.
- Type with its own outline (a dark stroke round light letters, or the reverse) is scored by the outline
  against the fill, since that reads on any picture.
- A card (a solid core wider than 9% of the frame) needs 1.5:1 against the typical part of its
  surroundings, by its fill or by its rim. Its own text sits on its own fill.

It exits 1 when an element is short for 0.25 s or more and draws each case into
`mv/review/contrast_NN.jpg`. Run it at the output size: at half size a 2 px outline on 23 px type
doesn't resolve.

What fixed a slopcore video that failed it 151 times:
- A dark outline on all light type: `stroke_width` about 2% of the font size (3% for a thin serif, 2-3 px
  at 1080 for fine print) and `stroke_fill` a near-black ink, under a soft drop shadow and a tight one
  (radius 4-5 px).
- Fine print at full strength, not 60% white, with the same outline.
- A rim on dark cards, a 3 px outline a few steps lighter than the fill, so a dark card on a dark shot
  still has an edge.
- Glass and hollow letterforms with a dark edge outside their light outline.

What a second slopcore video needed on top:
- A dark halo behind front elements drawn only where the overlay is empty. A halo over the whole front
  layer joined neighbouring elements into one, and they failed together.
- One light colour per word stack: stacks mixing white and gold words failed where one cream for every
  word passed.
- Dot-matrix (LED) type with the unlit dots drawn solid and dark, a bright rim round the panel, and at
  least one unlit dot column between letters (three between words), or the letters run together.
- Small type sized per shape: captions and fine print that passed at 1920x1080 failed at 1080x1920
  until the caption went from 36 to 46 px and the fine print to a bold weight with a 2 px outline.

`ov.backdrop(rect, t)` returns the bare picture's luminance under a rect (mean, 10th and 90th
percentile), for choosing a treatment per shot: dark type on a bright sky, a stronger shadow on a busy
shot, a darker part of the frame.

## Explaining graphics (devices.py)

The engine's library of explaining graphics (references/effects-ideas.md, "What makes an effect land"):
drawn, timed in beats and placed by the engine, filled and styled by the video. Start each line's graphic
from a device and spend new code on the video's signature overlays; write a new device (below) only when
no device fits the line.

```python
import devices as DV
STYLE = DV.Style(accent=(255, 92, 64), dark=True, sans=..., bold=..., mono=..., mono_bold=..., display=...)
PLAN = DV.Plan(STYLE)
PLAN.add(DV.Counter("PEOPLE WHO CAN DO THIS", 8_000_000_000, mode="odometer"), DV.word("billion"),
         4 * BEAT, prefer=0.3)
```

`Plan.add(device, t0, dur, prefer=0.3, xs=None)` shows it from t0 (a beat, or `DV.word("text", n)` for the
n-th time a word is sung) for dur seconds; prefer is the centre line wanted as a fraction of the height,
xs the left edges to try as fractions of the width. `Plan.draw(ov, img, t, avoid=rects)` draws what is on
screen at t onto the front layer, clear of faces, of `avoid` (that frame's lyric blocks) and of each other,
and returns the rects it took. Lay it out with the video's own blocks: in the layout pass, call
`PLAN.draw` on a scratch image at every time in `PLAN.starts()`, in order with the other blocks
(`examples/fx_examples.py`, example 6).

| Device | Role | Explains | Main parameters |
|---|---|---|---|
| `Counter` | hero | a number: stakes, scale, money, time | label, value, start, fmt, unit, sub, beats, mode "count" or "odometer" |
| `Gauge` | hero | a feeling or risk measured | label, value, lo, hi, unit, ticks, zone |
| `Chart` | hero | the trend a line implies | label, points, kind "line"/"area"/"bars", xlabels, mark, note, per (beats a point) |
| `Poll` | hero | opinion, odds; a callback that moves | title, options [(label, pct)], later [(time, [pcts])], votes |
| `Progress` | hero | loading, copying, a countdown to something | label, done, start, end, beats |
| `Terminal` | hero | the tool, the code, the agent | title, lines [("cmd"/"out", text[, beat])], prompt, cps |
| `Chat` | hero | dialogue, a prompt and its reply | messages [("in"/"out", text)], title |
| `Spec` | hero | a model card, product tag, garment label | kicker, title, rows [(field, value)], barcode |
| `Flap` | hero | departures, countdowns, a verdict | rows, cols, label |
| `Stamp` | hero | a verdict slammed on the beat | text, angle, color, sub |
| `Strike` | hero | before and after, a price drop, a downgrade | label, old, new, under |
| `Redact` | hero | a secret; a reveal later | label, lines with [hidden] words, lift (time) |
| `Typed` | micro | sources, dates, coordinates, a footnote | rows (up to 3) |
| `Tags` | cv | a classifier's verdict on the people in frame | label(i, box) -> text or None |
| `Callout` | cv | a named thing in frame (locked shots) | xy (0..1), text, rows |

The budget per frame is one hero, two cv marks and two micro rows; when more are on, the newest wins.
Every device animates in beats from its start (`timing.beat_at`) and rises in and fades out; give each at
least about 1.5 s (Plan warns under 1.2 s). Panels are dark glass with a lighter rim (or light paper with
`dark=False`), which `contrastcheck.py` accepts on any shot. `Tags` draws a box round a lone head and, in
a group, a chip with a leader line above each head, so nothing lands inside a head box even where the
detector merged two heads; `Callout` drops its leader where it would cross a face.

A new device subclasses `Device`: set `role`, `W`, `H` (1080p units) and write `tile(ov, st, t, t0, t1)`
returning an RGBA image of that size (`_panel` draws the shared panel and header), or, for marks
anchored to the frame, `draw_frame(ov, st, img, t, t0, t1, avoid)`. Keep it in the video's `fx.py`; a
device that more than one video would use belongs in the engine.

## Shaders and uniforms (fx.py)

- `UNIFORMS = {"name": default}` declares extra uniforms (float or 2/3/4-tuples) in both shader passes.
- `GLSL_COMP` defines `vec3 fxComp(vec3 col, vec2 uv, float matte)`, applied to the composited picture
  before echo/trail feedback and overlays; `matte` is the person matte, and the global `DEPTH` (0 far to
  1 near) holds the depth on shots with a depth map (0 elsewhere). Matte tricks (a glow or outline
  around the person, light behind them), short accents on hits and, for visualizers, generated
  backgrounds go here. In a music video the footage stays graded footage: picture-wide stylization runs
  for a beat or two at most (SKILL.md Phase 3).
- `GLSL_FINAL` defines `vec3 fxFinal(vec3 col, vec2 uv, vec2 p)`, applied after bloom, flash and invert,
  before vignette and grain. GLSL helpers available: `hash`, `gnoise`, `mrep`, `ASP`, `time`.
- `uniforms(t, a)` returns values per frame. `a` holds `kick`, `snare`, `hat`, `rms` envelopes, `spec`
  (48 bands), `pulse` (the engine's beat-locked kick envelope), `beat` and `phase`, `section` and
  `kick_level`, `calm`, `src`, `local`, `shot` (the EDL shot dict) and `BEAT`. Returning an engine
  uniform (`bloom`, `glint`, `grain`, `vignette`, `ca`, `punch`, `flash`, `invert`, `scan`, `letterbox`,
  `fade`, `shockT`/`shockAmp`) overrides it for that frame.

`$ENGINE/examples/fx_examples.py` (the engine folder, SKILL.md "The engine") shows the mechanics with four small effects (light leak on downbeats,
a one-beat aberration accent on drops, a rim glow on the person on kicks, embers lit by hi-hats).
Render stills at 3-6 telling times and look at the sheet before a full render. The end card is part of
`fx.py` too: artist and title as the brief gave them, and a credit for every source whose license asks
for one.

## Depth (make_depth.py)

`.venv/bin/python mv/scripts/make_depth.py mv/clips/W1.mp4 ...` writes `<CODE>_depth.mp4` next to each
clip: Depth Anything V2 Small (Apache-2.0, about 99 MB, fetched once by `models.py` with a pinned
checksum), on CPU through the onnxruntime that rembg installs, about 7 s per second of footage. Depth is
relative, normalized per clip and smoothed over time. Archive shots get it per segment with `depth=True`.
Make maps only for the shots that use them.

Per shot in `edl.py`:
- `depth_fx="relight"`: a band of light travels from near to far once per cycle. Energy on wides and
  crowds; warm or white `depth_col`.
- `depth_fx="contours"`: iso-depth lines, the nearest first, one more level each eighth. Turns a place
  into a map; good on aerials and architecture.
- `depth_fx="scan"`: a sweep crosses the frame once per cycle and leaves a point cloud tinted by depth.
  Surveillance, analysis, "the machine sees it".
- `depth_fx="haze"`: air by depth, lifting a little on the kick. Calm sections, golden hour.
- `depth_rate` beats per cycle (default 1, from the shot's cut), `depth_amt` strength (defaults 0.85,
  0.9, 0.8, 0.45), `depth_col` an RGB colour 0..1.
- `behind_depth=0.6`: the `behind` layer tucks behind anything nearer than 0.6 (a tower, a rope, a
  crowd), not only the person matte. Place the block so an edge tucks; a word that mostly disappears
  doesn't read.

A treatment is the footage's medium, chosen from the story (references/effects-ideas.md): rotate them,
never the same one on neighbouring shots, and leave most shots untreated, so each one lands. `fx.py`
can override `dTreat`, `dPhase`, `dAmt`, `dCol` and `dBehind` from `uniforms()` per frame.

## Screens in the footage (track_screen.py)

To put something on a screen, sign or window in a moving shot (a countdown on a tower, the line on a
billboard), track the screen and bake the picture onto it as a new clip:
```bash
.venv/bin/python mv/scripts/track_screen.py W1 --quad 0.443,0.403,0.558,0.413,0.556,0.652,0.444,0.642
.venv/bin/python mv/scripts/bake_screen.py W1 --panel panel.mp4 --out W1s1742
```
`--quad` is the screen's corners on the clip's first frame, clockwise from top left, in 0..1 (read them
off a still with a grid). `track_screen.py` fits the screen's own four edges on every frame, carries an
edge it can't see (cut by the frame edge, hidden by someone) from the frame before, smooths the corners
(`--smooth clip` for one smooth camera move) and draws `mv/review/screen_CODE.jpg`: the outline has to
sit on the screen's edge on every frame. Following the outline keeps the panel turning exactly with the
building; on a drone shot an earlier tracker let the panel turn more than the tower, which the user
caught, and a feature-point homography drifted. The screen has to differ from its surroundings in
brightness, so generate it blank and dark ("a large blank black LED screen on the tower").
`bake_screen.py` warps an image or a video onto it and copies the clip's matte and depth to the new
code. Content tied to the song, like a countdown, is a panel video per shot and one baked copy per shot.

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
- A block placed from its first frame alone lands on a face later in its span: after a cut, or when the
  person moves or turns. Place it over the whole span (`ov.place`).
- An effect that darkens or drops everything outside the person matte drops the props with it: a
  "lights out" moment kept only the people, and the singer's car went black. Mattes hold people only;
  keep such effects off shots that a car, a set or a prop carries.
