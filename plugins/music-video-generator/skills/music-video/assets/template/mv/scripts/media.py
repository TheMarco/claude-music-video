"""Source lookup shared by the EDL builder and the compositor.

A source code is one of:
- an AI clip: mv/clips/<CODE>.mp4 (e.g. P1, Q3)
- an entry in mv/data/codes.json whose value is either an archive.org identifier (downloaded by
  ia_fetch.py into mv/archive/<identifier>/) or a path to any video or image file (the user's own
  footage, stock clips, photos, album art), absolute or relative to the project root
- "BLACK", or a procedural background: GEN_GRID, GEN_PLASMA, GEN_TUNNEL
"""
import json
import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path("mv")
_codes_file = ROOT / "data" / "codes.json"
CODES = json.loads(_codes_file.read_text()) if _codes_file.exists() else {}
_crops_file = ROOT / "data" / "crops.json"
CROPS = json.loads(_crops_file.read_text()) if _crops_file.exists() else {}  # {"A3": [x, y, w, h], ...} in 0..1


GEN_IDS = {"GEN_GRID": 1, "GEN_PLASMA": 2, "GEN_TUNNEL": 3}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpg", ".mpeg")


def is_gen(code):
    return code in GEN_IDS


def is_ai(code):
    return (ROOT / "clips" / f"{code}.mp4").exists()


def src_path(code):
    if is_ai(code):
        return ROOT / "clips" / f"{code}.mp4"
    v = CODES[code]
    if v.lower().endswith(IMAGE_EXT + VIDEO_EXT):
        return Path(v).expanduser()
    d = ROOT / "archive" / v
    return next(p for p in sorted(d.iterdir()) if p.suffix.lower() in VIDEO_EXT)


def is_image(code):
    return code in CODES and CODES[code].lower().endswith(IMAGE_EXT)


def matte_path(code):
    return ROOT / "clips" / f"{code}_matte.mp4"


@lru_cache(maxsize=None)
def probe(code):
    """(duration_s, width, height) of a source."""
    if code == "BLACK" or is_gen(code):
        return 1e9, 1920, 1080
    if is_image(code):
        from PIL import Image
        w, h = Image.open(src_path(code)).size
        return 1e9, w, h
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(src_path(code))],
                         capture_output=True, text=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    return float(j["format"]["duration"]), int(st["width"]), int(st["height"])


def duration(code):
    return probe(code)[0]


_auto_file = ROOT / "data" / "crops_auto.json"


def picture_area(code):
    """Active picture inside burned-in black bars (pillarbox/letterbox), as (x, y, w, h) in 0..1.

    Uses ffmpeg cropdetect on 20 s from the middle of the film; cached in mv/data/crops_auto.json.
    """
    cache = json.loads(_auto_file.read_text()) if _auto_file.exists() else {}
    if code in cache:
        return tuple(cache[code])
    dur, w, h = probe(code)
    out = subprocess.run(["ffmpeg", "-ss", f"{dur * 0.4:.1f}", "-i", str(src_path(code)), "-t", "20",
                          "-vf", "cropdetect=24:2:0", "-f", "null", "-"], capture_output=True, text=True).stderr
    found = Counter(re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", out)).most_common(1)
    area = (0.0, 0.0, 1.0, 1.0)
    if found:
        cw, ch, cx, cy = map(int, found[0][0])
        if cw * ch > 0.3 * w * h:          # ignore near-black frames that fool cropdetect
            area = (cx / w, cy / h, cw / w, ch / h)
    cache[code] = area
    _auto_file.parent.mkdir(parents=True, exist_ok=True)
    _auto_file.write_text(json.dumps(cache, indent=1))
    return area


def crop_for(code):
    """Crop rectangle (x, y, w, h) in 0..1 that turns the source into a clean 16:9 frame.

    Archive films: black bars are detected and removed first, then the picture is center-cropped
    to 16:9. mv/data/crops.json overrides it per code (burned-in intros, a wobbly gate, a reframe),
    after checking a contact sheet.
    """
    if code in CROPS:
        return tuple(CROPS[code])
    if is_ai(code):
        return (0.0, 0.01, 1.0, 0.98)
    _, w, h = probe(code)
    ax, ay, aw, ah = (0.0, 0.0, 1.0, 1.0) if is_image(code) else picture_area(code)
    a = (aw * w) / (ah * h)
    target = 16 / 9
    if a < target:                       # 4:3 and similar: keep full width, crop top and bottom
        hh = ah * a / target
        return (ax, ay + (ah - hh) / 2, aw, hh)
    ww = aw * target / a                 # wider than 16:9: crop the sides
    return (ax + (aw - ww) / 2, ay, ww, ah)
