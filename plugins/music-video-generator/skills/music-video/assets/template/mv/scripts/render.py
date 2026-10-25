"""GPU compositor for a music video.

Usage:
  .venv/bin/python mv/scripts/render.py OUT.mp4 [--size 1920x1080] [--start S] [--end E] [--stills T1,T2,...]
  --size 1080x1920 (vertical), 1080x1080 or 1080x1350 for social cuts: sources stay 16:9 and the frame
  shows the middle of them; shots with a person matte are reframed on the person automatically, and
  pan=((x, 0), (x, 0)) in the EDL reframes any other shot. Letterbox is skipped for non-wide output.

Reads mv/data/edl.json (built by mv/scripts/edl.py), mv/data/song.json (via timing.py) and
mv/data/audio_feats.npz (audio_feats.py). Each EDL segment is cut from its source by ffmpeg into
mv/work/seg/ (1280x720, 24 fps, speed applied); AI clips with a person matte get a matching matte
segment. Every output frame is then built on the GPU with moderngl:
  pass 1  layer transforms (zoom/pan/rotate/shake, mirror, kaleidoscope), gradient-map grading,
          dissolves, double exposure (over track), echo/trail feedback, glitch; matte in alpha
  pass 2  overlay: "behind" layer (big words) masked by the person matte, then the "front" layer
  bloom   two-level bloom from the bright pass
  final   punch-in, shockwave, chromatic aberration, bloom/halation, star glints, flash, fx.py's
          final shader, vignette, scanlines, film grain, fade
Sources can also be GEN_GRID, GEN_PLASMA or GEN_TUNNEL: procedural backgrounds drawn in the shader
that pulse with the kick, for visualizers and footage-free sections.
With --stills it writes JPEGs (OUT_<time>.jpg) instead of a video, rendering a 0.6 s warm-up before
each still so feedback effects look the same as in the full render.

This file is the engine and has no style of its own. Per video: look.py (palettes, grades and the
finish: grain, bloom, glints, letterbox, drop flashes, all off by default) and fx.py (this video's
shaders, uniforms and every overlay graphic).
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import moderngl
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from media import GEN_IDS, crop_for, is_ai, is_gen, is_image, matte_path, src_path  # noqa: E402
import fx  # noqa: E402
from look import FINISH, GRADES, PALETTES, SHADOW_TINT  # noqa: E402
from overlay import Overlay  # noqa: E402
from timing import BEAT, DROPS, DUR, END, FPS, SHOCKS, SONG, beat_phase, is_calm, section  # noqa: E402

ROOT = Path("mv")
SEG = ROOT / "work" / "seg"
SW, SH = 1280, 720

VERT = """
#version 330
in vec2 pos; out vec2 uv;
void main(){ uv = pos*0.5+0.5; gl_Position = vec4(pos,0,1); }
"""

COMMON = """
const float ASP = ASP_VALUE;        // output aspect, filled in at startup
const float SRC_ASP = 16.0/9.0;     // segments are always 16:9
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
vec2 mrep(vec2 p){ return abs(mod(p+1.0, 2.0)-1.0); }
vec2 hash2(vec2 p){
  p = vec2(dot(p, vec2(127.1,311.7)), dot(p, vec2(269.5,183.3)));
  return -1.0 + 2.0*fract(sin(p)*43758.5453);
}
float gnoise(vec2 p){
  vec2 i = floor(p), f = fract(p), u = f*f*(3.0-2.0*f);
  return mix(mix(dot(hash2(i), f), dot(hash2(i+vec2(1,0)), f-vec2(1,0)), u.x),
             mix(dot(hash2(i+vec2(0,1)), f-vec2(0,1)), dot(hash2(i+vec2(1,1)), f-vec2(1,1)), u.x), u.y);
}
float grainAt(vec2 px, float size, float seed){
  vec2 o = vec2(fract(seed*0.6180339), fract(seed*0.4142135))*1000.0;
  return gnoise(px/size + o)*0.7 + gnoise(px/(size*0.5) + o*1.7)*0.3;
}
"""

P1 = """
#version 330
uniform sampler2D tA, tB, tC, tPrev, tMA, tMB;
uniform float hasMA, hasMB;
uniform vec4 xfA, xfB, xfC;          // zoom, offx, offy, rot
uniform vec4 gA1, gA2, gB1, gB2, gC1, gC2;  // (gm,pal,sat,con) (lift,expo,mirror,kal)
uniform float mixAB, opC, blendC, echo, trail, glitch, time, kalRot, genA, genB, genC, kick, loud;
in vec2 uv; out vec4 o;
""" + COMMON + """
vec3 pal(float l, float id){
  vec3 s0,s1,s2,s3,s4;
  PALETTE_CODE
  l = clamp(l,0.,1.)*4.0;
  if (l<1.) return mix(s0,s1,l); if (l<2.) return mix(s1,s2,l-1.); if (l<3.) return mix(s2,s3,l-2.); return mix(s3,s4,l-3.);
}
vec2 xform(vec2 p, vec4 xf, float mir, float kal){
  vec2 c = p-0.5; c.x *= ASP;
  float cs = cos(xf.w), sn = sin(xf.w);
  c = mat2(cs,-sn,sn,cs)*c;
  if (kal > 0.5){
    float r = length(c), a = atan(c.y,c.x) + kalRot, s = 6.2831853/kal;
    a = mod(a, s); a = abs(a - s*0.5); c = vec2(cos(a), sin(a))*r;
  }
  c.x /= SRC_ASP; c /= xf.x; c += xf.yz;
  p = c+0.5;
  if (mir > 0.5) p.x = 0.5 - abs(p.x-0.5);
  return mrep(p);
}
vec3 grade(vec3 c, vec4 g1, vec4 g2){
  c *= g2.y;
  c = c + g2.x*(1.0-c);
  c = clamp((c-0.5)*g1.w+0.5, 0., 1.5);
  float l = dot(c, vec3(.299,.587,.114));
  c = mix(vec3(l), c, g1.z);
  return mix(c, pal(l, g1.y), g1.x);
}
vec3 genPattern(vec2 q, float id){
  vec2 p = (q - 0.5) * vec2(SRC_ASP, 1.0);
  float t = time;
  if (id < 1.5){                                    // 1: synthwave sun over a scrolling grid
    if (p.y > 0.0){
      vec3 sky = mix(vec3(0.10,0.02,0.18), vec3(0.01,0.0,0.04), clamp(p.y*2.0, 0.0, 1.0));
      float d = length(p - vec2(0.0, 0.12));
      float bands = min(step(0.5, fract((p.y - 0.12)*18.0 - t*0.6)) + step(0.12, p.y), 1.0);
      vec3 sc = mix(vec3(1.0,0.25,0.55), vec3(1.0,0.75,0.3), clamp(p.y/0.35, 0.0, 1.0));
      return sky + smoothstep(0.26, 0.25, d)*bands*sc*(1.0 + 0.6*kick) + smoothstep(0.45, 0.0, d)*vec3(0.25,0.05,0.2);
    }
    float z = 0.12 / max(-p.y, 0.002);
    float gx = abs(fract(p.x*z*1.5) - 0.5), gz = abs(fract(z - t*1.2) - 0.5);
    float line = clamp(smoothstep(0.03*z, 0.0, gx) + smoothstep(0.04*z, 0.0, gz), 0.0, 1.0);
    return vec3(0.0,0.0,0.02) + line*clamp(-p.y*4.0, 0.0, 1.0)*vec3(0.2,0.9,1.0)*(0.7 + 0.8*kick);
  } else if (id < 2.5){                             // 2: plasma
    float v = sin(p.x*6.0 + t) + sin(p.y*7.0 - t*1.3) + sin((p.x + p.y)*5.0 + t*0.7) + sin(length(p)*12.0 - t*2.0);
    v = v*0.25 + 0.5;
    return (0.5 + 0.5*cos(6.2831*(v + vec3(0.0, 0.33, 0.67) + loud*0.3)))*(0.45 + 0.6*kick);
  }
  float r = length(p) + 1e-3, a = atan(p.y, p.x);   // 3: tunnel of rings
  float z = 0.3/r + t*1.5;
  float ring = smoothstep(0.0, 0.08, abs(fract(z) - 0.5) - 0.42);      // bright near whole z
  float spokes = smoothstep(0.0, 0.03, abs(fract(a*6.0/6.2831) - 0.5) - 0.47);
  return (ring + 0.4*spokes)*smoothstep(0.0, 0.25, r)*mix(vec3(1.0,0.2,0.6), vec3(0.2,0.9,1.0), fract(z*0.25))*(0.7 + kick);
}
vec3 layer(sampler2D t, vec2 p, vec4 xf, vec4 g1, vec4 g2, vec2 gofs, float gen){
  vec2 q = xform(p, xf, g2.z, g2.w);
  if (gen > 0.5) return grade(genPattern(q, gen), g1, g2);
  q.y = 1.0 - q.y;
  vec3 c;
  if (glitch > 0.0){
    c.r = texture(t, mrep(q + gofs)).r; c.g = texture(t, q).g; c.b = texture(t, mrep(q - gofs)).b;
  } else c = texture(t, q).rgb;
  return grade(c, g1, g2);
}
void main(){
  vec2 p = uv;
  float seed = floor(time*12.0);
  vec2 gofs = vec2(0.0);
  if (glitch > 0.0){
    float band = floor(uv.y*28.0);
    if (hash(vec2(band, seed)) < glitch*0.7) p.x += (hash(vec2(band, seed+3.1))-0.5)*0.22*glitch;
    gofs = vec2(0.006 + 0.02*glitch, 0.0);
  }
  vec3 a = layer(tA, p, xfA, gA1, gA2, gofs, genA);
  float mA = 0.0, mB = 0.0;
  if (hasMA > 0.5){ vec2 q = xform(p, xfA, gA2.z, gA2.w); q.y = 1.0 - q.y; mA = texture(tMA, q).r; }
  if (hasMB > 0.5){ vec2 q = xform(p, xfB, gB2.z, gB2.w); q.y = 1.0 - q.y; mB = texture(tMB, q).r; }
  float matte = mix(mA, mB, mixAB);
  vec3 col = a;
  if (mixAB > 0.0) col = mix(a, layer(tB, p, xfB, gB1, gB2, gofs, genB), mixAB);
  if (opC > 0.0){
    vec3 c = layer(tC, p, xfC, gC1, gC2, gofs, genC) * opC;
    if (blendC < 0.5) col = 1.0-(1.0-col)*(1.0-c);
    else if (blendC < 1.5) col = col + c;
    else if (blendC < 2.5) col = max(col, c);
    else col = abs(col - c);
  }
  col = fxComp(col, uv, matte);
  vec3 prev = texture(tPrev, uv).rgb;
  if (glitch > 0.0){
    vec2 blk = floor(uv*vec2(16.,9.));
    if (hash(blk + seed*0.37) < glitch*0.18) col = prev;
  }
  if (echo > 0.0) col = mix(col, prev, echo);
  if (trail > 0.0) col = max(col, prev*trail);
  o = vec4(col, matte);
}
"""


def _palette_glsl():
    v = lambda c: "vec3(%.3f,%.3f,%.3f)" % c
    out = []
    for i, stops in enumerate(PALETTES):
        body = " ".join(f"s{k}={v(c)};" for k, c in enumerate(stops))
        if len(PALETTES) == 1:
            out.append(body)
        elif i < len(PALETTES) - 1:
            out.append(f"{'if' if i == 0 else 'else if'} (id < {i + 0.5}){{ {body} }}")
        else:
            out.append(f"else {{ {body} }}")
    return "\n  ".join(out)


def _fx_glsl():
    decl = []
    for k, v in fx.UNIFORMS.items():
        n = len(v) if isinstance(v, (tuple, list)) else 1
        decl.append(f"uniform {'float' if n == 1 else f'vec{n}'} {k};")
    return "\n".join(decl)


P1 = P1.replace("PALETTE_CODE", _palette_glsl()).replace("void main(){", _fx_glsl() + "\n" + fx.GLSL_COMP + "\nvoid main(){", 1)

P2 = """
#version 330
uniform sampler2D tBase, tOver, tBehind;
uniform float overGain, hasOver, hasBehind, letterbox;
in vec2 uv; out vec4 o;
void main(){
  vec4 bs = texture(tBase, uv);
  vec3 c = bs.rgb;
  float bar = 0.5*letterbox*(1.0-(ASP_VALUE)/2.39);
  if (uv.y < bar || uv.y > 1.0-bar) c = vec3(0.0);
  if (hasBehind > 0.5){
    vec4 t = texture(tBehind, vec2(uv.x, 1.0-uv.y));
    c = mix(c, t.rgb, t.a*(1.0 - smoothstep(0.3, 0.6, bs.a)));
  }
  if (hasOver > 0.5){
    vec4 t = texture(tOver, vec2(uv.x, 1.0-uv.y));
    c = mix(c, t.rgb*overGain, t.a);
  }
  o = vec4(c, 1.0);
}
"""

BRIGHT = """
#version 330
uniform sampler2D tSrc; uniform float thr;
in vec2 uv; out vec4 o;
void main(){ vec3 c = texture(tSrc, uv).rgb; float l = max(c.r, max(c.g, c.b));
  o = vec4(c * smoothstep(thr, thr+0.35, l), 1.0); }
"""

BLUR = """
#version 330
uniform sampler2D tSrc; uniform vec2 dir;
in vec2 uv; out vec4 o;
void main(){
  float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  vec3 c = texture(tSrc, uv).rgb*w[0];
  for (int i=1;i<5;i++){ c += texture(tSrc, uv+dir*float(i)).rgb*w[i]; c += texture(tSrc, uv-dir*float(i)).rgb*w[i]; }
  o = vec4(c,1.0);
}
"""

FINAL = """
#version 330
uniform sampler2D tComp, tB1, tB2;
uniform float bloom, halation, ca, shockT, shockAmp, grain, vignette, scan, letterbox, fade, flash, time, punch, invert, tint, glint;
in vec2 uv; out vec4 o;
""" + COMMON + """
void main(){
  vec2 p = uv;
  p = 0.5 + (p-0.5)/(1.0 + punch);
  if (shockAmp > 0.0){
    vec2 d = p-0.5; d.x *= ASP; float r = length(d);
    float rad = shockT*1.6; float w = 0.12;
    float k = smoothstep(w, 0.0, abs(r-rad));
    p -= normalize(d+1e-5)*vec2(1.0/ASP,1.0)*k*shockAmp;
  }
  vec2 dir = (p-0.5);
  float cr = ca*(0.4+length(dir)*1.6);
  vec3 col;
  col.r = texture(tComp, mrep(p + dir*cr)).r;
  col.g = texture(tComp, mrep(p)).g;
  col.b = texture(tComp, mrep(p - dir*cr)).b;
  vec3 b1 = texture(tB1, p).rgb, b2 = texture(tB2, p).rgb;
  col += b1*bloom + b2*bloom*0.8;
  col += b2*halation*vec3(1.0,0.32,0.12);
  if (glint > 0.0){
    vec3 star = vec3(0.0);
    for (int i = 1; i <= 10; i++){
      float w = exp(-float(i)*0.32);
      vec2 ox = vec2(float(i)*0.0055, 0.0), oy = vec2(0.0, float(i)*0.0098);
      star += (texture(tB1, p+ox).rgb + texture(tB1, p-ox).rgb + texture(tB1, p+oy).rgb + texture(tB1, p-oy).rgb)*w;
    }
    col += star*glint*0.1;
  }
  col = col/(1.0+max(col-1.0,0.0)*0.6);
  // shadow tint (SHADOW_TINT in look.py)
  float l = dot(col, vec3(.299,.587,.114));
  col = mix(col, col + SHADOW_TINT_VALUE, tint*(1.0-l));
  col = mix(col, vec3(1.0), flash);
  if (invert > 0.0) col = mix(col, 1.0-col, invert);
  col = fxFinal(col, uv, p);
  float v = length((uv-0.5)*vec2(1.0,0.85));
  col *= 1.0 - vignette*smoothstep(0.35, 0.85, v);
  if (scan > 0.0) col *= 1.0 - scan*0.5*(0.5+0.5*sin(uv.y*SCAN_RES*3.14159));
  // film grain: soft clumps from two octaves of gradient noise, a separate grain per dye layer
  // (blue coarsest), strongest in the midtones, applied mostly multiplicatively so blacks stay black
  vec2 px = uv*GRAIN_RES;   // pixels at 1080p-equivalent scale, so grain size matches any output
  float fr = floor(time*24.0 + 0.5);
  float gl = grainAt(px, 2.0, fr);
  vec3 gc = vec3(grainAt(px, 1.7, fr + 11.0), grainAt(px, 1.9, fr + 23.0), grainAt(px, 2.7, fr + 37.0));
  vec3 g = mix(vec3(gl), gc, 0.35) * 2.4;
  float lg = dot(col, vec3(.299,.587,.114));
  float resp = smoothstep(0.0, 0.03, lg) * (0.55 + 1.6*lg*(1.0 - lg)) * (1.0 - smoothstep(0.85, 1.0, lg));
  col += g*grain*resp;
  col *= fade;
  o = vec4(clamp(col,0.,1.),1.0);
}
"""
FINAL = (FINAL.replace("SHADOW_TINT_VALUE", "vec3(%.4f,%.4f,%.4f)" % SHADOW_TINT)
         .replace("void main(){", _fx_glsl() + "\n" + fx.GLSL_FINAL + "\nvoid main(){", 1))


def seg_file(src, t_in, need, speed, rev):
    crop = "" if src == "BLACK" or is_gen(src) else ",".join(f"{v:.4f}" for v in crop_for(src))
    key = f"{src}|{t_in:.3f}|{need:.3f}|{speed:.4f}|{rev}|{crop}"
    return SEG / (src + "_" + hashlib.md5(key.encode()).hexdigest()[:10] + ".mp4")


def prep_one(job):
    src, t_in, need, speed, rev, out = job[:6]
    is_matte = len(job) > 6 and job[6]
    if src == "BLACK" or is_gen(src) or out.exists():
        return
    if is_matte and not (is_ai(src) and matte_path(src).exists()):
        # archive shot flagged matte=True: segment the prepared color segment with rembg
        from make_matte import matte_video
        color = Path(str(out).replace("_m.mp4", ".mp4"))
        if color.exists():
            matte_video(color, out, log=False)
        else:
            print("matte skipped, color segment missing:", color)
        return
    x, y, w, h = crop_for(src)
    blend = speed < 0.85
    vf = [f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}", f"setpts=(PTS-STARTPTS)/{speed}"]
    vf.append(f"framerate=fps={FPS}:interp_start=0:interp_end=255:scene=100" if blend else f"fps={FPS}")
    vf.append(f"scale={SW}:{SH}:flags=lanczos")
    if is_ai(src) and not is_matte:
        vf.append("unsharp=5:5:0.6")
    if rev:
        vf.append("reverse")
    vf.append(f"trim=end_frame={int(math.ceil(need * FPS)) + 2}")
    if is_image(src) and not is_matte:  # stills: loop the picture; zoom and pan in the EDL make the move
        inp = ["-loop", "1", "-framerate", str(FPS), "-t", f"{need + 0.4:.3f}", "-i", str(src_path(src))]
        vf = [v for v in vf if not v.startswith(("setpts", "framerate", "reverse"))]
    else:
        inp = ["-ss", f"{t_in:.3f}", "-t", f"{need * speed + 0.4:.3f}",
               "-i", str(matte_path(src) if is_matte else src_path(src))]
    cmd = ["ffmpeg", "-v", "error", "-y", *inp, "-an", "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "12",
           "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("prep failed", src, t_in, r.stderr[-300:])


class Reader:
    def __init__(self, path, gray=False):
        self.path = path
        self.gray = gray
        self.nb = SW * SH * (1 if gray else 3)
        self.open()

    def open(self):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(self.path), "-f", "rawvideo",
                                   "-pix_fmt", "gray" if self.gray else "rgb24", "-"], stdout=subprocess.PIPE)
        self.i, self.buf = -1, bytes(self.nb)

    def get(self, fi):
        if fi < self.i:
            self.close()
            self.open()
        while self.i < fi:
            data = self.p.stdout.read(self.nb)
            if len(data) < self.nb:
                break
            self.buf, self.i = data, self.i + 1
        return self.buf

    def close(self):
        self.p.stdout.close()
        self.p.kill()
        self.p.wait()


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Track:
    """Sequential access to one EDL track (main or over)."""

    def __init__(self, segs):
        self.segs = segs
        self.readers = {}

    def reader(self, seg):
        f = seg["file"]
        if f not in self.readers:
            self.readers[f] = Reader(f)
        return self.readers[f]

    def frame(self, seg, local):
        if seg["src"] == "BLACK" or is_gen(seg["src"]):
            return bytes(SW * SH * 3)
        return self.reader(seg).get(max(0, int(round(local * FPS))))

    def matte(self, seg, local):
        f = seg.get("mfile")
        if not f:
            return None
        if f not in self.readers:
            self.readers[f] = Reader(f, gray=True)
        return self.readers[f].get(max(0, int(round(local * FPS))))

    def gc(self, keep):
        for f in list(self.readers):
            if f not in keep and f in self.readers:
                self.readers.pop(f).close()


def xf_uniform(seg, local):
    u = ease(local / max(seg["dur"], 1e-3))
    z0, z1 = seg.get("zoom", (1.0, 1.06))
    p0, p1 = seg.get("pan", ((0, 0), (0, 0)))
    z = z0 + (z1 - z0) * u
    shake = seg.get("shake", 0.0)
    sx = shake * (math.sin(local * 37.0) * 0.6 + math.sin(local * 23.0) * 0.4) * 0.01
    sy = shake * (math.cos(local * 31.0) * 0.6 + math.sin(local * 17.0) * 0.4) * 0.01
    return (z, p0[0] + (p1[0] - p0[0]) * u + sx, p0[1] + (p1[1] - p0[1]) * u + sy,
            seg.get("rot", 0.0) + seg.get("spin", 0.0) * local)


def grade_uniform(seg):
    g = GRADES[seg.get("grade", "orig")]
    return (g[0], g[1], g[2], g[3]), (g[4], g[5] * seg.get("expo", 1.0), float(seg.get("mirror", 0)),
                                      float(seg.get("kal", 0)))


def build_jobs(edl):
    jobs = []
    main = edl["main"]
    for i, s in enumerate(main):
        nxt = main[i + 1] if i + 1 < len(main) else None
        extra = nxt["xd"] if nxt and nxt.get("x") == "dissolve" else 0.0
        need = s["dur"] + extra + 0.1
        s["file"] = str(seg_file(s["src"], s["in"], need, s.get("speed", 1.0), s.get("rev", False)))
        jobs.append(((s["src"], s["in"], need, s.get("speed", 1.0), s.get("rev", False), Path(s["file"])), s))
        if s["src"] != "BLACK" and not is_gen(s["src"]) and (s.get("matte") or (is_ai(s["src"]) and matte_path(s["src"]).exists())):
            s["mfile"] = s["file"].replace(".mp4", "_m.mp4")
            jobs.append(((s["src"], s["in"], need, s.get("speed", 1.0), s.get("rev", False), Path(s["mfile"]), True), s))
    for s in edl.get("over", []):
        need = s["dur"] + 0.1
        s["file"] = str(seg_file(s["src"], s["in"], need, s.get("speed", 1.0), s.get("rev", False)))
        jobs.append(((s["src"], s["in"], need, s.get("speed", 1.0), s.get("rev", False), Path(s["file"])), s))
    return jobs


def subject_x(mfile):
    """Horizontal center (0..1 of the 16:9 segment) of the person in a matte segment."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mfile, "-vf", "fps=4,scale=96:54,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    if not raw:
        return 0.5
    m = np.frombuffer(raw, np.uint8).reshape(-1, 54, 96).astype(float).mean(0)
    col = m.sum(0)
    return float((col * (np.arange(96) + 0.5) / 96).sum() / col.sum()) if col.sum() > 50 else 0.5


def find(segs, t):
    lo, hi = 0, len(segs) - 1
    best = None
    while lo <= hi:
        m = (lo + hi) // 2
        if segs[m]["start"] <= t:
            best, lo = m, m + 1
        else:
            hi = m - 1
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    ap.add_argument("--size", default="1920x1080", help="WxH, e.g. 1080x1920 for vertical")
    ap.add_argument("--stills", default="")
    args = ap.parse_args()

    W, H = map(int, args.size.lower().split("x"))
    out_asp = W / H
    k = 1080.0 / min(W, H)
    global P1, P2, FINAL
    P1 = P1.replace("ASP_VALUE", f"{out_asp:.6f}")
    P2 = P2.replace("ASP_VALUE", f"{out_asp:.6f}")
    FINAL = (FINAL.replace("ASP_VALUE", f"{out_asp:.6f}").replace("GRAIN_RES", f"vec2({W * k:.1f}, {H * k:.1f})")
             .replace("SCAN_RES", f"{H * k:.1f}"))
    edl = json.loads((ROOT / "data" / "edl.json").read_text())
    SEG.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs(edl)
    t0, t1 = args.start, min(args.end, DUR)
    stills = [float(x) for x in args.stills.split(",") if x]
    if stills:
        t0, t1 = min(stills), max(stills) + 0.05
    main_segs, over_segs = edl["main"], edl.get("over", [])

    def needed(s):
        return s["start"] < t1 + 0.5 and s["start"] + s["dur"] + 1.0 > t0

    todo = [j for j, s in jobs if needed(s)]
    color = [j for j in todo if len(j) == 6]
    mattes = [j for j in todo if len(j) > 6]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(prep_one, color))
    with ThreadPoolExecutor(4) as ex:  # archive mattes read the color segments made above
        list(ex.map(prep_one, mattes))
    print(f"prepped {len(todo)} segments", flush=True)
    if out_asp < 1.2:  # narrow output: center each matted shot on its person unless the EDL pans it
        lim = 0.5 - 0.5 * out_asp / (16 / 9)
        for s in main_segs:
            if needed(s) and s.get("mfile") and "pan" not in s and Path(s["mfile"]).exists():
                off = max(-lim, min(lim, subject_x(s["mfile"]) - 0.5))
                s["pan"] = ((off, 0.0), (off, 0.0))

    try:
        ctx = moderngl.create_standalone_context(require=330)
    except Exception:   # headless Linux: no X display, use EGL
        ctx = moderngl.create_standalone_context(require=330, backend="egl")
    quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4"))

    def prog(frag):
        p = ctx.program(vertex_shader=VERT, fragment_shader=frag)
        return p, ctx.vertex_array(p, [(quad, "2f", "pos")])

    p1, v1 = prog(P1)
    p2, v2 = prog(P2)
    pbr, vbr = prog(BRIGHT)
    pbl, vbl = prog(BLUR)
    pfi, vfi = prog(FINAL)

    def tex(w, h, comps=3, dtype="f1"):
        t = ctx.texture((w, h), comps, dtype=dtype)
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return t

    tA, tB, tC = tex(SW, SH), tex(SW, SH), tex(SW, SH)
    tOver = tex(W, H, 4)
    tBehind = tex(W, H, 4)
    tMA, tMB = tex(SW, SH, 1), tex(SW, SH, 1)
    feats = np.load(ROOT / "data" / "audio_feats.npz")
    a_kick, a_hat, a_rms = feats["kick"], feats["hat"], feats["rms"]
    a_snare, a_spec = feats["snare"], feats["spec"]

    def set_fx(progs, values):
        for k, v in values.items():
            for pr in progs:
                if k in pr:
                    pr[k] = tuple(v) if isinstance(v, (tuple, list)) else float(v)
    base = [tex(W, H, 4, "f2"), tex(W, H, 4, "f2")]
    fbase = [ctx.framebuffer([b]) for b in base]
    comp = tex(W, H, 4, "f2")
    fcomp = ctx.framebuffer([comp])
    bw, bh = W // 4, H // 4
    b1, b2 = tex(bw, bh, 4, "f2"), tex(bw, bh, 4, "f2")
    c1, c2 = tex(bw // 2, bh // 2, 4, "f2"), tex(bw // 2, bh // 2, 4, "f2")
    fb1, fb2, fc1, fc2 = (ctx.framebuffer([x]) for x in (b1, b2, c1, c2))
    outt = tex(W, H, 3)
    fout = ctx.framebuffer([outt])
    for f in fbase:
        f.use()
        ctx.clear(0, 0, 0, 1)

    ov = Overlay(W, H)
    mt, ot = Track(main_segs), Track(over_segs)
    enc = None
    if not stills:
        enc = subprocess.Popen([
            "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
            "-r", str(FPS), "-i", "-", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", SONG,
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart",
            "-shortest", args.out], stdin=subprocess.PIPE)

    f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
    ping = 0
    for fi in range(f0, f1):
        t = fi / FPS
        if stills and not any(-0.6 <= t - s < 0.5 / FPS for s in stills):
            continue  # still mode renders a 0.6 s warm-up before each still so echo trails are honest
        i = find(main_segs, t)
        seg = main_segs[i]
        local = t - seg["start"]
        mixab = 0.0
        if seg.get("x") == "dissolve" and local < seg["xd"] and i > 0:
            prev = main_segs[i - 1]
            tA.write(mt.frame(prev, t - prev["start"]))
            tB.write(mt.frame(seg, local))
            sa, la = prev, t - prev["start"]
            mixab = ease(local / seg["xd"])
            keep = {prev["file"], seg["file"], prev.get("mfile"), seg.get("mfile")}
            ma, mb = mt.matte(prev, t - prev["start"]), mt.matte(seg, local)
        else:
            tA.write(mt.frame(seg, local))
            sa, la = seg, local
            keep = {seg["file"], seg.get("mfile")}
            ma, mb = mt.matte(seg, local), None
        if ma is not None:
            tMA.write(ma)
        if mb is not None:
            tMB.write(mb)
        if i + 1 < len(main_segs):
            keep.add(main_segs[i + 1]["file"])
        mt.gc(keep)

        oc = 0.0
        osg = None
        j = find(over_segs, t) if over_segs else None
        if j is not None:
            cand = over_segs[j]
            ol = t - cand["start"]
            if 0 <= ol < cand["dur"]:
                osg = cand
                tC.write(ot.frame(cand, ol))
                fin = cand.get("fade", 0.4)
                oc = cand.get("op", 0.5) * min(1, ol / fin) * min(1, (cand["dur"] - ol) / fin)
        ot.gc({osg["file"]} if osg else set())

        name, kick, sa_t, sb_t = section(t)
        since, bk = beat_phase(t)
        kenv = max(0.6 * kick * math.exp(-since / 0.11), min(1.0, kick * 1.2) * float(a_kick[min(fi, len(a_kick) - 1)]))
        hat = float(a_hat[min(fi, len(a_hat) - 1)])
        loud = float(a_rms[min(fi, len(a_rms) - 1)])
        glitch = seg.get("glitch", 0.0)
        # glitch burst around hard cuts tagged "glitch"
        if seg.get("x") == "glitch" and local < 0.16:
            glitch = max(glitch, 0.8)
        nxt = main_segs[i + 1] if i + 1 < len(main_segs) else None
        if nxt and nxt.get("x") == "glitch" and nxt["start"] - t < 0.09:
            glitch = max(glitch, 0.6)
        flash = 0.0
        if seg.get("x") == "flash" and local < 0.25:
            flash = (1 - local / 0.25) ** 2 * seg.get("flash", 0.85)
        for td in (DROPS if FINISH["drop_flash"] else []):
            if 0 <= t - td < 0.55:
                flash = max(flash, FINISH["drop_flash"] * (1 - (t - td) / 0.55) ** 2)
        shockT, shockAmp = 0.0, 0.0
        for td, amp in (SHOCKS if FINISH["shock"] else []):
            if 0 <= t - td < 1.3:
                shockT, shockAmp = (t - td) / 1.3, FINISH["shock"] * amp * (1 - (t - td) / 1.3)
        lb = 0.0
        for a, b in (FINISH["letterbox"] if out_asp > 1.5 else []):
            lb = max(lb, ease((t - a + BEAT) / BEAT) * ease((b - t) / BEAT) if a - BEAT <= t <= b else 0.0)
        fade = min(1.0, t / 1.2) if t < 1.2 else 1.0
        if END <= t:
            fade = 1.0
        ai = seg["src"] != "BLACK" and is_ai(seg["src"])
        calm = is_calm(t)

        # pass 1
        p1["tA"], p1["tB"], p1["tC"], p1["tPrev"], p1["tMA"], p1["tMB"] = 0, 1, 2, 3, 4, 5
        tA.use(0)
        tB.use(1)
        tC.use(2)
        base[1 - ping].use(3)
        tMA.use(4)
        tMB.use(5)
        p1["hasMA"] = 1.0 if ma is not None else 0.0
        p1["hasMB"] = 1.0 if mb is not None else 0.0
        p1["xfA"] = xf_uniform(sa, la)
        ga1, ga2 = grade_uniform(sa)
        p1["gA1"], p1["gA2"] = ga1, ga2
        p1["xfB"] = xf_uniform(seg, local)
        gb1, gb2 = grade_uniform(seg)
        p1["gB1"], p1["gB2"] = gb1, gb2
        if osg:
            p1["xfC"] = xf_uniform(osg, t - osg["start"])
            gc1, gc2 = grade_uniform(osg)
            p1["gC1"], p1["gC2"] = gc1, gc2
            p1["blendC"] = float({"screen": 0, "add": 1, "lighten": 2, "diff": 3}[osg.get("blend", "screen")])
        p1["genA"] = float(GEN_IDS.get(sa["src"], 0))
        p1["genB"] = float(GEN_IDS.get(seg["src"], 0))
        p1["genC"] = float(GEN_IDS.get(osg["src"], 0)) if osg else 0.0
        p1["kick"] = kenv
        p1["loud"] = loud
        p1["mixAB"] = mixab
        p1["opC"] = oc
        p1["echo"] = seg.get("echo", 0.0)
        p1["trail"] = seg.get("trail", 0.0)
        p1["glitch"] = glitch
        p1["time"] = t
        p1["kalRot"] = t * 0.35
        fi_c = min(fi, len(a_kick) - 1)
        fxa = dict(kick=float(a_kick[fi_c]), snare=float(a_snare[fi_c]), hat=hat, rms=loud, spec=a_spec[fi_c],
                   beat=bk, phase=since, section=name, kick_level=kick, calm=calm, src=seg["src"], local=local,
                   shot=seg, BEAT=BEAT, pulse=kenv)
        fxv = {**fx.UNIFORMS, **fx.uniforms(t, fxa)}
        set_fx((p1, pfi), fxv)
        fbase[ping].use()
        v1.render(moderngl.TRIANGLE_STRIP)

        # pass 2: text (the EDL's end-card tail is BLACK, so fx.py can draw the end card in any pass)
        ob, o = ov.frame(t, {"src": seg["src"], "local": local, "dur": seg["dur"], "label": seg.get("label")})
        p2["tBase"], p2["tOver"], p2["tBehind"] = 0, 1, 2
        base[ping].use(0)
        if o is not None:
            tOver.write(o.tobytes())
            tOver.use(1)
        if ob is not None:
            tBehind.write(ob.tobytes())
            tBehind.use(2)
        p2["hasOver"] = 1.0 if o is not None else 0.0
        p2["letterbox"] = lb
        p2["hasBehind"] = 1.0 if ob is not None else 0.0
        p2["overGain"] = 1.25
        set_fx((p2,), fxv)
        fcomp.use()
        v2.render(moderngl.TRIANGLE_STRIP)

        # bloom
        pbr["tSrc"] = 0
        pbr["thr"] = (0.72 if ai else 0.58) if not calm else 0.5
        comp.use(0)
        fb1.use()
        vbr.render(moderngl.TRIANGLE_STRIP)
        pbl["tSrc"] = 0
        for src_t, dst_f, d in ((b1, fb2, (1 / bw, 0)), (b2, fb1, (0, 1 / bh)),
                                (b1, fb2, (2 / bw, 0)), (b2, fb1, (0, 2 / bh))):
            src_t.use(0)
            pbl["dir"] = d
            dst_f.use()
            vbl.render(moderngl.TRIANGLE_STRIP)
        pbr["thr"] = 0.0
        b1.use(0)
        fc1.use()
        vbr.render(moderngl.TRIANGLE_STRIP)
        for src_t, dst_f, d in ((c1, fc2, (1.5 / (bw // 2), 0)), (c2, fc1, (0, 1.5 / (bh // 2))),
                                (c1, fc2, (3 / (bw // 2), 0)), (c2, fc1, (0, 3 / (bh // 2)))):
            src_t.use(0)
            pbl["dir"] = d
            dst_f.use()
            vbl.render(moderngl.TRIANGLE_STRIP)

        # final
        pfi["tComp"], pfi["tB1"], pfi["tB2"] = 0, 1, 2
        comp.use(0)
        b1.use(1)
        c1.use(2)
        src_i = 0 if ai else 1
        pfi["bloom"] = (FINISH["bloom"][src_i] * (FINISH["bloom_calm"] if calm else 1.0)
                        + FINISH["bloom_kick"] * kenv + FINISH["bloom_loud"] * loud)
        pfi["glint"] = FINISH["glint"][0] + FINISH["glint"][1] * hat
        pfi["halation"] = FINISH["halation"][src_i]
        pfi["ca"] = FINISH["ca"][0] + FINISH["ca"][1] * kenv + 0.012 * glitch
        pfi["shockT"], pfi["shockAmp"] = shockT, shockAmp
        pfi["grain"] = FINISH["grain"][src_i]
        pfi["vignette"] = FINISH["vignette"][1 if calm or name == "intro" else 0]
        pfi["scan"] = seg.get("scan", 0.0)
        pfi["fade"] = fade
        pfi["flash"] = flash
        pfi["time"] = t
        pfi["punch"] = FINISH["punch"] * kenv * seg.get("punch", 1.0)
        pfi["invert"] = seg.get("invert", 0.0)
        pfi["tint"] = 1.0
        set_fx((pfi,), fxv)   # fx.uniforms() may override any engine value this frame
        fout.use()
        vfi.render(moderngl.TRIANGLE_STRIP)
        img = fout.read(components=3)
        ping = 1 - ping
        if stills and any(abs(t - s) < 0.5 / FPS for s in stills):
            from PIL import Image
            Image.frombytes("RGB", (W, H), img).transpose(Image.FLIP_TOP_BOTTOM).save(
                f"{Path(args.out).with_suffix('')}_{t:07.2f}.jpg", quality=88)
        elif not stills:
            frame = np.frombuffer(img, np.uint8).reshape(H, W, 3)[::-1]
            enc.stdin.write(frame.tobytes())
        if fi % 240 == 0:
            print(f"t={t:6.1f}s", flush=True)
    if enc:
        enc.stdin.close()
        enc.wait()
    mt.gc(set())
    ot.gc(set())
    print("done", args.out)


if __name__ == "__main__":
    main()
