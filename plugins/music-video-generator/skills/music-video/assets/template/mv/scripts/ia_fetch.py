"""Download the smallest 360p-or-better h.264 MP4 of each archive.org item.

Usage: .venv/bin/python mv/scripts/ia_fetch.py ID [ID ...]
Files land in mv/archive/<id>/; item metadata goes to mv/archive/<id>/meta.json. Uses archive.org's
public metadata and download URLs anonymously: no account, no credentials.
"""
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("mv/archive")


def get_json(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def pick(files):
    mp4 = [f for f in files if f["name"].lower().endswith(".mp4") and "hevc" not in f["name"].lower()]
    good = [f for f in mp4 if int(f.get("height") or 0) >= 360] or mp4
    return min(good, key=lambda f: int(f.get("size") or 1e12)) if good else None


def download(url, dest, md5=None, retries=5):
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(retries):
        try:
            h = hashlib.md5()
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
            if md5 and h.hexdigest() != md5:
                raise OSError("checksum mismatch")
            tmp.replace(dest)
            return
        except OSError as e:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1}: {e}")
            time.sleep(2 ** attempt)


def main():
    for ident in sys.argv[1:]:
        item = get_json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}")
        f = pick(item.get("files", []))
        if not f:
            print(f"SKIP {ident}: no mp4")
            continue
        dest = OUT / ident
        dest.mkdir(parents=True, exist_ok=True)
        md = item.get("metadata", {})
        (dest / "meta.json").write_text(json.dumps({
            "identifier": ident, "title": md.get("title"), "date": md.get("date") or md.get("year"),
            "collection": md.get("collection"), "licenseurl": md.get("licenseurl"),
            "rights": md.get("rights"), "file": f["name"],
            "url": f"https://archive.org/details/{ident}"}, indent=1))
        if (dest / f["name"]).exists():
            print(f"have {ident}/{f['name']}")
            continue
        url = f"https://archive.org/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(f['name'])}"
        download(url, dest / f["name"], f.get("md5"))
        print(f"ok   {ident}/{f['name']} ({int(f.get('size', 0)) // 1_000_000} MB)")
        time.sleep(1)


if __name__ == "__main__":
    main()
