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
transcription and headless OpenGL, but are untested.

## Install

As a plugin:

```
claude plugin marketplace add TheMarco/claude-music-video
claude plugin install music-video-generator@music-video
```

Or copy `plugins/music-video-generator/skills/music-video/` to `~/.claude/skills/music-video/`.

The plugin itself holds only Markdown, JSON and its icon. The pipeline's Python scripts are in this
repository's `engine/` folder; on first use the skill downloads that folder from GitHub, pinned to one
commit (`ENGINE_REV` in `SKILL.md`), into `~/.claude/music-video/engine/<commit>/`, and copies the
scripts into each project from there.

## Use

Start Claude Code in an empty folder with your song in it and ask for a music video ("make a music video
for song.mp3, moody and nocturnal, archive footage only"). Installed as a plugin, the skill can also be
run directly as `/music-video-generator:music-video`. It asks its brief questions in one message, waits
for your go before downloading, spending credits or rendering, proposes three concepts, and shows still
frames before the full render.

Each project gets an `mv/` folder with the pipeline scripts, data, clips and renders. Your history of
accepted videos lives in `~/.claude/music-video/`.

## What it runs and where data goes

Everything runs on your machine: Python scripts copied into each project, ffmpeg, and a GPU compositor.
Every request the scripts make is anonymous. Network access:
- github.com: the pipeline scripts, this repository's `engine/` folder at the commit pinned in
  `SKILL.md`, downloaded once per engine version with `curl` from codeload.github.com
- archive.org: searching and downloading public-domain and openly licensed films, anonymously
  (`ia_search.py`, `ia_fetch.py`)
- your video-generation MCP, only through its own tools: prompts, and the reference photos you choose
  to send it; finished clips are downloaded from the URLs it returns (`fetch_clip.py`)
- Python packages from PyPI during setup
- the lyrics and background-removal models on first use, downloaded anonymously and checked against
  pinned checksums (`models.py`): Whisper large-v3-turbo from huggingface.co into
  `~/.cache/music-video/models/`, and rembg's person model from github.com into rembg's own model
  folder. Off Apple Silicon, openai-whisper fetches its model from OpenAI's public download server.

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
a full render, a vertical hook and QC, and stops at the first step that fails. Then commit, set
`ENGINE_REV` in `plugins/music-video-generator/skills/music-video/SKILL.md` to that commit and raise
`version` in `plugin.json`, so installs download the new engine.

`evals/evals.json` holds test prompts for the skill itself, with what a good run does for each. Run
them after changing `SKILL.md` or the references.
