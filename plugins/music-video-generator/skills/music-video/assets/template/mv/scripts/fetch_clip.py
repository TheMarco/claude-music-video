"""Download a finished clip or still from the URL a video-generation MCP returned.

Usage: python3 -I mv/scripts/fetch_clip.py OUT_PATH URL          (run from the project root)
       python3 -I mv/scripts/fetch_clip.py OUT_PATH @URL_FILE    (the URL read from a text file)

Works with any provider whose tools return a downloadable URL (public, or presigned with its signature
in the URL). It sends no credentials and only writes inside mv/, e.g. mv/clips/P1.mp4 or
mv/keyframes/P1.png. Presigned URLs are often 1,000-2,000 characters long and break when retyped: save
the URL to a file exactly as the tool returned it and pass @file. A 403 usually means a damaged or
expired URL; fetch a fresh one from the provider's tools.
"""
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    out, url = Path(sys.argv[1]), sys.argv[2]
    if url.startswith("@"):
        url = Path(url[1:]).read_text().strip()
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        sys.exit("only http(s) URLs")
    root = Path("mv").resolve()
    if root not in out.resolve().parents:
        sys.exit(f"refusing to write outside mv/: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(out)
    print(f"saved {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
