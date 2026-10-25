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
   mark, a word, a line around a person. Write 2-3 candidates per motif.
3. Pick 3-6 that together tell the song's arc: something that builds, something that pays off at the
   drop or last chorus, something that changes on a specific lyric. One strong overlay carried through
   the whole video beats five busy ones.
4. Check them against the brief's mood, the craft list and habits in SKILL.md Phase 5, and the
   history. A restyled HUD, meter, ring or analyzer gets replaced. So does anything that reframes
   or restyles the whole picture for longer than a beat or two.
5. Build in `fx.py`; prototype each on a still sheet at the moments it matters. Drop what doesn't read
   at full speed, and what hides the footage.

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

The only picture-wide effects, and only briefly: a flash frame, the color channels tearing apart, one
beat in negative, a radial zoom blur, strobing exposure for the last bar into a drop, a freeze, a burn
across the cut, two frames of block glitch, half a beat stuttered, a beat of black before the drop, a
shake. Thermal, infrared, halftone, posterize or kaleidoscope can flash for a beat; as the look of a
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
