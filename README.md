# Music Video Generator

A Claude Code skill that makes complete music videos from a song. You give it the track and a few words
about the mood; it analyzes the song's beat grid and sections, finds footage on archive.org or uses your
own clips and photos, optionally generates performer clips through any video-generation MCP you connect,
cuts everything to the beat, and renders a finished video with the original audio in 16:9,
9:16 or square.

The picture is always your graded footage, full frame. Each video gets its own overlays, type and title,
designed for that song inside your brief, and a history file keeps later videos from repeating earlier
ones.

## Requirements

- Claude Code
- Python 3.10-3.13 and ffmpeg on the PATH
- A GPU with OpenGL 3.3 (the compositor uses moderngl)
- Optional: any video-generation MCP server (Hedra, Runway, Luma, Kling, Replicate, fal or others) if
  you want AI-generated performer clips, plus credits with that provider. The plugin works only through the tools
  of the MCP you have connected. Archive-only videos need no provider and cost nothing.

It runs in Claude Code on your own computer. In claude.ai chat or Cowork the skill can load but can't
render, since those have no local Python, ffmpeg or GPU.

Developed and tested on macOS with Apple Silicon. Linux and Windows have fallbacks for fonts, lyrics
transcription and headless OpenGL, but are untested. Head tracking (which keeps every overlay off every
face) uses Apple's Vision framework on macOS, through a small Swift helper compiled with `swiftc` from
the Xcode command line tools; elsewhere it falls back to OpenCV face detection, which misses heads seen
from behind, so the review sheets need a closer look there.

## Install

As a plugin:

```
claude plugin marketplace add TheMarco/claude-music-video
claude plugin install music-video-generator@music-video
```

Or copy `plugins/music-video-generator/skills/music-video/` to `~/.claude/skills/music-video/`.

The plugin itself holds only Markdown, JSON and its icon. The pipeline's Python scripts (the engine)
are in this repository's `engine/` folder, and you install them yourself, once per engine version (next
section). The skill copies them into each project from there.

### Install the engine

The skill is pinned to one engine commit (`ENGINE_REV` in `SKILL.md`) and looks for it in
`~/.claude/music-video/engine/<commit>/`. When it isn't there, the skill stops and sends you here. The
current version is `ade7169`:

```
ENGINE_REV=ade71698060a6e0c6cd829e567231df5be5e4dca
DEST="$HOME/.claude/music-video/engine/$ENGINE_REV"
mkdir -p "$DEST" &&
curl -fsSL "https://codeload.github.com/TheMarco/claude-music-video/tar.gz/$ENGINE_REV" |
  tar -xz -C "$DEST" --strip-components=2 "claude-music-video-$ENGINE_REV/engine" &&
ls "$DEST/template/mv/scripts/render.py"
```

This unpacks only the repository's `engine/` folder at that commit; nothing runs during the install, and
every file is plain Python you can read first. With git instead:

```
git clone https://github.com/TheMarco/claude-music-video.git && cd claude-music-video
git checkout ade71698060a6e0c6cd829e567231df5be5e4dca
mkdir -p ~/.claude/music-video/engine/ade71698060a6e0c6cd829e567231df5be5e4dca
cp -R engine/. ~/.claude/music-video/engine/ade71698060a6e0c6cd829e567231df5be5e4dca/
```

After an update of the plugin the skill may ask for a newer engine: run the same steps with the commit
it names. Older engine folders can stay; projects made with them keep working.

## Use

Start Claude Code in an empty folder with your song in it and ask for a music video ("make a music video
for song.mp3, moody and nocturnal, archive footage only"). Installed as a plugin, the skill can also be
run directly as `/music-video-generator:music-video`. It asks its brief questions in one message, waits
for your go before downloading, spending credits or rendering, proposes three concepts, and shows still
frames before the full render.

Named styles carry a genre's whole treatment, so you don't have to send reference videos for it. Ask for
a slopcore video and the skill applies that genre's treatment (`references/styles/slopcore.md`): one
AI performer singing to the lens with lip sync on every line, big words on the sung words, an interface
gag per line and fine print at the edges, in a look of its own. Styles of your own, written in the same
shape, go in `~/.claude/music-video/styles/`.

Each project gets an `mv/` folder with the pipeline scripts, data, clips and renders. Your history of
accepted videos lives in `~/.claude/music-video/`.

## What it runs and where data goes

Everything runs on your machine: Python scripts copied into each project, ffmpeg, and a GPU compositor.
Every request the scripts make is anonymous. Network access:
- github.com: the pipeline scripts, this repository's `engine/` folder at the commit pinned in
  `SKILL.md`, which you download yourself during install ("Install the engine")
- archive.org: searching and downloading public-domain and openly licensed films, anonymously
  (`ia_search.py`, `ia_fetch.py`)
- your video-generation MCP, only through its own tools: prompts, and the reference photos you choose
  to send it; finished clips are downloaded from the URLs it returns (`fetch_clip.py`)
- Python packages from PyPI during setup
- the lyrics, background-removal and depth models on first use, downloaded anonymously and checked
  against pinned checksums (`models.py`): Whisper large-v3-turbo and Depth Anything V2 Small (Apache-2.0,
  for the depth treatments) from huggingface.co into `~/.cache/music-video/models/`, and rembg's person
  model from github.com into rembg's own model folder. Off Apple Silicon, openai-whisper fetches its model from OpenAI's public download server.
- optionally, for lip-sync and word-timed type: Demucs (vocal separation), installed from PyPI when
  you agree to it; it pulls in PyTorch and downloads its own model on first run

Project files stay in the project folder; the history of accepted videos stays in
`~/.claude/music-video/`. Nothing is sent anywhere else.

## Footage rights

You are responsible for the rights to everything in your video. The skill reads license fields on
archive.org items and flags items that have none, and it puts source credits on the end card, but check
anything you plan to release commercially.

## Author

Made by Marco van Hylckama Vlieg: [ai-created.com](https://ai-created.com/), [@AIandDesign](https://x.com/AIandDesign) on X.

## Development

The engine lives in `engine/`. After changing it, run the smoke test with a Python that has
`engine/template/requirements.txt` installed (a project's `.venv/bin/python` works):

```
path/to/.venv/bin/python engine/scripts/smoke_test.py
```

It pushes a synthetic song and test-pattern clips through analysis, the grid check, the edit, stills,
a full render, a vertical hook, QC and the face and contrast checks, and stops at the first step that
fails. Then commit, set `ENGINE_REV` in `plugins/music-video-generator/skills/music-video/SKILL.md` and
in "Install the engine" above to that commit, and raise `version` in `plugin.json`. The plugin itself
never downloads the engine: the skill checks for it and sends users to "Install the engine".

`evals/evals.json` holds test prompts for the skill itself, with what a good run does for each. Run
them after changing `SKILL.md` or the references.
