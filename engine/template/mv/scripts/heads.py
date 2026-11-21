"""Head boxes for every frame of the edit, so every overlay can keep clear of every face.

  .venv/bin/python mv/scripts/heads.py [--size 540x960] [--video CLEAN.mp4] [--rebuild]

Run it once the edit is cut, again after every change to the EDL, and before the stills (Phase 6).
1. Renders the edit with no overlays (render.py --clean) at --size, which needs the output's shape:
   960x540 (the default) for 16:9, 540x960 for 9:16. --video uses a clean render you already have.
2. Finds faces and heads on every frame of that render, so the boxes follow every crop, zoom, pan and
   speed change exactly as the viewer sees them. On macOS it uses Apple's Vision framework through a
   small Swift helper compiled on first use (swiftc, from the Xcode command line tools): face boxes,
   plus body pose for heads that are turned away or seen from behind. Elsewhere it falls back to
   OpenCV's Haar cascades (frontal and profile faces), which miss turned heads; the sheets matter more
   there. Everything runs locally; nothing is uploaded.
3. Holds each box for 4 frames either side inside its shot (movement between frames), never across a
   cut, and applies the hand corrections in mv/data/heads_manual.json (song seconds, boxes as 0..1 of
   the frame):
     {"add":   [[t0, t1, x0, y0, x1, y1], [t0, t1, x0, y0, x1, y1, x0b, y0b, x1b, y1b]],
      "clear": [[t0, t1]],
      "drop":  [[t0, t1, y]]}
   "add" puts a box on every frame from t0 to t1 (the 10-number form moves from the first box to the
   second); "clear" removes every box; "drop" removes boxes whose top lies below y (a prop read as a head).
4. Writes mv/data/heads.json and mv/review/heads_NN.jpg: every shot every 0.25 s, with a 0.1 grid and the
   boxes in red. Look at every sheet. A head without a box (seen from behind, small in a wide shot,
   blurred by motion, half out of frame) gets an "add"; then run again with --rebuild, which skips the
   render and the detection.

overlay.py reads heads.json: ov.heads(t), ov.place(...) and ov.touches_face(...). facecheck.py checks
the finished overlay of every frame against it.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from timing import FPS  # noqa: E402

WORK = Path("mv/work/heads")
FRAMES = WORK / "frames"
DETECT = WORK / "detect.jsonl"
MANUAL = Path("mv/data/heads_manual.json")
OUT = Path("mv/data/heads.json")
MIN_H = 0.03       # smallest head kept, as a fraction of the frame height (crowds far away are left out)
HOLD = 4           # frames either side a box is held, inside its shot

SWIFT = r"""
import Foundation
import Vision
import AppKit
let dir = CommandLine.arguments[1]
let files = try! FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".jpg") }.sorted()
func box(_ r: CGRect) -> [Double] { [Double(r.minX), Double(1 - r.maxY), Double(r.maxX), Double(1 - r.minY)] }
for f in files {
    guard let img = NSImage(contentsOf: URL(fileURLWithPath: dir + "/" + f)),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let faceReq = VNDetectFaceRectanglesRequest()
    let poseReq = VNDetectHumanBodyPoseRequest()
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([faceReq, poseReq])
    var out: [String: Any] = ["f": f, "w": cg.width, "h": cg.height]
    out["faces"] = (faceReq.results ?? []).map { box($0.boundingBox) + [Double($0.confidence)] }
    var poses: [[String: [Double]]] = []
    for p in poseReq.results ?? [] {
        var d: [String: [Double]] = [:]
        if let pts = try? p.recognizedPoints(.all) {
            for (k, v) in pts where v.confidence > 0.1 {
                d[k.rawValue.rawValue] = [Double(v.location.x), Double(1 - v.location.y), Double(v.confidence)]
            }
        }
        poses.append(d)
    }
    out["pose"] = poses
    print(String(data: try! JSONSerialization.data(withJSONObject: out), encoding: .utf8)!)
}
"""


def on_frame(x):
    return math.floor(x * FPS + 1e-6) / FPS


def render_clean(size):
    out = WORK / "clean.mp4"
    print(f"rendering the edit without overlays at {size} ...", flush=True)
    subprocess.run([sys.executable, "mv/scripts/render.py", str(out), "--clean", "--size", size], check=True)
    return out


def extract(video):
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-q:v", "3", "-start_number", "0",
                    str(FRAMES / "%05d.jpg")], check=True)


def detect_vision():
    src, exe = WORK / "vdetect.swift", WORK / "vdetect"
    if not exe.exists() or not src.exists() or src.read_text() != SWIFT:
        src.write_text(SWIFT)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], check=True)
    with open(DETECT, "w") as f:
        subprocess.run([str(exe), str(FRAMES)], stdout=f, check=True)


def detect_haar():
    import cv2
    cascades = [cv2.CascadeClassifier(cv2.data.haarcascades + n)
                for n in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    with open(DETECT, "w") as out:
        for p in sorted(FRAMES.glob("*.jpg")):
            g = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
            h, w = g.shape
            faces = []
            for flip in (False, True):
                img = cv2.flip(g, 1) if flip else g
                for c in cascades:
                    for (x, y, bw, bh) in c.detectMultiScale(img, 1.1, 5, minSize=(int(MIN_H * h * 0.6),) * 2):
                        x0 = (w - x - bw) if flip else x
                        faces.append([x0 / w, y / h, (x0 + bw) / w, (y + bh) / h, 1.0])
            out.write(json.dumps({"f": p.name, "w": w, "h": h, "faces": faces, "pose": []}) + "\n")


def face_box(f):
    """Vision's face box runs brow to chin: widen it and raise it to take in the hair."""
    x0, y0, x1, y1 = f[:4]
    w, h = x1 - x0, y1 - y0
    return [x0 - 0.18 * w, y0 - 0.55 * h, x1 + 0.18 * w, y1 + 0.04 * h]


def pose_box(p, ar):
    """A head box from body-pose points (nose, eyes, ears, neck, shoulders): also for heads seen from behind."""
    P = {k: (v[0], v[1] * ar) for k, v in p.items() if v[2] > 0.15}   # square units
    ls, rs = P.get("left_shoulder_1_joint"), P.get("right_shoulder_1_joint")
    sw = math.dist(ls, rs) if ls and rs else None
    hp = [P[k] for k in ("head_joint", "left_eye_joint", "right_eye_joint", "left_ear_joint", "right_ear_joint")
          if k in P]
    le, re = P.get("left_ear_joint"), P.get("right_ear_joint")
    size = abs(le[0] - re[0]) * 1.5 if le and re else None
    if sw:
        size = max(size or 0, 0.42 * sw)
    if not size:
        return None
    if hp:
        cx, cy = sum(q[0] for q in hp) / len(hp), sum(q[1] for q in hp) / len(hp)
    elif "neck_1_joint" in P:
        cx, cy = P["neck_1_joint"][0], P["neck_1_joint"][1] - 0.8 * size
    else:
        return None
    hw, hh = 0.62 * size, 0.78 * size
    return [cx - hw, (cy - hh * 1.1) / ar, cx + hw, (cy + hh * 0.9) / ar]


def union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / ua if ua > 0 else 0


def merge(bs):
    out = []
    for b in bs:
        for i, o in enumerate(out):
            if overlap(b, o) > 0.05:
                out[i] = union(o, b)
                break
        else:
            out.append(list(b))
    return out


def build(segs):
    starts = [on_frame(s["start"]) for s in segs]

    def shot(n):   # the shot on frame n, cut where the renderer cuts
        t, best = n / FPS, 0
        for i, a in enumerate(starts):
            if a <= t + 1e-9:
                best = i
        return best

    M = json.loads(MANUAL.read_text()) if MANUAL.exists() else {}
    raw = {}
    for line in open(DETECT):
        d = json.loads(line)
        n, ar = int(d["f"][:-4]), d["h"] / d["w"]
        bs = [face_box(f) for f in d["faces"]] + [b for b in (pose_box(p, ar) for p in d["pose"]) if b]
        bs = [b for b in bs if b[3] - b[1] >= MIN_H]
        for d0, d1, ylim in M.get("drop", []):
            if d0 <= n / FPS < d1:
                bs = [b for b in bs if b[1] < ylim]
        raw[n] = merge(bs)
    frames = sorted(raw)
    held = {}
    for n in frames:
        s = shot(n)
        held[n] = merge([b for m in range(n - HOLD, n + HOLD + 1) if m in raw and shot(m) == s for b in raw[m]])
        t = n / FPS
        if any(c[0] <= t < c[1] for c in M.get("clear", [])):
            held[n] = []
        for a in M.get("add", []):
            if a[0] <= t < a[1]:
                if len(a) == 10:
                    u = (t - a[0]) / (a[1] - a[0])
                    b = [a[2 + k] + (a[6 + k] - a[2 + k]) * u for k in range(4)]
                else:
                    b = list(a[2:6])
                held[n] = merge(held[n] + [b])
    OUT.write_text(json.dumps({"fps": FPS, "frames": {str(n): [[round(v, 4) for v in b] for b in held[n]]
                                                      for n in frames}}))
    return held, shot


def sheets(segs, held):
    Path("mv/review").mkdir(parents=True, exist_ok=True)
    for old in Path("mv/review").glob("heads_*.jpg"):
        old.unlink()
    first = Image.open(FRAMES / "00000.jpg")
    vertical = first.height > first.width
    TW = 216 if vertical else 320
    TH = round(TW * first.height / first.width)
    COLS, PER = (10, 40) if vertical else (6, 36)
    font = ImageFont.load_default()
    want = []
    for i, s in enumerate(segs):
        a, b = on_frame(s["start"]), on_frame(s["start"] + s["dur"])
        t = a + 0.04
        while t < b - 0.03:
            want.append((i, s["src"], round(t * FPS)))
            t += 0.25
        want.append((i, s["src"], int((b - 0.04) * FPS)))
    for k in range(0, len(want), PER):
        chunk = want[k:k + PER]
        rows = (len(chunk) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * TW, rows * (TH + 16)), (12, 12, 12))
        d = ImageDraw.Draw(sheet)
        for j, (i, src, n) in enumerate(chunk):
            p = FRAMES / f"{n:05d}.jpg"
            im = Image.open(p).convert("RGB").resize((TW, TH)) if p.exists() else Image.new("RGB", (TW, TH))
            g = ImageDraw.Draw(im)
            for q in range(1, 10):
                c = (255, 255, 0) if q == 5 else (0, 170, 230)
                g.line([(q * TW / 10, 0), (q * TW / 10, TH)], fill=c)
                g.line([(0, q * TH / 10), (TW, q * TH / 10)], fill=c)
            for b in held.get(n, []):
                g.rectangle((b[0] * TW, b[1] * TH, b[2] * TW, b[3] * TH), outline=(255, 40, 40), width=2)
            x, y = (j % COLS) * TW, (j // COLS) * (TH + 16)
            sheet.paste(im, (x, y + 16))
            d.text((x + 3, y + 2), f"#{i} {src} {n / FPS:.2f}s", font=font, fill=(255, 220, 120))
        sheet.save(f"mv/review/heads_{k // PER:02d}.jpg", quality=82)
    return (len(want) + PER - 1) // PER


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="960x540", help="the output's shape at half size: 540x960 for 9:16")
    ap.add_argument("--video", help="an existing render made with render.py --clean")
    ap.add_argument("--rebuild", action="store_true", help="only re-apply heads_manual.json and redraw the sheets")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    segs = json.loads(Path("mv/data/edl.json").read_text())["main"]
    if not args.rebuild:
        extract(Path(args.video) if args.video else render_clean(args.size))
        if sys.platform == "darwin" and shutil.which("swiftc"):
            print("finding heads with Apple Vision ...", flush=True)
            detect_vision()
        else:
            print("no Apple Vision here: finding faces with OpenCV Haar cascades, which miss heads turned away "
                  "or seen from behind; check the sheets closely", flush=True)
            detect_haar()
    held, shot = build(segs)
    n = sheets(segs, held)
    empty = sorted({shot(k) for k in held} - {shot(k) for k, v in held.items() if v})
    print(f"{len(held)} frames, {sum(1 for v in held.values() if v)} with a head box -> {OUT}")
    print(f"review: mv/review/heads_00.jpg .. heads_{n - 1:02d}.jpg (every shot every 0.25 s, boxes in red)")
    if empty:
        print("shots with no head box at all (check them for people the detector missed):",
              ", ".join(f"#{i} {segs[i]['src']}" for i in empty))


if __name__ == "__main__":
    main()
