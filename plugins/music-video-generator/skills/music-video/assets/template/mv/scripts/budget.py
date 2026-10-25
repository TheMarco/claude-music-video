"""Generation budget ledger: what was agreed, what each job cost, what is left.

Usage:
  python3 mv/scripts/budget.py set 3000 [--unit credits]     # the budget the user agreed to
  python3 mv/scripts/budget.py plan LABEL AMOUNT [--note T]   # an estimate, before submitting
  python3 mv/scripts/budget.py add LABEL AMOUNT [--note T]    # actual cost, once the job is done
  python3 mv/scripts/budget.py                                # summary
Stored in mv/data/budget.json. Record every paid generation, including failed and rejected takes,
so the summary matches the provider's balance.
"""
import argparse
import json
import time
from pathlib import Path

F = Path("mv/data/budget.json")
ap = argparse.ArgumentParser()
ap.add_argument("cmd", nargs="?", default="show", choices=["show", "set", "plan", "add"])
ap.add_argument("a", nargs="?")
ap.add_argument("b", nargs="?")
ap.add_argument("--unit", default=None)
ap.add_argument("--note", default="")
args = ap.parse_args()
d = json.loads(F.read_text()) if F.exists() else {"budget": None, "unit": "credits", "entries": []}
if args.cmd == "set":
    d["budget"] = float(args.a)
    d["unit"] = args.unit or d["unit"]
elif args.cmd in ("plan", "add"):
    d["entries"].append(dict(kind=args.cmd, label=args.a, amount=float(args.b), note=args.note,
                             at=time.strftime("%Y-%m-%d %H:%M")))
F.parent.mkdir(parents=True, exist_ok=True)
F.write_text(json.dumps(d, indent=1))
spent = sum(e["amount"] for e in d["entries"] if e["kind"] == "add")
done = {e["label"] for e in d["entries"] if e["kind"] == "add"}
planned = sum(e["amount"] for e in d["entries"] if e["kind"] == "plan" and e["label"] not in done)
u = d["unit"]
print(f"budget {d['budget'] if d['budget'] is not None else 'not set'} {u}")
print(f"spent  {spent:.0f} {u}   still planned {planned:.0f} {u}", end="")
if d["budget"] is not None:
    left = d["budget"] - spent
    print(f"   left {left:.0f} {u}{'   OVER BUDGET IF PLAN RUNS' if planned > left else ''}")
else:
    print()
