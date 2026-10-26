"""Build mv/data/edl.json: the cut list, laid out on the song's beat grid.

Usage: .venv/bin/python mv/scripts/edl.py

Write the edit as sections. Each section starts on a beat and holds shots that run back to back:
    section(START_BEAT, [S(src, in_seconds, beats, **opts), ...])
Sections must tile the song from beat 0 to the "end" beat in song.json; a BLACK tail for the end card
is added automatically. src is an AI clip code (mv/clips/<CODE>.mp4), a code from mv/data/codes.json
(archive film, local video or still image), "BLACK", or a procedural background (GEN_GRID, GEN_PLASMA,
GEN_TUNNEL). in_seconds is clamped so the shot never runs past its source.

Shot options (all optional):
  speed=0.6        playback speed; below 0.85 uses motion-blended frames (dreamy slow motion)
  rev=True         play backwards
  x="dissolve", xd=2   transition INTO this shot: dissolve over xd beats
  x="glitch"       glitch burst on the cut;  x="flash", flash=0.6  white flash on the cut
  grade="mono"     a key of GRADES in look.py (defaults: AI_GRADE for AI clips, ARCHIVE_GRADE otherwise)
  expo=0.75        exposure multiplier on top of the grade (tame bright archive shots)
  zoom=(1.0, 1.1)  zoom from/to over the shot;  pan=((x0, y0), (x1, y1)) offset in frame units
  rot=0.0, spin=0.0, shake=0.5   rotation (radians), rotation speed, handheld shake
  mirror=1, kal=6  mirror the frame, or kaleidoscope with N slices (an accent; not on faces)
  echo=0.4         feedback ghosting;  trail=0.5  bright light trails
  glitch=0.3       continuous glitch;  scan=0.3  scanlines;  invert=1.0
  punch=1.0        scales the beat punch-in;  label="TEXT"  per-shot caption, ctx["label"] in fx.py
  size="W"         shot size: W wide, M medium, C close, X extreme close; edl.py then warns on neighbours
                   of the same size and on sections that don't open wide
  motif=True       a deliberate repeat of footage used elsewhere (otherwise edl.py warns on reuse)
  sync=SONG_TIME   for lipsync clips: the song time where the clip's own audio starts; the in-point
                   is then computed so the mouth stays on the song (find it with sync_offset.py)
  matte=True       person matte for an archive shot (rembg on the segment), so fx.py can put graphics
                   behind the people in it; AI clips with a <CODE>_matte.mp4 get one automatically
OVER track (double exposures over the main track):
  (start_beat, beats, src, in_seconds, dict(op=0.4, blend="screen"|"add"|"lighten"|"diff", fade=0.4, ...))

After writing edl.json it prints an edit report and warnings: footage reused, grade changes between
consecutive archive shots that aren't at a story turn, the average shot length against PACE_BEATS,
sources per song section, shot sizes (when tagged), and singer shots whose mouth may move off the
lyrics (from mv/data/mouths.json, see references/video-providers.md "Lipsync"). Warnings are advice:
fix them or know why each one stands.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from media import duration, is_ai, is_gen  # noqa: E402
from timing import BEAT, DROPS, DUR, END, SECTIONS as SONG_SECTIONS, beat, beat_at  # noqa: E402,F401

ROOT = Path("mv")
ARCHIVE_GRADE = "base"  # default grade for archive, library and photo shots (a key of GRADES in look.py)
AI_GRADE = "ai"         # default grade for AI clips
DEFAULT_GRADES = {}     # per-code default grade, e.g. {"A3": "mono", "P2": "dim"}
# Colour follows the story, not the source film: one grade per chapter, changing at a story turn.
# [(song_time, grade), ...] for archive/library shots, e.g. [(0.0, "cold"), (DROPS[0], "warm")]
STORY_GRADES = []
AI_STORY_GRADES = []    # the same for AI clips (cold-lit takes before the turn, warm-lit after)
PACE_BEATS = (2.0, 4.0)  # usual average shot length in beats for a dance track; ballads run longer
MAX_SOURCES = 4         # distinct sources in one song section before edl.py warns

DREAMY = dict(speed=0.7, echo=0.25)
SLOW = dict(speed=0.55, echo=0.4)


def S(src, t_in, beats, **o):
    return (src, t_in, beats, o)


SECTIONS = []
OVER = []


def section(start_beat, shots):
    SECTIONS.append((start_beat, shots))


# ======================================= EDIT ==================================================
# Write this video's cut here. One way a dance track can run: intro 8-beat dissolves; verse 4-beat
# shots; build 4 then 2 beats; riser 1-beat cuts; the drop opens on the strongest image, then 1-2 beat
# cuts; breakdown 8-beat dissolves; final build 1 then half beats. Interleave sources.
#
# section(0, [
#     S("A1", 12.0, 8, speed=0.6, zoom=(1.1, 1.2)),
#     S("A2", 40.5, 8, x="dissolve", xd=2, grade="dim"),
#     S("P1", 0.5, 16, x="dissolve", xd=2, speed=0.8),
# ])
# section(32, [S("B1", 63.0, 4, x="dissolve", xd=1), S("P2", 1.0, 4), ...])
# OVER.append((24, 8, "A1", 48.0, dict(op=0.35, grade="mono", speed=0.6)))
# ===============================================================================================


def default_grade(src, start=0.0):
    if src in DEFAULT_GRADES:
        return DEFAULT_GRADES[src]
    if src == "BLACK" or is_gen(src):
        return "orig"
    ai = is_ai(src)
    grade = AI_GRADE if ai else ARCHIVE_GRADE
    for t, g in (AI_STORY_GRADES if ai else STORY_GRADES):
        if start >= t - 0.01:
            grade = g
    return grade


def seg_dict(src, t_in, dur, o, start=0.0):
    d = dict(src=src, dur=dur)
    d.update(o)
    d.setdefault("grade", default_grade(src, start))
    ai = src != "BLACK" and is_ai(src)
    d.setdefault("zoom", (1.0, 1.06) if ai else (1.04, 1.12))
    need = dur * d.get("speed", 1.0) + 0.15
    d["in"] = max(0.0, min(t_in, (duration(src) if src != "BLACK" else 1e9) - need))
    if d.get("x") == "dissolve":
        d["xd"] = d["xd"] * BEAT
    return d


def main():
    if not SECTIONS:
        sys.exit("no sections yet: write the edit in the EDIT block of edl.py")
    end_beat = round(beat_at(END), 3)
    last_start, last_shots = SECTIONS[-1]
    covered = last_start + sum(sh[2] for sh in last_shots)
    if covered < end_beat - 1e-3:
        sys.exit(f"the edit ends at beat {covered:g} but the song's end (song.json \"end\") is beat {end_beat:g}: "
                 f"add {end_beat - covered:g} beats or move \"end\"")
    if END < DUR and covered - end_beat < 0.25:
        section(covered, [S("BLACK", 0.0, beat_at(DUR) - covered + 0.5)])
    for (sb, shots), nxt in zip(SECTIONS, SECTIONS[1:]):
        total = sum(sh[2] for sh in shots)
        if abs(sb + total - nxt[0]) > 1e-6:
            sys.exit(f"section at beat {sb} sums to {total} beats, but the next section starts at beat {nxt[0]}")
    main_segs = []
    for start_beat, shots in SECTIONS:
        b = start_beat
        for src, t_in, beats, o in shots:
            start = beat(b) if b else 0.0
            if "sync" in o:  # lipsync: play the clip so its audio lines up with the song
                t_in = start - o["sync"]
            s = seg_dict(src, t_in, beats * BEAT, o, start)
            s["start"] = start
            main_segs.append(s)
            b += beats
    for a, nxt in zip(main_segs, main_segs[1:]):
        a["dur"] = nxt["start"] - a["start"]
    over = []
    for sb, beats, src, t_in, o in OVER:
        s = seg_dict(src, t_in, beats * BEAT, o, beat(sb))
        s["start"] = beat(sb)
        over.append(s)
    from look import GRADES
    unknown = sorted({s["grade"] for s in main_segs + over} - set(GRADES))
    if unknown:
        sys.exit(f"grades not in look.py GRADES: {', '.join(unknown)}")
    (ROOT / "data" / "edl.json").write_text(json.dumps({"main": main_segs, "over": over}, indent=1))
    kind = lambda s: "black" if s["src"] == "BLACK" else "gen" if is_gen(s["src"]) else "ai" if is_ai(s["src"]) else "lib"
    tot = {k: sum(s["dur"] for s in main_segs if kind(s) == k) for k in ("ai", "lib", "gen")}
    shown = max(sum(tot.values()), 1e-9)
    print(f"{len(main_segs)} cuts, {len(over)} overlays; AI {tot['ai']:.1f}s ({100 * tot['ai'] / shown:.0f}%), "
          f"archive/library {tot['lib']:.1f}s ({100 * tot['lib'] / shown:.0f}%), generated backgrounds "
          f"{tot['gen']:.1f}s; last cut at {main_segs[-1]['start']:.2f}s")
    report(main_segs, GRADES)


def report(segs, grades):
    """Print the edit report and warnings (advice, not errors)."""
    warns = {}
    add = lambda kind, msg: warns.setdefault(kind, []).append(msg)
    lib = lambda s: s["src"] != "BLACK" and not is_gen(s["src"]) and not is_ai(s["src"])
    span = lambda s: (s["in"], s["in"] + s["dur"] * s.get("speed", 1.0))
    shown = [s for s in segs if s["start"] < END - 0.01 and s["src"] != "BLACK"]

    used = {}
    for s in shown:
        if not lib(s):
            continue
        a, b = span(s)
        prev = next((t for (a2, b2, t) in used.get(s["src"], []) if min(b, b2) - max(a, a2) > 0.5), None)
        if prev is not None and not s.get("motif"):
            add("footage reused (set motif=True on deliberate repeats)",
                f"{s['start']:7.2f}s {s['src']} {a:.1f}-{b:.1f}s, already shown at {prev:.2f}s")
        used.setdefault(s["src"], []).append((a, b, s["start"]))

    look = lambda g: (grades[g][1] if grades[g][0] > 0.05 else -1, grades[g][2] < 0.05)
    turn = lambda t: sum(t >= x - 0.01 for x, _ in STORY_GRADES)
    prev = None
    for s in (x for x in shown if lib(x)):
        if prev and look(s["grade"]) != look(prev["grade"]) and turn(s["start"]) == turn(prev["start"]):
            add("look changes between consecutive archive shots, not at a story turn",
                f"{s['start']:7.2f}s {prev['src']} ({prev['grade']}) -> {s['src']} ({s['grade']})")
        prev = s

    print(f"\n{'section':12} {'start':>7} {'cuts':>5} {'beats/cut':>9} {'sources':>7}")
    for a, b, name, _, _ in SONG_SECTIONS:
        sec = [s for s in shown if a - 0.01 <= s["start"] < b - 0.01]
        if not sec:
            continue
        srcs = sorted({s["src"] for s in sec})
        print(f"{name:12} {a:7.2f} {len(sec):5d} {(beat_at(min(b, END)) - beat_at(a)) / len(sec):9.2f} {len(srcs):7d}")
        if len(srcs) > MAX_SOURCES:
            add(f"sections using more than {MAX_SOURCES} sources (give each chapter its own footage)",
                f"{name} at {a:.2f}s: {', '.join(srcs)}")
        sized = [s for s in sec if s.get("size")]
        if sized and sec[0].get("size") not in (None, "W"):
            add("sections that don't open wide", f"{name} at {a:.2f}s opens on {sec[0]['size']}")
    avg = beat_at(END) / max(len(shown), 1)
    print(f"{'all':12} {0:7.2f} {len(shown):5d} {avg:9.2f}")
    if not PACE_BEATS[0] <= avg <= PACE_BEATS[1]:
        add("pace", f"average shot {avg:.2f} beats, outside PACE_BEATS {PACE_BEATS} (SKILL.md, Phase 4)")
    for x, y in zip(shown, shown[1:]):
        if x.get("size") and x.get("size") == y.get("size"):
            add("neighbouring shots of the same size", f"{y['start']:7.2f}s {x['src']} -> {y['src']} both {y['size']}")

    mfile = ROOT / "data" / "mouths.json"
    mouths = json.loads(mfile.read_text()) if mfile.exists() else {}
    for s in shown:
        m = mouths.get(s["src"])
        if not m:
            continue
        a, b = span(s)
        native = m.get("sync")
        if native is not None and s.get("speed", 1.0) == 1.0 and abs(s["start"] - s["in"] - native) <= 0.05:
            continue   # a singing take shown where it was recorded
        if any(a >= x - 0.05 and b <= y + 0.05 for x, y in m.get("safe", [])):
            continue   # mouth closed or out of view in this stretch
        why = (f"recorded for song time {native + a:.2f}s" if native is not None
               else "outside its mouth-safe ranges")
        add("singer shots whose mouth may move off the lyrics (mouths.json)",
            f"{s['start']:7.2f}s {s['src']} clip {a:.1f}-{b:.1f}s, {why}")

    if not warns:
        print("\nno warnings")
    for kind, msgs in warns.items():
        print(f"\nWARNING {kind}: {len(msgs)}")
        for m in msgs[:8]:
            print("  " + m)
        if len(msgs) > 8:
            print(f"  ... and {len(msgs) - 8} more")


if __name__ == "__main__":
    main()
