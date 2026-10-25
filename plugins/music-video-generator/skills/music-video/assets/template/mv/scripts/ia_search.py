"""Search archive.org for movie items and print rights-relevant fields.

Usage: .venv/bin/python mv/scripts/ia_search.py "QUERY" [ROWS]
Appends hits to mv/data/ia_hits.json keyed by identifier. Uses archive.org's public search API
anonymously: no account, no credentials.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HITS = Path("mv/data/ia_hits.json")
FIELDS = ["identifier", "title", "year", "date", "collection", "licenseurl", "rights",
          "downloads", "runtime", "description"]
API = "https://archive.org/advancedsearch.php"


def search(query, rows, retries=3):
    params = [("q", f"({query}) AND mediatype:movies"), ("rows", rows), ("page", 1), ("output", "json")]
    params += [("fl[]", f) for f in FIELDS]
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)["response"]["docs"]
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def main():
    query, rows = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40
    hits = json.loads(HITS.read_text()) if HITS.exists() else {}
    for r in search(query, rows):
        col = r.get("collection", [])
        col = col if isinstance(col, list) else [col]
        hits[r["identifier"]] = {k: r.get(k) for k in FIELDS}
        print(f"{r['identifier'][:48]:48} | {str(r.get('year') or r.get('date',''))[:10]:10} | "
              f"{r.get('downloads',0):>7} | {','.join(col)[:40]:40} | "
              f"{(r.get('licenseurl') or '')[-28:]:28} | {str(r.get('title'))[:60]}")
    HITS.parent.mkdir(parents=True, exist_ok=True)
    HITS.write_text(json.dumps(hits, indent=1))


if __name__ == "__main__":
    main()
