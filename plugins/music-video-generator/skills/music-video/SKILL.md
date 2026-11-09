---
name: music-video
description: Make a complete music video for a song, from brief to final render in 16:9, vertical 9:16 or square. Covers beat-grid song analysis (including tempo drift) and lyrics, AI-generated performer and lipsync clips through whatever video-generation MCP the user connects, archive.org and other free or user-supplied footage and photos, a credit budget, and a GPU shader compositor whose overlays and graphics are designed fresh for every video on top of the graded footage (person mattes, film grain, audio-reactive overlays, lyric timing), with a history of past videos so each one has its own identity. It also makes archive-only videos, visualizers, lyric videos and social cuts with no AI footage at all. Use this whenever the user wants a music video, visualizer, lyric video, Reels/TikTok/Shorts cut of a song, footage or photos cut to a track, a DJ/singer/dancer rendered for a song, or changes to an existing mv/ project (EDL, overlays, grades, re-renders), even if they never say "music video".
---

# Music video

This skill turns a song into a finished music video: a beat-locked edit of AI-generated performer clips
and/or archive and library footage, finished in a GPU compositor (moderngl), rendered with the original
audio at 1920x1080 by default (any size, including 1080x1920). The picture is the graded footage, full
frame; each video's identity comes from what is drawn on top of it (signature overlays, type, title),
designed for the song inside the user's brief. A history file keeps later videos from repeating earlier
ones.

**Paths.** `$SKILL` below means this skill's base directory, which Claude Code shows when the skill
loads. Per-user data lives in `~/.claude/music-video/`: `history.md` (created from
`$SKILL/assets/history_template.md` on first use), `refs/` (frame sheets of accepted videos) and
`local.md`.

**Standing preferences.** If `~/.claude/music-video/local.md` exists, read it before Phase 0: it holds
this user's own tools and standing preferences as plain Markdown, one per line, and it wins over the
defaults here. When the user states a preference meant to last (their provider and model, a resolution
they always want, their credit line, something they never want to see again), add a line to it and say
that you did. One-off choices for a single video go in the project's notes, not here.

**The engine.** The pipeline scripts are not part of the plugin. They live in the `engine/` folder of
the skill's public repository, github.com/TheMarco/claude-music-video, and are downloaded once per
engine version, pinned to one commit, into `~/.claude/music-video/engine/<commit>/`. `$ENGINE` below
means that folder:

```bash
SKILL="<base directory>"
ENGINE_REV=691f52588134b4fff8d1905463db0804a91bfb84
ENGINE="$HOME/.claude/music-video/engine/$ENGINE_REV"
if [ ! -f "$ENGINE/template/mv/scripts/render.py" ]; then
  TMP="$ENGINE.part" && rm -rf "$TMP" "$ENGINE" && mkdir -p "$TMP" &&
  curl -fsSL "https://codeload.github.com/TheMarco/claude-music-video/tar.gz/$ENGINE_REV" |
    tar -xz -C "$TMP" --strip-components=2 "claude-music-video-$ENGINE_REV/engine" &&
  [ -f "$TMP/template/requirements.txt" ] && mv "$TMP" "$ENGINE"
fi
```

Shell variables don't carry over from one command to the next. Start every command that uses `$SKILL`,
`$ENGINE` or `$ENGINE_REV` with the three assignment lines above; the `if` block is needed only once.

Tell the user once, before the first download, that the skill fetches its scripts from that repository
at that commit. It is setup, a small set of scripts, and the one download that doesn't wait for the go
in "Working rules". The template in it (`$ENGINE/template/mv/scripts/`) is a working pipeline. Copy it
into each new project. Three files belong to the video and get written for it: `edl.py` (the cut),
`look.py` (palettes, grades, the finish) and `fx.py` (its overlays and shaders). The rest is the engine.

```
<project>/
  song.mp3, reference photos         from the user
  .venv/                             Python venv (see setup)
  mv/NOTES.md                        the brief in the user's words, decisions, job ids, where the work stands
  mv/scripts/                        copied template; edl.py, look.py, fx.py written per video;
                                     ENGINE_REV, the engine commit the copy came from
  mv/data/   song.json, lyrics.json, audio_feats.npz, codes.json, crops.json, edl.json, budget.json
  mv/clips/  <CODE>.mp4 AI clips (+ <CODE>_matte.mp4)    mv/keyframes/ generated stills
  mv/archive/<identifier>/ archive films                 mv/work/ segments, stills, sheets
  mv/review/ copies for the user to check                mv/out/ renders
```

## What kind of video is it?

Every request uses the same pipeline; the request type decides which phases matter.

| Request | Footage | What to lean on |
|---|---|---|
| Music video with performers | AI clips + archive | The whole flow below; "Choosing the mix" |
| Archive-only, or no budget | archive.org, the user's own footage | "Archive-only videos"; `references/compositor.md` |
| Visualizer | procedural backgrounds, artist photos, a few archive textures | An audio-reactive picture built in `fx.py` from the spectrum, waveform and drum envelopes; no AI needed |
| Lyric video | any backgrounds | Confirmed lyrics; line and word timings from `ov.lyric_at(t)`; a type treatment designed for the song |
| Performance / lipsync | AI lipsync clips | `references/video-providers.md` "Lipsync": one take per sung line, shown only where it was recorded; `sync_offset.py --save`, `mouth_check.py`, `mv/data/mouths.json` |
| Photo or album-art video | stills in `codes.json` | Slow zoom and pan per shot; grades; overlays between photos |
| Vertical or square cut, teaser | an existing edit | `render.py --size 1080x1920` (matted shots reframe on the person); `--start/--end` for a 15-30 s hook (see Phase 6) |
| The user's own footage | local files in `codes.json` | Same as archive; check framing with contact sheets |
| Remake of an existing music video | the original video plus new footage | The original's soundtrack is the song and its timing is final: singer shots at their own song times (`sync=0`), the original audio stream kept (Phase 6, "Lip sync"); anything the user excludes (a person, a logo) checked on every shot's full visible span (Phase 5) |
| Changes to an existing project | whatever it has | Read `mv/NOTES.md` first (or whatever notes an older project has); see "Updating a project's engine" if its scripts are older than the template |

## Working rules

These matter more than any technique below.

- **Collect the whole brief before working.** Briefs often arrive in pieces, and an imperative sentence
  inside one ("render the dancer at 1080p...") is not a go-ahead. Ask your questions, then wait for an explicit
  go before spending credits, downloading or rendering. Save the brief in `mv/NOTES.md` as it grows, in
  the user's own words.
- **Keep `mv/NOTES.md` current.** The brief, the chosen concept, decisions the user made, generation
  job ids, and the phase the work is in. A project outlasts a session and a context window; these notes
  are what the next one starts from, so read them first when returning to a project.
- **The user judges faces and taste.** Don't build automated likeness checks or narrate your own face
  comparisons. Put the reference photo and the clips in `mv/review/` and give the path. For a real
  person, render one test clip and wait for approval before the batch.
- **Show the pieces before the long render.** After generating clips, list where they are so the user
  can look first.
- **Report money after every paid batch**: what it cost, what is left.
- **The brief's mood and look words are binding.** Check every concept and every still sheet against
  the user's own words first. Variety happens inside the brief, never against it.
- **Effects are overlays, not takeovers.** The footage stays graded footage, full frame, for the whole
  video. Overlays, type and short accents sit on top of it. Reframing the footage into cards, panels or
  pages, or restyling the whole picture as print, a diagram or an exhibit, turns a music video into
  something that reads like a textbook.
- **Each video gets its own identity.** Videos that share overlays (a HUD frame, a spectrum analyzer,
  the same title and word styles) look like one family even when each adds something new. New
  signature overlays, type and title for every song (Phase 3).
- **Text is sparse.** Running subtitles belong in lyric videos, when asked.
- **Grain, when a look uses it, has to read as film, not digital noise.** The engine's grain does this
  (clumped, per dye layer, midtone weighted).
- **Never "fix" original footage with someone singing.** When the song is an existing video's own
  soundtrack, the singer's shots play at exactly their original times (`sync=0`) with the original
  audio: no lip-sync measurement, no offsets. If the user reports it out of sync, check that the shots
  sit at their original times and ask whether the original plays in sync for them; build nothing.

## Phase 0: the brief

Ask these in one plain message, each with your default, so the user can answer only what they care about:

1. **Lyrics** as text, and the language they are sung in? (Default: transcribe with Whisper, in
   English unless the title or brief says otherwise, and confirm the unclear lines.)
2. **Theme and angle.** Any double meaning worth playing (a song about a city, set against old footage
   of that city being built)?
3. **Look and mood.** A few words, references, or free rein? (Default: three directions inside the
   mood, proposed after the song analysis, Phase 3.) Write the user's words down exactly; they are the
   test for everything later.
4. **Footage mix.** How much AI-generated versus archive footage, or archive only? See "Choosing the mix".
5. **AI provider and settings** if any AI footage: which MCP, model, resolution, clip length, lipsync
   or not. Default: whatever video MCP is connected, low resolution (480p) to save credits, no lipsync,
   10 s clips, 15 s for long dance takes.
6. **Performers.** Reference photos, outfits, settings. Real people need the identity method in Phase 4.
7. **Budget** in credits or money. Default: propose a number from the plan (see "Budget").
8. **Story or mood piece.** Default: a mood piece that still tells a story without words, in chapters
   that follow the song's sections (Phase 5).
9. **Text and graphics.** Default: decided by the concept; can be none at all.
10. **Output.** Default: 1920x1080, 24 fps, H.264 + AAC. Vertical (1080x1920) or square cut needed?
11. **Artist and title credit** exactly as they should appear. File tags are often wrong.

### Choosing the mix

Talk this through with the user; it drives the budget and the look.

| Mix | When it fits | Cost |
|---|---|---|
| Archive only (0% AI) | Era, place or history themes; abstract or visualizer videos; no budget; no likeness risk. Performers come from archive (soundies, dance films, crowds) and the compositor does the rest. | Free |
| Light AI (10-30%) | Hero shots of the artist for the intro, drops and ending; archive carries the rest. | Low |
| Balanced (40-50%) | Performers carry the drops and choruses, archive carries verses and breakdowns. | Medium |
| AI-heavy (70-100%) | Story videos, lipsync, a performer on screen most of the time. | Scales with runtime |

Planning numbers: a 10 s clip usually gives 3 to 5 usable cuts, so render about 1.5 times the AI screen
time you need. The EDL builder prints the actual archive/AI split; check it against what was agreed.

### Archive-only videos

Without AI clips, the edit and the compositor carry the variety: speed and time (motion-blended slow
motion, reverse, freeze, stutter), double exposures on the OVER track, person mattes on archive shots
(`matte=True`) so overlays can sit behind people, grades that unify decades of film stock, and the
concept's overlays in `fx.py`. `references/compositor.md` lists the per-shot options.

### Budget

1. Find the provider's balance and pricing tools in its MCP (a balance, estimate or model-list tool).
2. Price the plan: clips x seconds x rate, plus stills for keyframes, plus about 20% for retakes.
3. Agree a number with the user, then `python3 mv/scripts/budget.py set N --unit credits`.
4. Before each batch `budget.py plan LABEL AMOUNT`; after it `budget.py add LABEL AMOUNT`, failed and
   rejected takes included. Run `budget.py` to see spent and left, and stop to ask before exceeding.
5. Report spend and balance after each batch and in the final report.

## Phase 1: setup

Needs Python 3.10-3.13, ffmpeg on the PATH, and a GPU with OpenGL 3.3 (any Mac from the last decade, or
a Linux or Windows machine with current drivers).

```bash
python3 -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 13), sys.version'
mkdir -p mv && cp -R "$ENGINE/template/mv/scripts" mv/ && echo "$ENGINE_REV" > mv/scripts/ENGINE_REV
mkdir -p mv/data mv/clips mv/keyframes mv/archive mv/review mv/work mv/out
python3 -m venv .venv
.venv/bin/pip install -q -r "$ENGINE/template/requirements.txt"
.venv/bin/python -c "import moderngl; print(moderngl.create_standalone_context().info['GL_RENDERER'])"
```
If the first line fails, build the venv with a Python in that range (`python3.12 -m venv .venv`). On
Windows the venv's Python is `.venv\Scripts\python`. Lyrics transcription uses mlx-whisper on Apple
Silicon (installed by the requirements); elsewhere `pip install openai-whisper`. `models.py` downloads
the Whisper and person-matte models on first use with plain anonymous requests and pinned checksums;
keep model downloads in `models.py` rather than the libraries' own downloaders. Fonts are picked per
video in `fx.py`; `F` and `FS` in `overlay.py` point at the macOS system font folders, and on other
systems any `.ttf` or `.otf` path works (`references/compositor.md`, "Fonts"). Run every script from
the project root.

### Updating a project's engine

A project's `mv/scripts/ENGINE_REV` names the engine commit its scripts came from; a project without
that file is older than any engine that writes it. When it differs from `$ENGINE_REV`, copy
`mv/scripts/` to `mv/scripts_old/`, then copy the template's engine files over everything except the
project's own `edl.py`, `look.py` and `fx.py`, write the new `ENGINE_REV`, and install the template's
requirements again. The part of `edl.py` below its EDIT block is engine too: carry the template's
changes there into the project's copy, keeping any project additions, and re-run `edl.py`. A project from engine
1.1.0 or earlier also needs the four-line `fx.py` change in `references/compositor.md` ("The picture
never trails the sound"), or its beat-timed accents land a frame after the cuts. Render stills at 4-6
moments with both and compare before changing anything else.

## Phase 2: the song

```bash
.venv/bin/python mv/scripts/analyze_song.py song.mp3 --title "Title" --artist "Artist" --lyrics [--language es]
```
`--language` is the language the song is sung in (a Whisper code; `en` when left out).
This writes a draft `mv/data/song.json`: BPM, beat-0 offset `t0`, sections (name, start, end, kick,
calm), drops, shocks, countdowns, suggested letterbox spans, end-card time. AI-generated songs often
drift by several BPM over their length; the analyzer then writes a `beats` map that follows the drift,
and every script uses it automatically (`beat(k)` and `beat_at(t)` in `timing.py`). A "WEAK BEAT"
warning (ballads, rubato) means cutting on phrases, lyrics and energy changes instead of strict beats.
Treat it as a draft:

- Rename sections after listening and reading the lyrics (intro, verse, build, riser, drop1, chorus,
  breakdown...). The first section should stay "intro".
- Check the drops (it may flag a bass return as a drop), the countdowns (8 beats before a drop) and the
  end time. These are facts about the song; whether anything happens visually at them is up to the
  concept.
- Whisper invents lines in instrumental parts; `lyrics.json` marks likely ones with `suspect`. Ask the
  user for the real lyrics if anything matters on screen.
- Whisper can also miss lines. The analyzer transcribes in overlapping 30 s windows, which is more
  reliable than one pass over the whole song (a single pass once dropped a 1984 single's first verse
  and put verse 1 three seconds late); if a stretch where someone audibly sings still has no lines,
  `lip_check.py` prints word timings for the 8 s around any song time.

**Check the grid before anything is cut to it.** `.venv/bin/python mv/scripts/gridcheck.py` prints,
per section, how the song's kicks sit on the grid, with a hint when the first beat looks half a beat
off, the tempo half or double, or a section drifting; and it writes `mv/review/grid_check.wav`, the
song with a click on every beat and a higher one on every bar line. Follow up each hint (correct `bpm`,
`t0` or the sections in `song.json` and run it again), then give the user the file along with the
section list to confirm by ear: a wrong grid spoils every cut after it.

Then `.venv/bin/python mv/scripts/audio_feats.py` writes the per-frame spectrum, loudness, kick,
snare, hi-hat and waveform data the overlays can react to.

## Phase 3: concept, look and signature overlays

Design this for every video, after the song analysis and before any footage is generated or collected:
the concept's light, colour and era go into the generation prompts and the footage search, and its
chapters and grades into the edit. A video has to do two things:
feel like this song and this brief, and have an identity no earlier video in the history had. The first
is never traded for the second.

**Every video keeps the craft:**
- **The brief's mood and look words.** They decide the light, the palette family and the finish.
  "Moody, nocturnal, film grain" means dark frames with real blacks and texture, whatever the overlays.
- **Footage fills the frame; effects are overlays on it.** The picture is the graded footage, full
  frame, from start to end. Signature effects sit on top: titles, sparse words, particles, light leaks
  and flares, small graphic elements, matte tricks such as a word behind a person. No takeovers: no
  reframing the footage into cards, panels, spreads, borders or 3D objects, no backgrounds replacing it,
  no picture-wide stylization (print, thermal, posterize, kaleidoscope, negative) as the look. A
  picture-wide hit is allowed as an accent of a beat or two on a drop. (Visualizers are the exception:
  there the picture itself is generated.)
- **The picture moves with the music.** Cuts sit on the grid, energy follows the sections, and each drop
  lands visibly harder than what led into it (cut, light, color, motion or scale).
- **It tells a story without words.** Chapters that follow the song, each with its own footage, angles
  that change, and colour that turns when the story does (Phase 5). Footage chosen only for mood, mixed
  from every source in every section, reads as disconnected however good each shot is.
- **A finish with weight.** Start from the `STARTS` entry in `look.py` that matches the mood: real blacks
  for dark songs, grain, glow and halation where the mood is filmic or nocturnal. An empty finish with
  a pale grade reads flat.
- **It reads as a music video, not a document.** No printed-object, textbook, museum, catalog, diagram
  or specimen styling: paper and card stock, serif labels and captions, engraved borders, numbered
  plates.

**Every video changes the identity:** the signature overlays, the title and credit treatment, type, the
specific palette, transitions. For a different song, nothing listed under a history entry's identity
lines returns unless the user asks.

1. **Brief and song first.** Write down the brief's mood and look words, and what the song does at its
   loudest point (tempo, drops, how the energy feels). Every concept has to pass both.
2. **Read `~/.claude/music-video/history.md`** (create it from `$SKILL/assets/history_template.md` if
   missing): the identity lines of recent videos and any rejected directions. For a new version of the
   same song, keep the brief's look and the edit's energy; replace what the user objected to.
3. **Collect motifs and sparks.** 5-10 concrete motifs from the title, lyrics, theme and footage; method
   and sparks in `references/effects-ideas.md`. For more, `python3 "$ENGINE/scripts/concept_dice.py"`
   draws random overlay ideas; use the ones that serve the brief and drop the rest.
4. **Write three concepts**, three different identities inside the same brief. For each: one or two
   sentences on what a viewer sees and feels at the drop (light, color, what fills the frame, what
   moves); the look (palette, finish start); title and credits; type, or none; 3-6 signature overlays,
   at least half new code, building toward the drop or last chorus; the edit's devices; the story in
   one line per chapter. Each overlay says how much of the frame it covers and when: most of the time
   the footage is what you see.
   Sensation over conceit: a concept whose appeal is a clever mapping that needs explaining (the verses
   as chess moves, the song as a lecture) is a design idea, not a video idea. Drop it.
5. **Test each concept** against the craft list above and the habits below; replace any that fails.
6. **Propose.** Send the three in one short message with a recommendation, and ask which one in a plain
   question. Recommend the one that fits the brief best and hits hardest at the drop, not the most novel
   or the cleverest. If the user says to choose, that is the one.
7. **Avoid these habits.** Sessions reach for them whenever they go for the familiar, and they make
   different videos look like one family. Each is off unless the user asks for it:
   - broadcast, telemetry, surveillance or camcorder HUD frames: corner brackets, tally light, captions
     joined by "·", timecode and BPM readouts
   - spectrum analyzer bars, oscilloscope traces, rings rippling from the center on kicks, symbols
     popping on snares
   - meters, counters and readouts climbing into the drop
   - thin, widely tracked capitals for the artist and title, centered over the intro
   - one big word behind the performer in a heavy grotesk (Futura, Impact)
   - letterboxed intro and breakdown with lyric cards decoding in the bar
   - a film-leader countdown before drops; a white flash plus a shockwave ring on the drop
   - star glints on the hi-hats, neon-tube script, synthwave sun-and-grid backgrounds

   These are graphics, not finish. Glow, grain, halation, punch, shake and letterbox framing are craft
   and stay available to every video.

Once the user has chosen, write the concept into `mv/NOTES.md`: it steers the footage (Phase 4) and the
edit (Phase 5), and it is built in Phase 6.

## Phase 4: footage

### AI clips, with any MCP

Use whatever video-generation MCP the user has connected; the skill holds no provider keys and works
only through that MCP's tools. `references/video-providers.md` covers the method for any provider:
finding the tools and reading each model's capabilities (start frame, reference images, durations,
resolutions, audio, price), getting local reference photos to the provider, downloading outputs with
`fetch_clip.py`, polling and costs. It ends with notes on one provider (Hedra) as an example.

- **Real people (the artist, a dancer from a photo):** identity comes from their actual photo through
  the model's reference-image mode, never from an animated generated keyframe
  (`references/video-providers.md`, "Method that carries over"). Render one test clip, put it next to
  the photo in `mv/review/`, and wait for the user's verdict.
- **Masked or invented characters** (a robot, a mascot, a stylized character): make a keyframe still
  first (cheap, saved in `mv/keyframes/`), check it, then animate from it as the start frame.
- **Inventory the angles first.** Contact-sheet the performer clips you have and spend credits on the
  missing angles (profile, from behind, overhead, low, wide), not on more frontal close-ups. Name the
  angle and the move in every prompt.
- **Lipsync:** one take per sung line, shown only at the song time it was recorded for; every other
  shot of the singer keeps the mouth closed or out of view (`references/video-providers.md`, "Lipsync").
  Any source with a singing mouth, AI or not, gets the lip-sync check in Phase 6 before delivery.
- **Prompts:** describe the motion, camera move, light and atmosphere; turn generated audio off; no
  lipsync unless asked; frame people knees-up or closer so faces hold; for masked characters say the
  face is never shown. Write the concept's look into the prompts (light, color, era) so the clips are
  shot for it rather than graded into it afterwards.
- Save clips as `mv/clips/<CODE>.mp4` with short codes (P1-P6 for one performer, Q1-Q6 for another):
  `python3 -I mv/scripts/fetch_clip.py mv/clips/P1.mp4 URL`. Then make mattes: `.venv/bin/python mv/scripts/make_matte.py mv/clips/*.mp4` (skip files already
  ending in `_matte`).
- Write each job id into `mv/NOTES.md` when you submit it, so a lost context can pick the jobs up.
- Keep superseded clips in a subfolder rather than deleting them.

### Archive, library and the user's own footage

Any video or image file can be a source: add `"CODE": "path/to/file.mp4"` (or `.jpg`, `.png`) to
`mv/data/codes.json`. `references/archive-org.md` covers archive.org and other free sources: search,
rights, downloading, scanning films for usable shots and contact sheets. In short: `ia_search.py` to find
items, `ia_fetch.py` to download, list them in `mv/data/codes.json` as short codes (A1, A2 for one
theme, B1 for another), `scan_archive.py` to find night-light and flash moments, `contact.py` to look at
labeled thumbnails and pick in-points. Black bars are cropped automatically; override odd framing in
`mv/data/crops.json`. Several codes can point at one file with different crops (a 4:3 film cropped high
for close-ups and centered for wides); `edl.py` counts reuse per file.

Footage where a singer's mouth is on screen (an existing music video, the user's performance footage,
concert film) is placed with `sync=` like a lipsync take: an existing video cut against its own
soundtrack uses `sync=0`, which shows every frame at its own time, exactly as the original plays.

## Phase 5: the edit

**Plan the story first, even for a mood piece.** Before the EDL, write a chapter table: one row per
song section with what happens, the footage pool, the shot sizes and the grade. Show it to the user
with the plan. A made-up example for a song about leaving town at night:

| Section | What happens | Footage | Sizes | Grade |
|---|---|---|---|---|
| intro | the town at dusk, lights coming on | B1, B4 | W, W, M | cold |
| verse 1 | the same day again: clocks, queues, traffic | A2, A5 | M, C, W | cold |
| chorus 1 | the road out of town | C1, C3, P1 | W, M, C | cold |
| drop 1 | the night opens up: neon, speed | C2, P2, P3 | W, C, X | warm |
| breakdown | stopped at the edge of the sea | D1, P4 | W, M | warm |
| drop 2 | driving on, the town gone | C4, P5, P6 | W, M, C | warm |

Each chapter uses its own footage, and no section interleaves every source: a video that rotates all
its films shot by shot reads as a montage with no progression. Colour follows the story too: one grade
per chapter, changing at a story turn (`STORY_GRADES` and `AI_STORY_GRADES` in `edl.py`), never from
film to film. Tag shot sizes with `size="W"` (W, M, C, X), open each chapter wide, and avoid neighbours
of the same size; varied angles and sizes are what make the footage feel shot rather than collected.

Write this video's palettes and grades in `look.py` first (Phase 6, "Build the concept"): `edl.py`
stops on a grade name `look.py` doesn't define. Then write the cut in the EDIT block of
`mv/scripts/edl.py` as beat-aligned sections of shots (its docstring lists every shot option), and run `.venv/bin/python mv/scripts/edl.py`. It checks that
sections tile the song, adds the black end-card tail, clamps in-points to each source, checks grade
names against `look.py`, prints the archive/AI split and a table of cuts, shot length and sources per
song section, and warns about: footage reused (`motif=True` marks a deliberate repeat), look changes
between consecutive archive shots that aren't at a story turn, an average shot length outside
`PACE_BEATS`, sections with more than `MAX_SOURCES` sources, shot-size problems, and singer shots whose
mouth may move off the lyrics. Fix each warning or know why it stands.

Pace comes from the song. A 120-130 BPM dance track wants most shots between half a beat and two beats
in the loud sections, longer in breakdowns, faster into drops: about 150-180 cuts in three and a half
minutes, an average of 2-4 beats per shot. A ballad or a weak beat wants phrases (raise `PACE_BEATS`).
Few long takes in a fast song read as stuck, and twice the cuts reads as noise. The concept adds devices
on top (match cuts, repetition, freezes, ramps), as chosen in Phase 3. Save the most striking footage
for the moments the song builds to.

**Check every shot before rendering.** `.venv/bin/python mv/scripts/contact.py mv/work/shots --edl`
makes contact sheets of every shot at its midpoint, cropped as rendered, and prints a brightness report.
Look at all of them: title cards, in-points on the wrong side of a cut, shots too dark to read. Shots
flagged bright (mean luma above 0.42 or 90th percentile above 0.85) usually want `expo=0.6-0.8`.

A shot shows more of its source than its own length: while the next shot dissolves in, it keeps playing
for the length of that dissolve (`xd`). `edl.py` warns about shots that run across a cut in their source
over that full span, and about footage reused anywhere (AI clips included). When the user excludes
something from a source (a person, a logo, a scene), check the first and last frame of every shot's full
visible span, dissolve tail included, not only its midpoint: the contact sheet shows midpoints, and
dissolves in old films carry a ghost of the next shot for a second or more.

## Phase 6: build, preview, render, QC

**Build the concept.** `look.py`: the `FINISH` (from a start), on top of the palettes and grades written
for the edit. `fx.py`: overlays
(`draw_front`, `draw_behind`), shaders (`GLSL_COMP` with the person matte, `GLSL_FINAL`) for matte
tricks, light and accents, and per-frame uniforms from the audio and song position (they can also drive
any engine value). The engine draws nothing by itself and stays untouched.
`$ENGINE/examples/fx_examples.py` shows the mechanics; it is not a kit. `references/compositor.md`
documents the engine, the per-shot options and the `fx.py` hooks.

```bash
.venv/bin/python mv/scripts/contact.py mv/work/shots --edl                       # every shot + brightness
.venv/bin/python mv/scripts/render.py mv/work/stills/s --stills 8,30,48,62,110,152,196
.venv/bin/python mv/scripts/sheet.py mv/work/stills/s mv/work/stills/sheet
.venv/bin/python mv/scripts/render.py mv/out/<name>_v1.mp4                         # full render
.venv/bin/python mv/scripts/beatsheet.py mv/out/<name>_v1.mp4 mv/work/drop1.jpg <drop_time> 32   # one frame per beat
.venv/bin/python mv/scripts/qc.py mv/out/<name>_v1.mp4 --ignore-after <end>
.venv/bin/python mv/scripts/render.py mv/out/<name>_9x16.mp4 --size 1080x1920      # vertical cut
.venv/bin/python mv/scripts/render.py mv/out/<name>_hook.mp4 --size 1080x1920 --start <drop> --end <8 or 16 bars later>
```

**Judge the stills before the full render**, at the drops, the loudest chorus, the breakdown, the intro
and the end card. The y-flip, palette and exposure mistakes all show up there. Don't approve your own
stills because the idea is clever.
- Read them against the brief's words: would the user recognize their brief in these frames?
- If the history has accepted videos with frame sheets in `~/.claude/music-video/refs/`, put the new
  stills next to them: as rich and as hard-hitting, clearly a different video. Without any, judge
  against the craft list in Phase 3.
- Check `sheet.py`'s tone readout. For a dark or moody brief, dark shots need real blacks (black
  share 0.25 or more); a pale, printed-looking picture sits around 0.05-0.15 on every shot.
- Compare with frames from the last three videos in the history for repeated identity.
- The story test: from the still sheets alone, write one sentence per section saying what happens.
  If you can't, the video is still a montage; rework the chapters before rendering.
- Credits: the end card shows the artist and title exactly as the brief gave them, and names every
  source whose license asks for a credit (CC-BY items; each `mv/archive/<id>/meta.json` has the license).

A three-and-a-half-minute render takes a few minutes on a recent Apple Silicon Mac; segments are cached
in `mv/work/seg/` (delete a clip's segments there after replacing the clip). Fine grain raises the
bitrate: expect about 900 MB for three and a half minutes at CRF 19 with heavy grain. After the render,
`beatsheet.py` shows whether the picture lands on the beats around a drop, `qc.py` lists black frames
and frozen stretches, and `ffprobe` on the file should show one video and one audio stream as long as
the song.

**Lip sync.** When the song is an existing video's own soundtrack and the user sees that video play in
sync, its timing is final: singing shots at their own song times (`sync=0`), no offset. Don't "correct"
it from a measurement. Whisper's word timings on sung vocals can be off by a third of a second, enough to
make a source that plays in sync look 0.36 s early on a strip read against them; a remake was shifted by
exactly that and the user, who saw the original in sync, had to undo it. `lip_check.py` strips help place
a lipsync take or check the user's own footage, and `av_offset` (`lip_check.py CODE --save SECONDS`) is
for a source the user sees out of sync when it plays on its own. Ask the user to watch the source before
setting one.

When the song is a video's own soundtrack, keep that audio unchanged in the final file: the render
encodes the song as AAC, so put the original stream back with
`ffmpeg -i OUT.mp4 -i ORIGINAL.mp4 -map 0:v:0 -map 1:a:0 -c copy -movflags +faststart FINAL.mp4`.

**Hooks for Reels, TikTok and Shorts.** These platforms replay a video in a loop, so a hook should
start on a downbeat and run whole bars: `--start` and `--end` move to the nearest bar line (`--exact`
keeps the times as given), and the audio gets a 3 ms fade at each edge so it doesn't click. Feeds
show the first frame before playback starts, so start on a strong full-frame shot, not black or the
middle of a dissolve. Eight or sixteen bars from a drop usually work.

## Phase 7: report and history

Give the output path, duration, resolution and size; what changed since the last version; credits
spent this round, in total, and left; the sources credited on the end card; and anything the user must
check or decide: unclear lyric lines, archive items without a license field (Prelinger home movies have none; fine to use, worth checking
before commercial release), and any shot you are unsure about. Clear superseded renders only when asked.
Bring `mv/NOTES.md` up to date with the version delivered and what is still open.

When the user accepts a video, add its entry at the top of `~/.claude/music-video/history.md` in the
template's format (brief, look, edit, type, graphics, signature) and save a six-frame sheet of it to
`~/.claude/music-video/refs/<title>.jpg` (drops, loudest chorus, intro). When the user rejects a
direction outright, add it under "Rejected directions" with their reasons.
