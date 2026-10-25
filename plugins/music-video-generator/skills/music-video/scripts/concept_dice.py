#!/usr/bin/env python3
"""Random sparks for a video's signature overlays, to get past this skill's usual graphics.

Usage: python3 "$SKILL/scripts/concept_dice.py" [--n 3] [--seed N]   ($SKILL = this skill's folder)

Optional. The brief and the song decide the base look (mood, palette, finish, edit pace), and the
footage stays graded footage, full frame. The dice only suggest what goes on top of it: an overlay
element, an accent for the drops (a beat or two at most), a color move in the grade, how type behaves,
how cuts are marked, what the music drives, plus a wildcard rule. Use what serves the brief and the
song, drop the rest. Entries whose key (the words before the colon) appear in the identity lines of the
last three entries in ~/.claude/music-video/history.md are skipped (the file is created from
assets/history_template.md if missing; MUSIC_VIDEO_HOME moves it), and the draws don't share entries.
No dependencies; any Python 3 works.
"""
import argparse
import os
import random
import re
import shutil
from pathlib import Path

HOME = Path(os.environ.get("MUSIC_VIDEO_HOME", "~/.claude/music-video")).expanduser()
HISTORY = HOME / "history.md"
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "history_template.md"

DECKS = {
    "overlay": [  # the signature element drawn over the footage; it covers part of the frame
        "particles: one material from the lyrics or theme drifting over the footage (ash, embers, snow)",
        "sparks: sparks thrown across the frame on the snares",
        "symbol: one small mark or shape that returns at key moments, changed each time",
        "light leaks: warm leaks drifting across on phrase starts",
        "flares: lens flares anchored to bright sources, flaring on hits",
        "beams: shafts of light sweeping over the frame through the builds",
        "smoke: haze drifting through the lower third, lit by the kick",
        "cracks: thin cracks spreading from a corner on hits, gone by the next bar",
        "shadow pass: a soft shadow sweeping over the frame before the drop",
        "water: drops running down the lens in the breakdown",
        "outline: a thin glowing line traced around the person (matte)",
        "halo: a soft glow behind the person (matte), swelling with the voice",
        "streaks: thin light streaks racing across on the hi-hats",
        "dust motes: specks lit in the light, drifting slowly in the calm parts",
    ],
    "accent": [  # a picture-wide hit for a beat or two on drops and big accents, never longer
        "flash frame: one bright frame on the drop",
        "rgb split: the color channels tear apart for a beat",
        "negative: one beat inverted on the drop",
        "zoom blur: a radial blur thrown on the hit",
        "strobe: exposure strobes for the last bar into the drop",
        "freeze: the picture holds for a beat on the downbeat",
        "burn: a light-leak burn across the cut into the drop",
        "glitch: block displacement for two frames on the hit",
        "stutter: half a beat repeated before the drop",
        "smash to black: a beat of black before the drop",
    ],
    "color": [  # moves inside the grade; the footage stays readable
        "drop color: one hue arrives only from the drop on",
        "hue walk: the grade shifts section by section",
        "kick tint: a slight color push on each kick",
        "split tone: cool shadows, hot highlights",
        "one hue: the grade mutes everything except one color",
        "hot blacks: shadows tinted deep red or violet",
        "warm to cold: the grade cools across the song",
    ],
    "type": [  # how words behave, if there are any
        "no text: nothing until the final title",
        "one word: a single huge word cut in on the snare",
        "light letters: words made of light that burn out",
        "letter windows: the title plays footage inside its letters",
        "stencil spray: letters sprayed on with overspray and drips",
        "shatter: words break apart on the drop",
        "one line: a single lyric repeated and transformed",
        "vertical: words stacked down one edge",
        "font swap: a word that strobes between faces on the hats",
        "scratched: letters scratched into the film",
    ],
    "transition": [  # how cuts are marked
        "whip pans: motion-blurred whips between shots",
        "strobe cuts: 1-2 frame flashes of other shots",
        "zoom through: each cut flies through the last shot",
        "match cuts: by shape or color",
        "ramps: speed ramps into the drops",
        "reverse snap: a shot snaps backwards before the cut",
        "leak dissolves: dissolves that pass through a light leak",
        "dip to white: short white dips on phrase starts",
    ],
    "reaction": [  # what the music drives
        "kick zoom: framing punches on the kick",
        "hat sparkle: the overlay sparkles on the hi-hats",
        "vocal glow: the voice lights the overlay",
        "held back: little reacts until the drop, then everything",
        "snare cuts: the snare drives the edit",
        "loudness exposure: exposure breathes with the loudness",
        "bass glow: glow swells with the low end",
    ],
    "wildcard": [
        "the performer or subject is never fully seen until the last chorus",
        "the title appears only at the very end",
        "use no more than three source films",
        "the video gets older as the song goes (clean to damaged)",
        "a single prop or symbol travels through every shot",
        "one section goes almost black",
        "every shot before the drop is a close-up",
        "the camera always moves forward",
        "the drop opens on the single best shot in the footage, held for a full bar",
    ],
}


def recent_text(n=3):
    """The identity lines (type, graphics, signature) of the last n history entries."""
    if not HISTORY.exists():
        return ""
    entries = re.split(r"^## ", HISTORY.read_text(), flags=re.M)[1:]
    lines = [ln for e in entries[:n] for ln in e.splitlines() if re.match(r"- (type|graphics|signature):", ln)]
    return "\n".join(lines).lower()


def key(entry):
    return entry.split(":")[0].lower().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed", type=int)
    args = ap.parse_args()
    if not HISTORY.exists() and TEMPLATE.exists():
        HOME.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATE, HISTORY)
    rng = random.Random(args.seed)
    seen = recent_text()
    print("Last videos (their signature, graphics, type and title are not reused for a different song):")
    if HISTORY.exists():
        for e in re.split(r"^## ", HISTORY.read_text(), flags=re.M)[1:4]:
            print("  " + e.splitlines()[0])
    print()
    used = {axis: set() for axis in DECKS}
    for i in range(args.n):
        print(f"Draw {chr(65 + i)}")
        for axis, deck in DECKS.items():
            pool = [e for e in deck if not re.search(r"\b" + re.escape(key(e)) + r"\b", seen) and e not in used[axis]] or deck
            pick = rng.choice(pool)
            used[axis].add(pick)
            print(f"  {axis:10s} {pick}")
        print()


if __name__ == "__main__":
    main()
