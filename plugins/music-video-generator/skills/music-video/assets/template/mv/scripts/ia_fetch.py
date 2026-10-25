"""Download the smallest 480p-or-better h.264 MP4 of each archive.org item.

Usage: .venv/bin/python mv/scripts/ia_fetch.py ID [ID ...]
Files land in mv/archive/<id>/; item metadata goes to mv/archive/<id>/meta.json.
"""
import json
import sys
import time
from pathlib import Path

import internetarchive as ia

OUT = Path("mv/archive")


def pick(files):
    mp4 = [f for f in files if f["name"].lower().endswith(".mp4") and "hevc" not in f["name"].lower()]
    good = [f for f in mp4 if int(f.get("height") or 0) >= 360] or mp4
    return min(good, key=lambda f: int(f.get("size") or 1e12)) if good else None


def main():
    s = ia.get_session()
    for ident in sys.argv[1:]:
        item = s.get_item(ident)
        f = pick(item.files)
        if not f:
            print(f"SKIP {ident}: no mp4")
            continue
        dest = OUT / ident
        dest.mkdir(parents=True, exist_ok=True)
        md = item.metadata
        (dest / "meta.json").write_text(json.dumps({
            "identifier": ident, "title": md.get("title"), "date": md.get("date") or md.get("year"),
            "collection": md.get("collection"), "licenseurl": md.get("licenseurl"),
            "rights": md.get("rights"), "file": f["name"],
            "url": f"https://archive.org/details/{ident}"}, indent=1))
        if (dest / f["name"]).exists():
            print(f"have {ident}/{f['name']}")
            continue
        item.download(files=[f["name"]], destdir=str(dest), no_directory=True, retries=5, checksum=True)
        print(f"ok   {ident}/{f['name']} ({int(f.get('size', 0)) // 1_000_000} MB)")
        time.sleep(1)


if __name__ == "__main__":
    main()
