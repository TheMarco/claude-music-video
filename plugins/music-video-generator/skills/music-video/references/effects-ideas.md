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
   materials, instruments, verbs ("dust in the sky", "a letter never sent", "salt water"). Prefer
   motifs with a process you can watch happen (a line being drawn, a crack spreading, metal heating
   from red to white, a word burning out): an overlay that does something over time carries a shot,
   one that only appears decorates it.
2. For each, ask what it would look like as something drawn over the footage: a particle, a light, a
   mark, a word, a line around a person. Write 2-3 candidates per motif.
3. Pick 3-6 that together tell the song's arc: something that builds, something that pays off at the
   drop or last chorus, something that changes on a specific lyric. One strong overlay carried through
   the whole video beats five busy ones.
4. Check them against the brief's mood, the craft list and habits in SKILL.md Phase 5, and the
   history. A restyled HUD, meter, ring or analyzer gets replaced. So does anything that reframes
   or restyles the whole picture for longer than a beat or two.
5. Build in `fx.py`; prototype each on a still sheet at the moments it matters. Drop what doesn't read
   at full speed, and what hides the footage.

## Set pieces

The moments people remember are designed, not accumulated: the first drop, the last chorus or final
drop, and the ending. Plan each as a set piece in three parts, and build the first drop before the rest.

- **Anticipation (the bar before).** Hold something back so the hit has room: graphics thin out, the
  frame darkens or desaturates, the edit slows or tightens to close-ups, a loop stutters, a ramp speeds
  the footage up, the last half beat goes black or freezes. The song is already doing this; follow it.
- **The hit (the drop's first frame).** Up to three things land together, chosen from cut, light,
  colour, motion, scale and type: the strongest shot in the footage, the colour that has been withheld
  arriving, the performer matte-cut into a new world, the title slamming in, a ramp dropping into slow
  motion. More than three at once is noise.
- **Follow-through (the next 2-4 beats).** Something keeps moving after the hit: sparks still falling,
  letters settling, the slow motion easing back up to speed, a ghost trail behind a spin. A drop that
  hits and then goes still reads as a jump scare.

## Transitions

Most cuts in a music video are hard cuts on the beat, and that is what makes it feel cut to the music.
A transition marks a seam, so choose it from what the two shots are to each other:

- **A jump in energy** (breakdown into drop, verse into chorus): a whip, a zoom through, a white dip, a
  burn. Centred kinds switch on the beat.
- **A change of place or time with the same person** (the performer, then the performer elsewhere):
  `matte`, where they stay while the world changes behind them, or `matte_in`, where they arrive first.
  This is the most music-video transition there is; spend it on the story turns.
- **A drift at the same energy** (intro, breakdown): dissolve, luma, defocus.
- **A shape or motion shared by both shots**: a match cut, hard, on the beat. No effect needed.

One device per seam, never stacked (a whip plus a flash plus a glitch is noise). A transition's shapes
come from the frame: the performer's silhouette, the light in the shot, a door edge; a wipe whose shape
comes from nowhere looks like a slideshow. A video's own transition (`GLSL_MIX` in `fx.py`) is part of
its identity: slats of light, the picture tearing along a seam, ink spreading from the lyrics' object.

## Time

Speed is a material, not a setting. Ramp into the drop (`ramp=` fast, then slow motion on the hit) and
out of it; loop a half beat of a gesture on a snare roll (`loop=`); freeze on the downbeat (a ramp to
0); play smoke, water and debris backwards (`rev=True`); leave trails of a dancer (`ghost=`). Use one or
two of these as the video's devices, at the moments they mean something.

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

Pinned to the footage (`track.py`): a flare that lives on a street lamp and blooms on the kick, light
rays from a window marched through the bloom, sparks thrown off a hand or a grinder, a word painted on a
wall that stays on the wall as the camera moves, a lyric written in the sky above a moving car. Pinned
graphics feel shot rather than added; give them the scene's light (warm near a lamp, blue near a screen).

How these move matters as much as what they are: easing, follow-through, depth and streaks are in
`compositor.md`, "Motion".

## Accents (a beat or two, on drops and big hits)

The only picture-wide effects, and only briefly: a flash frame, the color channels tearing apart, one
beat in negative, a radial zoom blur, strobing exposure for the last bar into a drop, a freeze, a burn
across the cut, two frames of block glitch, half a beat stuttered, a beat of black before the drop, a
shake, a lightning flash (two to four snapping strokes a couple of frames apart). Thermal, infrared, halftone, posterize or kaleidoscope can flash for a beat; as the look of a
section or the video they are takeovers.

## Color (inside the grade)

One hue that arrives at the drop, the grade shifting section by section, a slight push on the kick,
split toning, hot blacks, warm to cold across the song. The footage stays readable.

## Type

Text is sparse in a music video. A single huge word cut in on the snare, words made of light that burn
out, the title with footage inside its letters, stencil spray with overspray, words that shatter on the
drop, one lyric line transformed through the song, letters scratched into the film, a word strobing
between faces on the hats, letters landing one by one and overshooting on the drop, a word pinned into
the scene. No serif labels, captions or numbered plates as a running device. Kinetic type lives on its
motion: each letter eases in, settles, and leaves faster than it came (`ov.glyphs`, `stagger`).

## Audio mappings

Kick: punch, a color push, the overlay pulsing. Snare: a cut, sparks, a word. Hats: sparkle, streaks,
grain flicker. Bass (low bands): glow, vignette breathing. Vocals (mid bands while singing): glow on the
person, type lighting up. Loudness: exposure, how many overlays are on. Section energy: keep calm
sections cleaner so the loud ones land, but never let the loud sections go still; the drops have to hit.
