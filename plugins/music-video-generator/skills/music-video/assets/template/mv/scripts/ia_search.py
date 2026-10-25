"""Search archive.org for movie items and print rights-relevant fields.

Usage: .venv/bin/python mv/scripts/ia_search.py "QUERY" [ROWS]
Appends hits to mv/data/ia_hits.json keyed by identifier.
"""
import json
import sys
from pathlib import Path

import internetarchive as ia

HITS = Path("mv/data/ia_hits.json")
FIELDS = ["identifier", "title", "year", "date", "collection", "licenseurl", "rights",
          "downloads", "runtime", "description"]


def main():
    query, rows = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40
    s = ia.get_session()
    hits = json.loads(HITS.read_text()) if HITS.exists() else {}
    res = s.search_items(f"({query}) AND mediatype:movies", fields=FIELDS,
                         params={"rows": rows}, max_retries=3)
    n = 0
    for r in res:
        n += 1
        if n > rows:
            break
        col = r.get("collection", [])
        col = col if isinstance(col, list) else [col]
        desc = r.get("description", "")
        desc = (desc[0] if isinstance(desc, list) else desc or "")[:140].replace("\n", " ")
        hits[r["identifier"]] = {k: r.get(k) for k in FIELDS}
        print(f"{r['identifier'][:48]:48} | {str(r.get('year') or r.get('date',''))[:10]:10} | "
              f"{r.get('downloads',0):>7} | {','.join(col)[:40]:40} | "
              f"{(r.get('licenseurl') or '')[-28:]:28} | {str(r.get('title'))[:60]}")
    HITS.write_text(json.dumps(hits, indent=1))


if __name__ == "__main__":
    main()
