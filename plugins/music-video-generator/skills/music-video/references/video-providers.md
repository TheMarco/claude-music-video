# Video-generation providers (any MCP)

AI clips come from whatever video-generation MCP server the user has connected: Hedra, a Runway, Luma,
Kling, Replicate or fal server, or anything else that renders video. The skill never handles provider
API keys or accounts; it works only through the tools the connected MCP exposes, signed in however
that MCP signs in. If no video MCP is connected, the video is archive-only.

## Find out what the provider can do

Find the tools with ToolSearch ("video", "generate", "image", "upload", "asset", the provider's name).
Read each tool's description and, where the MCP offers one, its model list or model details tool. Note
for each candidate model:

- inputs: text only, a start frame (image to video), reference images for identity, reference video
  or audio, and whether start frame and references can be combined
- durations, resolutions and aspect ratios; whether generated audio can be turned off
- price per second or per clip, and the tools for balance and estimates
- how jobs report progress, how outputs come back (a URL, an asset id), and how long URLs stay valid
- content rules that block prompts

Prefer the provider's own numbers over anything written here.

## Getting local files to the provider

Reference photos and keyframes usually live on the user's disk. Try these in order:

1. An MCP tool that uploads a local file directly.
2. A file picker the MCP shows in hosts that support it.
3. The user uploads the files to the provider's own library or web app (the MCP often links to it),
   and you find them with the MCP's asset or library search tool.
4. A public URL the user already hosts the file at, passed to a tool that accepts URLs.

Don't ask for API keys, and don't write upload scripts that need one; if none of these routes exist,
say so and ask the user how they want to provide the files.

## Getting outputs back

Download each finished clip from the URL the provider returns with
`python3 -I mv/scripts/fetch_clip.py mv/clips/<CODE>.mp4 URL` (stills to `mv/keyframes/`). Presigned
URLs are long and break when retyped: write the URL to a file exactly as returned and pass `@file`.
Download soon after a job finishes, since presigned URLs expire. If the MCP has its own download or
export tool that writes local files, that works too.

## Jobs, money and errors

- Generation is usually asynchronous. Poll the status tool at the interval it asks for, and wait in
  the background between checks rather than polling in a tight loop. Never resubmit a job just to check
  on it; reuse an idempotency key if the provider has one.
- Record job ids in `mv/data/` as you submit, so a lost context can recover them.
- Failed jobs are usually free; completed takes you reject still cost. Record both in the budget ledger
  (`budget.py add`).
- Prompts with sensual wording in close-ups get blocked by some providers. Rephrase plainly and keep
  the same references.
- Validation errors usually list the allowed values; fix and resubmit.

## Method that carries over between providers

- **Real person from a photo:** identity has to come from the actual photo through the model's
  reference-image mode (the full portrait plus a tight face crop, optionally a scene or outfit still).
  Animating a generated keyframe of a real person tends to produce a different face, and image models
  drift faces toward a generic look. One test clip first; the user judges the face.
- **Masked or invented character:** generate a keyframe still (cheap), check it, then animate from it
  as the start frame. Say in the prompt that the mask stays exactly the same and no face is shown.
- **Inventory the angles before generating more.** Make a contact sheet of the performer clips you
  already have (`contact.py`) and list each one's angle and size. Spend credits on the angles that are
  missing (profile, from behind, overhead, low, wide) rather than another frontal close-up: a video cut
  from one angle feels monolithic however good each clip is.
- **Prompt pattern for a person from references:**
  > The person is the one in [image 1] and [image 2]: their face, face shape, eyes, nose, lips, skin and
  > hair must match those photos exactly in every frame. [Image 3] shows the scene, framing, lighting and
  > outfit. [What they do, where]. [Camera angle, e.g. low angle from the side, or from behind], [shot
  > size, e.g. medium-wide from the knees up], [camera move]. [Light and atmosphere]. [Film or video look].

  Name the angle and the move explicitly; left out, the model defaults to a frontal medium shot. Say
  "face toward the camera" only when the shot needs the face.
- **Don't build a story beat on a prompt's last action.** Models often drop the final action of a
  clip ("in the last seconds the car pulls away" can simply not happen). Give a payoff its own
  shot, or cut the story so it works without it.
- Turn generated audio off; the song replaces it. Ask for the resolution the user chose (480p saves
  credits; the compositor upscales).

## Lipsync (performance shots)

Only when the user asks for it. Two routes exist on most providers:

- **A video model that takes reference audio.** Pass the singer's photos as references and a black video
  carrying the exact slice of the song as reference video, with generated audio on and a prompt that
  says to use that audio. Make the slice with
  `ffmpeg -f lavfi -i color=black:s=854x480:r=24 -ss START -t DUR -i song.mp3 -shortest -c:v libx264 -c:a aac slice.mp4`
  and get it to the provider like any other local file.
- **Avatar or talking-photo models:** a portrait plus an audio file, often minutes long and cheap per
  second. Good for whole verses on one setup; less camera movement.

Mouths follow the clip's own audio, which is not always exactly where you asked. For each lipsync clip
run `.venv/bin/python mv/scripts/sync_offset.py mv/clips/L1.mp4 --save` to find the song time where its
audio starts and record it in `mv/data/mouths.json`, then place it with `S("L1", 0, beats, sync=<that
time>)`; the EDL computes the in-point. Windows that disagree in the sync report mean drift there:
start that cut later or nudge `sync` per cut.

**A singing take is shown only at the song time it was recorded for.** Repeated lines are rarely
phrased the same: a chorus take reused on a later chorus or a drop line looks wrong on screen even when
the words repeat. Any other shot of the singer needs the mouth closed or out of view (from behind, a
silhouette, tiny in frame). So:

- Budget one take per line that is sung on screen. Drops and instrumental stretches get dancing or
  performance shots with no singing; slices dominated by a drop (loud kick, little vocal) tend not to
  sync at all.
- Check the stretches between lines. Generated takes don't reliably close the mouth when the vocal
  stops, and the user's own performer footage can contain talking or singing. `mouth_check.py` tiles
  mouth crops over time (`mouth_check.py mv/work/mouths.jpg L1:0-10 P3:4-12`); record each clip's
  closed or hidden stretches as `"safe"` ranges in clip seconds in `mv/data/mouths.json`:
  `{"L1": {"sync": 62.48, "safe": [[8.5, 10.0]]}, "P3": {"safe": [[0, 3.2]]}}`.
- `edl.py` warns about every shot of a clip in `mouths.json` that is neither shown at its recorded sync
  nor inside a safe range. `vocal_match.py` compares the separated vocal where a take was recorded with
  where it plays, as a second check, or (`--pair`) before you assume two lines match.

## Example: Hedra

Notes from using Hedra's MCP (`mcp__hedra__*`) in October 2026; check `list_models` and `get_model`
for current models and prices. It bills a workspace credit pool (`get_balance`, `estimate`).

| Use | Model | Mode | Cost at 480p |
|---|---|---|---|
| Real person from a photo | `seedance-25` (Seedance 2.5) | reference images (up to 30), no start frame | about 20.8 credits/s; durations 4-30 s |
| Masked or invented character | `seedance-20` (Seedance 2.0) | start frame (`start_keyframe_id`) | 22.5 credits/s standard, 18 fast; durations 4-15 s |
| Scene or outfit still | `nano-banana-pro` | references, needs `resolution` "1K"/"2K"/"4K" | 15 credits at 2K |
| Keyframe of a masked character | `gpt-image-2` | references | 8-11 credits |

- Both Seedance models reject a start frame combined with reference images, so a real person goes
  through reference mode.
- Lipsync: Seedance 2.5 accepts reference video with audio (up to 30 s; 15 s for 2.0); avatar models
  include `hedra-character-3`, `omnihuman-20` and `kling-ai-avatar-v2`. Seedance doesn't reliably close
  the mouth between sung lines: of three takes with a 3.5 s instrumental gap, one kept mouthing through
  it. A slice dominated by a drop came back with the model's own audio and a mouth that matched nothing,
  while vocal-led slices synced exactly. Check every take with `sync_offset.py` and `mouth_check.py`.
- Seedance 2.5 can skip the last action in a prompt; keep story payoffs in their own shot.
- Local files: `upload_file` takes a public URL only. `show_file_upload_widget` shows a picker in hosts
  that support it; in a terminal it returns a link to the Hedra library, where the user uploads the
  files, and `query_assets` then finds them.
- Outputs: `get_generations` returns presigned URLs of about 1,700 characters; download them with
  `fetch_clip.py` and `@file`. Up to 4 jobs per status call; a 10-15 s Seedance clip takes about 3-8
  minutes; keep at most 20 jobs in flight.
