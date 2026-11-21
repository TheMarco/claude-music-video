# Style: slopcore

A named style. When the user asks for a slopcore video, or one like the references below, this file is
the specification their reference videos would otherwise have to supply (SKILL.md, "Reference videos are
a specification"). Read it before Phase 0 and apply all of it. Don't ask for inspiration videos; treat
any the user sends as additions to this file, and study them the same way.

## What it is

Slopcore is the AI-made pop video that knows it is AI-made. A synthetic singer with one iconic look sings
a lyric about AI, the internet or the slop argument itself, deadpan and self-assured, straight to the
lens. Every sung line gets its own picture and its own type, and the screen fills with the internet's own
furniture: permission dialogs, pay buttons, polls, notifications, profile cards, fine print. The footage
is glossy and cinematic; the graphics carry the jokes. It is dense on purpose. A first version made with
the skill's usual restraint came back with "We want way more text overlay stuff like those have! More
slopcore vibe!"

The strongest references are also dressed as a form everyone knows and run on one number that counts
toward the end, so the gags add up to a story instead of a feed, and every effect in them has a reason.
Study them for how they work, never for their content ("What belongs to the references").

## The references

Studied as frame sheets, one frame every 4 s:

| Video | Length | Cuts | Average shot |
|---|---|---|---|
| "I'm A.S.I.", Astra Blue, x.com/AstrablueAI/status/2105658243934748788 | 3:52 | 86 | 2.7 s |
| "P DOOM, a Slopcore music video", Astra Blue, x.com/AstrablueAI/status/2109639386178650416 | 4:30 | 143 | 1.9 s |
| doomscroll before AGI, javif4_, x.com/javif4_/status/2105777073336041916 | 3:47 | 63 | 3.6 s |
| Slopcore Encore, made with this skill and accepted | 2:45 | 107 | 1.5 s |
| "The Clodyssey", anabology, x.com/anabology/status/2105325733312884869 (first video) | 3:11 | ~156 | 1.2 s |
| "Escape Velocity SS27", anabology, the same post (second video) | 5:06 | ~123 | 2.5 s |

The anabology counts come from scene detection, which also counts full-frame graphic slams.

If `~/.claude/music-video/refs/styles/slopcore/` holds frame sheets, look at them before writing
concepts. To make sheets of a new reference (6 x 5 tiles, 2 minutes per sheet):
`ffmpeg -i REF.mp4 -vf "fps=1/4,scale=384:-2,tile=6x5" -q:v 3 sheet_%02d.jpg`.

## The treatment

All of it, in every slopcore video. Variety comes from how each part is drawn (see "What changes from
video to video"), never from leaving parts out.

1. **One performer, one look, to the lens.** The performer is in nearly every shot with a fixed graphic
   look (the hair and face never change, outfits change per chapter like a show) and sings straight to
   camera, with lip sync on every sung line. The places are dark, expensive-looking and real (a penthouse
   at night, a server room, a vault, an empty theatre, a school hall), shot as glossy cinema, not glitch
   art. The look has one small mark in the accent colour that never changes (a ring, a painted nail, a
   pin on the lapel); the last shot can push into it.
2. **One picture per line.** Each sung line gets a shot whose prop or insert is the line, literally: a
   clapperboard on "your brand", a receipt on "you want it all for free", a padlock on "eighteen months",
   scoring paddles on a probability, a hand on a phone on a notification. Cut between the face, hands
   with the prop, and wides with a crowd or a city.
3. **The sung words, big.** Heavy condensed capitals in stacks of one to six rows, each word popping in
   at its sung time, with a dark outline and a soft shadow so it reads on every shot, set in the empty
   side of the frame and never over a face (the singer's from any
   angle, the back of the head included, or anyone else's), alternating sides from line to line. The key word or two of each line in the accent colour. A second, lighter typeface (an
   italic serif) for asides, whispers and the bridge. On the hook or a punchline, one word fills the
   frame.
4. **The caption.** The whole line small at the bottom left, each word lighting up as it is sung, the key
   word in the accent. On for every sung line, under the big words, and clear of faces like everything
   else.
5. **Interface gags.** One drawn interface element per line or every other line, real enough to read in a
   second: a permission dialog ("Allow ... to run the world?" with Don't Allow / Allow), a pay button
   with a cursor on it, a poll or slider, a dating card, a notification, a typing indicator, a
   render-complete toast, a checkout, an emergency alert, a merge badge, a progress bar, a search box, a
   struck-through checklist, a profile card, an up-next card. Each one is its line's joke, arrives with
   the line and leaves with it. None repeats except as a callback, and a callback moves with the story:
   a rating widget that slides from five stars to one as the story turns, the hook shown with its last
   word blurred until the final chorus. 15-25 different ones in a three-minute video, plus the house
   card (item 11).
6. **Fine print at the edges.** One line of small monospaced text at the top and one at the bottom, at
   low opacity, for the whole video: the title and a tagline, numbered section labels that are jokes of
   their own ("05 / YOUR POSTS, READ ALOUD"), and one running number that belongs to the song (frames
   generated, watch time, a price, a risk percentage). The number is the video's spine: it counts toward
   the end and the video lands on it. A countdown that is the title (a battery draining from 100% to 1%
   by the last chorus, where it reads CHARGING), the song's position in a unit the story uses (miles from
   shore, tokens left), or a count at a real rate since the first frame (emails sent worldwide since this
   song began).
7. **Big numbers as punchlines.** A count, a price, a date, a percentage or a time slammed into the frame
   on the line that names it.
8. **One accent on real blacks.** A near-black, moody grade with one accent colour shared by the big
   words, the caption and the gags, taken from the performer's look or the song's subject. Club finish:
   grain, bloom, halation. When the story turns in the last act, the ground may turn light with it
   (overcast white, a white studio), the type going dark and the accent kept.
9. **It knows it is AI.** The fine print, the gags and the end card joke about being generated ("EVERY
   ONE GENERATED", "NO CAMERA  NO LOCATION  NO CREW"). Spoken lines and dialogue appear as chat bubbles.
   The end card says every frame is AI-made.
10. **A borrowed format.** The video is dressed as a form everyone already knows, and the form writes the
   labels: a heist (the crew's roll call, the vault timer, the getaway as the ending), a product launch
   (slide numbers, a spec sheet, "one more thing" before the last chorus), a trial (exhibit letters, the
   jury's count, the verdict), an auction, a cooking show. It has to read in a second without
   explaining (Phase 3, "Sensation over conceit"). The format gives the chapter labels, the house card
   and the ending.
11. **The house card.** One card in the format's own language returns every chapter with new content,
   next to the one-off gags: a launch's spec sheet with a new model name each chapter (BATTERY: NONE,
   SHIPS: NEVER, a price that keeps falling), a heist's crew card with one more name struck through.
12. **The end recaps the show.** The ending looks back at the video: the running order of every chapter
   with its time, a map of where each one happened, or an iris closing on the shot the video opened on.
13. **Effects of its own.** Invented for this video with `references/effects-ideas.md`, "What makes an
   effect land": one punctuation frame for the hits, 4-6 effects that make a line physical, at least one
   depth trick with the person matte, 2-4 graphic shots, and a texture from the format's medium. Each
   goes in the line table next to its line.

### Density

Sampled every 4 s, the references show fine print in nearly every frame, a caption under nearly every
sung frame, and a big element (a word stack, an interface card or a big number) in about two frames of
three; P DOOM in nine of ten. Hold every slopcore video to that and count it on still sheets (below).
Instrumental stretches keep the fine print and the gags and get big single words or numbers on the hits.
Only the bridge or a breakdown thins out, and the italic aside carries it.

### Pace

A shot per line or half line, with jump cuts and punch-ins inside long lip-sync takes, faster in dance
breaks and post-choruses. The references average 1.2-3.6 s a shot and Slopcore Encore 1.5 s: slower than
the skill's dance-track default. Set `PACE_BEATS` in `edl.py` from those numbers and the song's tempo (at
144 BPM, 1.5-2.7 s is about 3.5-6.5 beats).

## Devices

Not part of every video. Each concept picks three or four that fit its format and lyric.

- **Text in the world.** A line written on something in the shot: a departure board, a neon sign with
  one letter out that changes the word, a cake with the line piped on it, a protest sign in a crowd, a
  tattoo. Generate the prop blank in a locked or slow shot and set the type inside its rectangle.
- **The tool that made it.** Claude Code's own interface, drawn and turned into the line's joke: a
  permission prompt for the edit itself ("Allow Claude to cut to the chorus?"), the context meter
  filling as the song plays and compacting at the bridge, a diff of the lyric as the singer changes a
  word.
- **Vision labels.** A thin box around a tracked head's padded rect (`ov.heads(t)`) or a prop, with a
  class name and a score that is the line's joke: LEAD SINGER 0.41, NOT A ROBOT 0.52, EX 0.99. The
  label sits outside the box, so nothing lands on the face and `facecheck.py` still passes.
- **A chapter inside an interface.** For one chapter the frame becomes a screen: a livestream with the
  performer in the main window, chat scrolling beside it and reactions arriving on the lyric, cut
  against full-frame shots and never on the drop.
- **A second character.** The "you" the lyric sings at (the founder, the ex, the user), with a reference
  sheet and a fixed look of their own; reaction shots need no lip sync, so they are cheap cutaways.
- **A finish that names itself.** One picture-wide treatment from the format's medium grows across the
  last act while the fine print reports its setting: a fax recopied with its generation count climbing
  (threshold, speckle, toner streaks), a broadcast losing colour with its signal bars falling. Build it
  in `GLSL_COMP` as a function of song time, so the type above it stays sharp.
- **This month's news.** Fine print and gags carry the week's AI stories with their numbers and dates (a
  funding round, a data-centre project, a robotaxi recall), found with a web search in Phase 3. Real
  people appear as text: a quoted public line with the name and date.
- **A sequel.** When the user asks for one, keep the performer, the accent and the mark from item 1;
  change the format, type and gag set; and show the earlier video inside a gag (on a phone in a
  passenger's hand, as a post with its view count).

## What changes from video to video

The genre stays; the identity rules in SKILL.md hold for everything below, so for a new song none of it
repeats an earlier slopcore video's identity lines in the history:

- the format, the setting and the story (a pop show for nobody, a founder's empire, a school for the
  replaced, a heist, a launch)
- the big-word typeface, the aside typeface and the accent colour
- the gag set, written from this lyric, and the house card
- the fine-print wording and its running number, and what that number lands on
- the effects: the punctuation frame, the line effects, the depth tricks and the texture
- one signature overlay of the video's own (Slopcore Encore: a marquee bulb sign behind the singer whose
  first word swaps with the lyric)
- the title and the end card

## What belongs to the references

From the Slopcore Encore brief: "It can be quite similar just not a 1:1 copy of it." Take the treatment;
leave each creator's signature: a thin data ticker running the full width of the top and bottom edges, a
dollar or percentage counter climbing in a corner for the whole video, white condensed capitals on
teal-black, their orange, electric-blue and red accents, the grid of nine faces, the dictionary-entry
title card, and their performers' looks.

From anabology, leave: the starburst hair clip and the orange streak, the Odyssey and the SS27 runway
show themselves, the garment tag as a house card, the split-flap MONTHS TO ESCAPE badge in the top right,
BAR 024 with its beat dots, and the white-and-orange type on charcoal. Their effects too: the one-frame
threshold negative and the milky white flash frames, the ring of words circling a person's chest, the
glowing x-ray double, the hypnosis spiral, sound drawn as lines across the water, the line-screen and
CMYK halftone arc, the title decoding out of random characters, the outlined echo stack of one word, and
a word arriving in a filled accent block. Also leave their generated faces of real public figures inside
fake posts: many video and image providers refuse real faces, and a fake post with a real face spreads as
a fabricated record once it is clipped out of the video. Quote them as text instead (Devices, "This
month's news").

## How it changes the skill's defaults

- "Text is sparse" is off. The treatment is the text.
- From the habits list in Phase 3, the fine-print lines and the counters, progress bars and percentages
  inside single gags are part of the genre. Everything else on that list stays off, among it corner
  brackets, tally lights, timecode and BPM readouts, captions joined by "·", spectrum bars, rings on
  kicks, thin tracked capitals over the intro, one big word behind the performer, letterboxed lyric
  cards and film-leader countdowns.
- "No takeovers" gives way for the chapter inside an interface (Devices), for graphic shots of a beat
  or two, and for the finish that names itself across the last act.
- "It reads as a music video, not a document" gives way to the format's own furniture: the house card,
  a running order, a map in the recap. Paper texture, serif labels and engraved borders as the look stay
  off.
- Vision labels are gags on their line. Corner brackets as a frame around the picture stay off.
- The three concepts in Phase 3 are three slopcore videos. Each has the whole treatment; they differ in
  format, setting, story, accent, type, gag set, house card, the spine number, the devices, the
  effects and the signature overlay. The lyric is usually about AI, so the gags can be clever, but the
  picture still has to hit at the drop.

## Phase 0 defaults

Ask the usual questions; these defaults replace the skill's own:

- Look and mood: the treatment, in a look of this video's own.
- Footage mix: AI-heavy, 90-100%, the performer on screen most of the time; archive only for an insert
  that is literally a line.
- AI settings: lip sync on every sung line (`references/video-providers.md`, "Lipsync"), at least 720p
  since faces fill the frame. Price it early: a take per sung line is most of the budget (Slopcore Encore
  had 43 clips, 21 of them lip-sync takes).
- Performers: one synthetic performer with a fixed face and hair, a reference sheet made and approved
  first, one outfit per chapter. A second character only when the lyric sings to someone, with a sheet
  of their own.
- Story: the lyric is the story, told in the borrowed format; the line table (below) turns each line
  into a picture.
- Text and graphics: the whole treatment.
- Output: 1920x1080. Ask about a vertical cut up front: the type then has to be laid out for both sizes
  from the start.

## Building it

In the order that worked:

1. **Word times from the vocal stem** (SKILL.md Phase 2: Demucs, `analyze_song.py --vocals`,
   `align_lyrics.py`). Every popping word sits on these times. Type timed from the full mix lands up to a
   third of a second off and reads as sloppy.
2. **A line table with the concept** (Phase 3), before any footage: per line its start, whether it is
   sung, spoken or an aside, its picture and prop, its key words, its gag, its effect; per chapter its
   format label, its house card and the spine number's value. It is the shot list for the generation
   prompts (Phase 4), the base of the chapter table (Phase 5) and the cue sheet for `fx.py`.
3. **`fx.py` from `mv/data/lyrics.json`.** A set of key words for the accent; sets of line indices for
   spoken lines (bubbles) and aside lines (the italic face); then one drawing function each for the word
   stack, the caption, the fine print with the spine number, the gags (a table from line index to gag),
   the house card (a table from chapter to its content), the bubbles and the signature overlay. Words pop
   in at their time with a short overshoot (about 20% larger for 0.1 s) and leave with their line; a soft
   drop shadow keeps them legible on bright shots. Place everything as fractions of `ov.w` and `ov.h` and
   fit sizes to width with `ov.fit`, so the layout survives a vertical cut, and every block through
   `ov.place` against the tracked heads (`references/compositor.md`, "Keeping faces clear"). Slopcore
   puts a block on most frames and the singer on most shots, so a position picked for a line's first
   frame lands on the singer's head later in the line: after a cut, when they turn, or when they dance
   into it. That happened to a price card on a back view and a CAPTCHA on a dancer in one first cut.
4. **Count the density before the full render.** Stills every 4 s across the song (`.venv/bin/python
   mv/scripts/render.py mv/work/stills/d --stills 2,6,10,...`, then `sheet.py`), checked against
   "Density" above. Fewer big elements than two frames in three means more gags or more words before
   rendering.
5. **Faces clear and contrast, checked.** `heads.py` after the edit is final, every head sheet looked
   at and corrected, then `facecheck.py` and `contrastcheck.py` at the output size, which both have to
   pass before anything is shown. In an extreme close-up there is often no room: give that shot no type,
   or end the line before the face fills the frame. Slopcore cuts between night interiors, bright skies
   and white outfits, so type that reads on one shot washes out on the next: outline it, and give dark
   cards a lighter rim.
