# Effect ideas: sparks, not a menu

Signature effects come from the song and sit inside the brief's mood. They are overlays: the picture is
the graded footage, full frame, for the whole video, and the effects go on top of it. What earlier videos
used is in `~/.claude/music-video/history.md`; their identity lines are not reused for another song.

Two traps. Data-graphics overlays (readouts, meters, telemetry HUDs, spectrum analyzers) are the reflex
choice and make every video look like the same broadcast. The opposite overcorrection takes over the
whole picture (footage printed on cards or pages, paper stock, serif labels) and stops reading as a
music video. New overlays, same structure.

## Method

1. List 5-10 concrete motifs from the title, lyrics, theme and footage: objects, places, eras,
   materials, instruments, verbs ("dust in the sky", "a letter never sent", "salt water").
2. For each, ask what it would look like as something drawn over the footage: a particle, a light, a
   mark, a word, a line around a person. Write 2-3 candidates per motif, held to "What makes an effect
   land" below.
3. Pick 3-6 that together tell the song's arc: something that builds, something that pays off at the
   drop or last chorus, something that changes on a specific lyric. One strong overlay carried through
   the whole video beats five busy ones.
4. Check them against the brief's mood, the craft list and habits in SKILL.md Phase 3, and the
   history. A restyled HUD, meter, ring or analyzer gets replaced. So does anything that reframes
   or restyles the whole picture for longer than a beat or two.
5. Build in `fx.py`; prototype each on a still sheet at the moments it matters. Drop what doesn't read
   at full speed, and what hides the footage.

## What makes an effect land

The bar is the strongest slopcore references (`references/styles/slopcore.md`): every effect in them has
a reason a viewer gets in a second, and none is decoration. Invent to that bar for each video. Take the
reasons, never their effects; the examples below are illustrations, not a list to pick from.

**One explaining graphic per line.** Every sung or written line gets a graphic that shows what it means,
besides its type: it enters on the word that names it, moves in beats, and reads in one glance on a
phone. This is the layer that most separates a rich video from a decorated one. Find it with these
questions, in order, and stop at the first that gives a picture:

1. Does the line claim a number? A counter, a chart, a gauge, a before-and-after strike.
2. Is the joke about an interface? Draw that interface: a terminal, a chat, a poll, a status card.
3. Is there an object or a person in frame that can carry it? Label it, measure it, classify it (a
   detection tag with a wrong or funny class, a callout on the thing).
4. Does it describe a mechanism? A diagram of it, a flow, a plan view.
5. Does it name a place? A map, coordinates, a route.
6. What is at stake? A readout that ticks toward something.
7. Is it a callback? The earlier graphic, one step further.

The engine's device library (`devices.py`, references/compositor.md "Explaining graphics") draws most of
these answers: start from a device and fill it with the line's own facts, in the video's style; write
new code for the video's signature overlays and for a line no device fits. One graphic escalates across
the whole video (a reading that climbs, a poll that swings, a board that counts down): pick it in the
concept. The budget per frame is one main graphic, up to two labels on people or things, up to two rows
of micro type; a line whose picture already explains itself can go without.

- **The line, made physical.** Ask of each key line what it does, to whom, and what that would look like
  if it were real, then draw that. A line about being forgotten: the caption's oldest words fall off the
  top as new ones arrive, like a full context window. A line about being watched: the world outside the
  person drops to a coarse screen while they stay sharp. A line about running out of time: the person's
  matte fills with the accent colour from the feet up across the line.
- **The world's own medium.** The texture comes from what the story is made of: a newsroom story runs on
  newsprint, a story inside a phone on compression and screen glare, a courtroom on a sketch artist's
  pastel, a story at sea on the glitter of the water. It can change when the story turns. The depth
  treatments (references/compositor.md, "Depth") give the footage itself a medium from its own depth: a
  light wave travelling into the picture on the beat, contour lines that turn a place into a map, a scan
  that leaves a point cloud, haze; rotate them over the wides and leave most shots untreated. Outside a
  style that allows longer (slopcore's last act), a picture-wide medium stays a beat or two; between
  those beats it lives in the particles, the punctuation and the type.
- **Depth from the matte and the depth map.** Effects placed in space look expensive: a shape that passes
  behind the person (`draw_behind`) and in front of them (`draw_front`, clear of the face), the world
  dropping to black for a beat while the person stays lit, the world in one treatment and the person in
  another, light coming from behind them, a word tucked behind a tower or a rope (`behind_depth`).
- **One punctuation of its own.** One move for the big hits (the drops, the finale), the same each time
  and invented from the concept, held long enough to read: about a beat held and a beat of motion out of
  it. The picture collapsing to the person's silhouette in white on black and opening back up, the
  accent colour flooding the shadows and draining out. Never a one- or two-frame flash, whatever the
  references do: in testing those read as render glitches, and a mark on every hit turns into noise.
  The edit follows the words and the punctuation follows the drum (in the references the cuts land on
  the beat no more often than chance would; their flashes sit within two frames of it).
- **Attached to the picture.** Graphics that know where things are read as part of the shot: a label on
  a tracked head (`ov.heads`), a line drawn from the edge of the matte, a mark pinned to a fixed point in
  a locked shot. Those three are what the engine can follow; don't plan an effect that needs a tracker
  it doesn't have.
- **Type that acts out its word.** The entrance has a reason: a word about pressure arrives crushed flat
  and springs to size, a word about doubt types, deletes and retypes, a word about heat arrives glowing
  and cools to the type's colour, a price falls digit by digit like an odometer run backwards. One
  family per video, a new move on the hook.
- **Footage under everything.** A counter, a diagram or an inventory sits over the footage as a card or
  as type, never as a full-frame graphic with no video: a graphic screen cut in as a shot was rejected
  in testing.

Write each effect down as its line or moment, what the viewer sees, the reason in a few words, its
layer, and its timing (a hit, a hold, or an arc across the video). An effect without a reason goes.

Where each kind goes in the engine (`references/compositor.md`):

- `devices.py` through a `Plan` in `fx.py`: the explaining graphics, placed clear of faces and lyrics.
- The EDL's `depth_fx` and `behind_depth` per shot (after `make_depth.py`): the footage's depth medium.
- `GLSL_COMP`, `fxComp(col, uv, matte)`: per-pixel changes to the footage, with the person matte and
  `DEPTH`, under the type: screens and textures, the world dropping out, the person tinted or filled. Type
  drawn in `fx.py` stays sharp above it.
- `GLSL_FINAL` and the engine uniforms returned by `uniforms(t, a)` (`flash`, `invert`, `ca`, `punch`,
  `fade`): the whole frame, type included. Punctuation moves go here; a move that resamples the
  composited picture (`tComp`) adds the bloom textures (`tB1`, `tB2`) back itself.
- `draw_behind` and `draw_front`: shapes behind and in front of the person; everything in front goes
  through `ov.place` against the heads.
- The EDL's `echo`, `trail` and `glitch` per shot: afterimages, smears and tears.

## Overlays (draw_front / draw_behind, or additive light in fxFinal)

Light: light leaks drifting across on phrase starts, lens flares anchored to bright sources, beams
sweeping through the builds, light streaks racing across on the hats, a glow that swells with the bass.

Particles and materials: one thing from the lyrics or theme drifting over the footage (ash, embers,
sparks, snow, glitter, petals, dust motes), smoke in the lower third lit by the kick, water running down
the lens, thin cracks spreading from a corner on hits.

Marks: one small symbol or shape from the song that returns at key moments, changed each time; a
shadow sweeping over the frame before the drop; hand-drawn marks animated on twos around the subject.

Matte tricks (the person matte is in fxComp): a word behind the person, a thin glowing outline around
them, a halo behind them that swells with the voice, particles that pass behind them.

## Accents (a beat or two, on drops and big hits)

The only picture-wide effects, and only briefly, but each long enough to read (half a beat or more; a
single flashed frame reads as a glitch): the color channels tearing apart, one beat in negative, a
radial zoom blur, strobing exposure for the last bar into a drop, a freeze, a burn across the cut, half
a beat of block glitch, half a beat stuttered, a beat of black before the drop, a shake. Thermal, infrared, halftone, posterize or kaleidoscope can flash for a beat; as the look of a
section or the video they are takeovers.

## Color (inside the grade)

One hue that arrives at the drop, the grade shifting section by section, a slight push on the kick,
split toning, hot blacks, warm to cold across the song. The footage stays readable.

## Type

Text is sparse in a music video. A single huge word cut in on the snare, words made of light that burn
out, the title with footage inside its letters, stencil spray with overspray, words that shatter on the
drop, one lyric line transformed through the song, letters scratched into the film, a word strobing
between faces on the hats. No serif labels, captions or numbered plates as a running device.

## Audio mappings

Kick: punch, a color push, the overlay pulsing. Snare: a cut, sparks, a word. Hats: sparkle, streaks,
grain flicker. Bass (low bands): glow, vignette breathing. Vocals (mid bands while singing): glow on the
person, type lighting up. Loudness: exposure, how many overlays are on. Section energy: keep calm
sections cleaner so the loud ones land, but never let the loud sections go still; the drops have to hit.
