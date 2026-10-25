# Archive and library footage

Any local video or image works as a source: give it a code in `mv/data/codes.json` with a file path
(`"U1": "footage/phone_clip_03.mov"`, `"P1": "photos/artist.jpg"`). Free sources besides archive.org:
- NASA (images.nasa.gov, NASA YouTube originals): public domain, great for cosmic and ambient looks.
- Library of Congress and the U.S. National Archives: public domain government film.
- Wikimedia Commons: check the license on each file; CC-BY needs a credit.
- Pexels and Pixabay: free licenses for modern stock clips; downloads need their sites or API keys.
- The user's own footage, photos and album art.
Avoid British Pathé, Getty and news archives unless the user has a license; uploads of TV shows or films
on any site are not free to use.

# archive.org

## Searching

Use the `internetarchive` library's default session (`ia_search.py`, `ia_fetch.py`). archive.org's
search returns 400 Bad Request when the User-Agent is custom; trying other User-Agents was blocked as
bot-check circumvention, so don't.

```bash
.venv/bin/python mv/scripts/ia_search.py 'title:("new york") AND collection:prelinger' 40
.venv/bin/python mv/scripts/ia_search.py '"amusement park" OR carnival OR "roller coaster"' 25
```
The script adds `AND mediatype:movies`, prints identifier, year, downloads, collections, license and
title, and appends hits to `mv/data/ia_hits.json`. Search `description:` fields too: Prelinger home
movies are titled by number ("Home Movie: 001234") and only the description says what is in them
("city lights at night"). Useful terms: night, neon, marquee, crowd, street, highway, ocean; soundies,
dance, nightclub for performers; place names and decades for the theme.

Good sources:
- `collection:prelinger`: industrial films and home movies, 1920s-1970s, Kodachrome color.
- U.S. government films (National Archives, FedFlix, NASA): industry, highways, cities, space. Public domain.
- `opensource_movies` items with `licenseurl` CC0 or CC-BY.

## Rights

Read each item's `licenseurl` and `rights` (`ia_fetch.py` saves them to `meta.json`). Public-domain
marks and CC0 are clear. U.S. federal works are public domain. Prelinger home movies usually have no
license field; Prelinger invites reuse, but flag them for a check before commercial release. Avoid items
that are uploads of TV, films or YouTube videos. Credit the sources on the end card, which
the video's `fx.py` draws.

## Downloading

```bash
.venv/bin/python mv/scripts/ia_fetch.py ID [ID ...]
```
It picks the smallest h.264 MP4 at 360p or better (the 480p derivatives are fine; the compositor
upscales and grades them), saves it to `mv/archive/<id>/` with `meta.json`. Then give each film a short
code in `mv/data/codes.json`: `{"A1": "SomeIndustrialFilm1955", "B1": "Home_Movie_001234", ...}`. Use
letter prefixes by theme (A for one theme, B for another) so EDL lines read easily. Disk fills fast (a
couple of dozen films can take several GB); check free space first.

## Finding the usable moments

```bash
.venv/bin/python mv/scripts/scan_archive.py
```
Samples every film at 2 fps and writes per-second luma, highlights, colorfulness and motion, then
`mv/data/candidates.json` with "night" runs (dark frames with bright colored highlights: neon, signs,
city lights) and "flash" times (explosions, fireworks, flashbulbs). Build a spec of `[code, seconds]` pairs from
those, or sample a film every N seconds, and look at it:

```bash
.venv/bin/python mv/scripts/contact.py mv/work/sheets/night mv/work/spec_night.json
```
Each sheet holds 30 labeled thumbnails (code and time). Read the sheets and note in-points. For a key
moment such as an explosion, sample every 0.5-1 s around it to find the exact frame where the flash
starts; drops land on that frame.

## Framing

`media.crop_for` detects burned-in black bars with ffmpeg cropdetect (cached in
`mv/data/crops_auto.json`) and center-crops the picture to 16:9. For anything else (a home-movie title
burned in, a wobbly gate, a better reframe) add `"CODE": [x, y, w, h]` (0..1) to `mv/data/crops.json`
after looking at a contact sheet.
