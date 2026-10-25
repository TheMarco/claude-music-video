# Videos made with the music-video skill

Newest first. Phase 7 adds an entry when the user accepts a video. Phase 5 reads it.

What this file protects is each video's identity: the lines "type", "graphics" and "signature". A video
for a different song does not reuse those unless the user asks. The "brief", "look" and "edit" lines are
for reference only: deep blacks, film grain, glow on the kick and fast cutting are craft, and they recur
whenever a brief and a song call for them. A new version of the same song keeps its brief's look; change
only what the user objected to. `scripts/concept_dice.py` reads the identity lines of the last three
entries.

### Rejected directions

(Directions the user rejected outright, with their reasons, so later concepts steer clear.)

<!-- Entry format, newest at the top:

## Title (Artist), Month Year
Project: path, BPM and genre, footage mix. Frames: refs/<title>.jpg
- brief: the user's mood and look words
- look: palette, grade, finish
- edit: cut count, pace, devices
- type: title, artist and word treatments, fonts
- graphics: overlays and graphic elements
- signature: the effects that made this video recognizable
-->
