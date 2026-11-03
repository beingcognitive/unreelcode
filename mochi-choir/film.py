"""The Mochi Choir: renders cache/video.mp4 (silent, 60 fps) and cache/audio.wav from cache/choir.json.

Physics (positions, contact times, bounce directions) comes from design.py. Display-only: the squish, faces, eyes
following the candies, blinking, blush, floating notes, sleep. Every sung note is a candy landing on a head.

  python film.py [--still t ...] [--audio]
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "lib"))
import gfx    # noqa: E402
import phys   # noqa: E402
from gfx import I  # noqa: E402

FPS, DUR = 60, 58.0
D = json.load(open(ROOT / "cache/choir.json"))
phys.G[1] = D["g"]
SING, CANDY = D["singers"], D["candies"]
SRC = np.array(D["source"])
RC = D["r_candy"]
AC = np.array(D["arc"][:2]); AA, AB = D["arc"][2], D["arc"][3]
LAST = max(c["t_note"] for c in CANDY)
NIGHT = LAST + 1.4
ROUND = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
REPO = "github.com/beingcognitive/unreelcode"
UNI = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
INKC = (110, 72, 78)

MOCHI_COLS = [(1.0, 1.0, 0.98), (1.0, 0.82, 0.88), (0.84, 0.97, 0.74), (1.0, 0.93, 0.66), (0.90, 0.84, 1.0)]
CANDY_COLS = [(1.0, 0.45, 0.55), (0.45, 0.75, 1.0), (1.0, 0.80, 0.30), (0.55, 0.85, 0.50), (0.80, 0.55, 1.0),
              (1.0, 0.60, 0.35)]
RAINBOW = [(1.0, 0.72, 0.74), (1.0, 0.84, 0.66), (1.0, 0.95, 0.70), (0.76, 0.92, 0.76), (0.72, 0.84, 1.0),
           (0.85, 0.77, 1.0)]

hits = {}
for c in CANDY:
    hits.setdefault(c["singer"], []).append(c)
for v in hits.values():
    v.sort(key=lambda c: c["t_hit"])

MOCHI_VS = """
#version 330
in vec2 corner;
in vec4 a; in vec4 b; in vec4 col; in vec4 col2;
uniform vec2 cam; uniform float scale; uniform vec2 res;
out vec2 wp; flat out vec4 A; flat out vec4 B; flat out vec4 C; flat out vec4 C2;
void main(){
    vec2 lo = vec2(a.x - a.z * 1.6 - 4.0, a.y - a.w * 2.5 - 4.0), hi = vec2(a.x + a.z * 1.6 + 4.0, a.y + 6.0);
    vec2 w = mix(lo, hi, corner * 0.5 + 0.5);
    wp = w;
    vec2 s = (w - cam) * scale + res * 0.5;
    gl_Position = vec4(s.x / res.x * 2.0 - 1.0, 1.0 - s.y / res.y * 2.0, 0.0, 1.0);
    A = a; B = b; C = col; C2 = col2;
}
"""
# a = (x, base_y, rx, ry)  b = (look x, look y, blink, mouth)  col = (rgb, blush)  col2 = (happy, sleep, 0, 0)
MOCHI_FS = """
#version 330
in vec2 wp; flat in vec4 A; flat in vec4 B; flat in vec4 C; flat in vec4 C2;
uniform float scale;
out vec4 o;
float ell(vec2 p, vec2 r){ return length(p / r) - 1.0; }
void main(){
    float rx = A.z, ry = A.w;
    vec2 q = (wp - vec2(A.x, A.y - ry)) / vec2(rx, ry);
    float n = q.y > 0.0 ? 3.2 : 2.1;
    float f = pow(pow(abs(q.x), n) + pow(abs(q.y), n), 1.0 / n);
    float d = (f - 1.0) * ry;
    float aa = 1.0 / scale;
    float cov = 1.0 - smoothstep(-aa, aa, d);
    if (cov <= 0.0) discard;
    float w = 1.3 / (ry * scale);
    vec3 c = C.rgb * (1.02 + 0.04 * (-q.y)) * (1.0 - 0.07 * smoothstep(0.35, 1.0, q.y));
    c = mix(c * vec3(0.90, 0.84, 0.86), c, smoothstep(-2.2, -0.6, d));                  // soft outline
    c += vec3(1.0) * 0.45 * exp(-dot((q - vec2(-0.40, -0.52)) / vec2(0.26, 0.15), (q - vec2(-0.40, -0.52)) / vec2(0.26, 0.15)));
    vec2 fc = vec2(B.x * 0.20, 0.08 + B.y * 0.12);
    // blush
    for (int i = 0; i < 2; i++) {
        float s = i == 0 ? -1.0 : 1.0;
        vec2 bp = (q - (fc + vec2(s * 0.56, 0.17))) / vec2(0.17, 0.09);
        c = mix(c, vec3(1.0, 0.50, 0.58), (0.40 + 0.50 * C.a) * exp(-dot(bp, bp) * 1.3));
    }
    vec3 ink = vec3(0.24, 0.15, 0.17);
    // eyes
    for (int i = 0; i < 2; i++) {
        float s = i == 0 ? -1.0 : 1.0;
        vec2 ep = q - (fc + vec2(s * 0.37, -0.03));
        float k = 0.0;
        if (C2.y > 0.5) {                                    // asleep: lower arcs
            float dd = abs(length(ep - vec2(0.0, -0.08)) - 0.115);
            k = (1.0 - smoothstep(0.026, 0.026 + w, dd)) * step(-0.04, ep.y);
        } else if (C2.x > 0.5) {                             // happy: ^ ^
            float dd = abs(length(ep - vec2(0.0, 0.09)) - 0.12);
            k = (1.0 - smoothstep(0.03, 0.03 + w, dd)) * step(ep.y, 0.04);
        } else {
            float h = max(0.016, 0.155 * (1.0 - B.z));
            float dd = ell(ep, vec2(0.112, h)) * min(0.112, h);
            k = 1.0 - smoothstep(0.0, w, dd);
            if (B.z < 0.5) {
                vec2 sp = ep - vec2(-0.038, -0.06);
                c = mix(c, ink, k);
                k = 0.0;
                c = mix(c, vec3(1.0), 1.0 - smoothstep(0.036, 0.036 + w, length(sp)));
            }
        }
        c = mix(c, ink, k);
    }
    // mouth
    vec2 mp = q - (fc + vec2(0.0, 0.22));
    float m = B.w;
    if (m > 0.04) {
        vec2 r = vec2(0.06 + 0.08 * m, 0.03 + 0.17 * m);
        float dd = ell(mp, r) * r.x;
        float k = 1.0 - smoothstep(0.0, w, dd);
        vec3 inside = mix(vec3(0.45, 0.13, 0.17), vec3(1.0, 0.55, 0.6), smoothstep(0.2 * r.y, 0.8 * r.y, mp.y));
        c = mix(c, inside, k);
    } else {
        float dd = abs(length(mp - vec2(0.0, -0.08)) - 0.085);
        c = mix(c, ink, (1.0 - smoothstep(0.022, 0.022 + w, dd)) * step(-0.03, mp.y) * step(abs(mp.x), 0.09));
    }
    o = vec4(c, cov);
}
"""


class Mochi:
    def __init__(self, g):
        self.g = g
        ctx = g.ctx
        self.prog = ctx.program(vertex_shader=MOCHI_VS, fragment_shader=MOCHI_FS)
        q = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32))
        self.buf = ctx.buffer(reserve=4 * 16 * 64)
        self.vao = ctx.vertex_array(self.prog, [(q, "2f", "corner"), (self.buf, "4f 4f 4f 4f/i", "a", "b", "col", "col2")])

    def draw(self, cam, inst):
        if not inst:
            return
        self.prog["cam"].value = cam[:2]
        self.prog["scale"].value = cam[2]
        self.prog["res"].value = (1080, 1920)
        data = np.asarray(inst, np.float32).reshape(-1, 16)
        self.buf.write(data.tobytes())
        self.vao.render(5, instances=len(data))      # TRIANGLE_STRIP


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def candy_pos(c, t):
    if t < c["t_launch"] or t > c["t_exit"]:
        return None
    if t < c["t_hit"]:
        return phys.pos(SRC, np.array(c["v0"]), t - c["t_launch"])
    return phys.pos(np.array(c["p_hit"]), np.array(c["v_out"]), t - c["t_hit"])


# ---- story beats (display only; all from the solved data)
T0, BAR = D.get("T0", 0.75), D.get("BAR", 2.7)
FIRST = min(CANDY, key=lambda c: c["t_hit"])
GRANDPA = 0                                                   # the biggest mochi (G2): asleep until bar 18
T_WAKE = min(c["t_hit"] for c in CANDY if c["singer"] == GRANDPA)
TINY = len(SING) - 1                                          # the smallest (A5): wobbles hardest


def _duet():
    """two neighbours who both sing in the same bar (bars 6-9): they glance at each other at the end of it"""
    for b in range(6, 10):
        who = sorted({c["singer"] for c in CANDY if c["bar"] == b})
        for i in who:
            if i + 1 in who and i > 2:
                return i, i + 1, T0 + (b + 1) * BAR - 1.5, T0 + (b + 1) * BAR - 0.1
    return 10, 11, 20.0, 21.4


DUET = _duet()
EXCITE = (T0 + 14 * BAR, T0 + 17 * BAR)                      # the conductor gets excited in the build-up
CHEER_BARS = [T0 + b * BAR for b in (4, 8, 12, 16)]          # the audience cheers at phrase starts
AUD = [(430.0, 1520.0, 30.0, (1.0, 0.86, 0.90)), (540.0, 1534.0, 33.0, (0.86, 0.97, 0.80)),
       (650.0, 1520.0, 30.0, (0.88, 0.86, 1.0))]
YAWN = (DUR - 2.6, DUR - 1.45)
SLIP = DUR - 1.3
LOOP = 0.5                                                    # the last 0.5 s dissolve into frame 0


def _track():
    """a tracking camera: frames the singers about to sing (window -0.3..+0.55 s), smoothed over ~0.6 s"""
    from scipy.ndimage import gaussian_filter1d
    ts = np.arange(0, DUR + 1, 1 / FPS)
    th = np.array([c["t_hit"] for c in CANDY])
    hx = np.array([SING[c["singer"]]["head"] for c in CANDY])
    cx, cy, sc = np.zeros(len(ts)), np.zeros(len(ts)), np.zeros(len(ts))
    for k, t in enumerate(ts):
        m = (th > t - 0.3) & (th < t + 0.55)
        if not m.any():
            m = np.abs(th - t) == np.abs(th - t).min()
        x0, x1 = hx[m, 0].min(), hx[m, 0].max()
        y0, y1 = hx[m, 1].min(), hx[m, 1].max()
        s_ = float(np.clip(min(1080 / (x1 - x0 + 220), 1920 / (y1 - y0 + 800)), 1.9, 2.4))
        cx[k] = np.clip((x0 + x1) / 2, 540 / s_ - 30, 1080 - 540 / s_ + 30)
        cy[k] = (y0 + y1) / 2 - 300 / s_
        sc[k] = s_
    f = lambda v: gaussian_filter1d(v, 0.6 * FPS, mode="nearest")
    return f(cx), f(cy), f(sc)


_CX, _CY, _SC = _track()


def _lerp(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w,
            math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * w))


def _win(t, t0, t1, ramp):
    return ease((t - t0) / ramp) * (1 - ease((t - t1) / ramp))


def camera(t):
    k = min(int(t * FPS), len(_CX) - 1)
    cam = (_CX[k], _CY[k], _SC[k])
    f = SING[FIRST["singer"]]
    cam = _lerp(cam, ((540 + f["head"][0]) / 2, (560 + f["head"][1]) / 2 + 40, 1.95), 1 - ease((t - 1.4) / 1.8))  # toss + bonk
    g = SING[GRANDPA]
    cam = _lerp(cam, (g["head"][0] + 40, g["head"][1] - 50, 2.7), _win(t, T_WAKE - 0.9, T_WAKE + 1.7, 0.45))
    a_, b_ = SING[DUET[0]]["head"], SING[DUET[1]]["head"]
    cam = _lerp(cam, ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2 - 30, 2.8), _win(t, DUET[2] - 0.4, DUET[3], 0.4))
    cam = _lerp(cam, (540, 1060, 1.0), _win(t, LAST + 0.3, NIGHT + 2.9, 1.0))                   # everyone, at dusk
    top = SING[len(SING) // 2]["head"]
    cam = _lerp(cam, (top[0], top[1] - 40, 2.4), _win(t, NIGHT + 2.9, YAWN[0] - 0.4, 0.7))     # two sleepers
    cam = _lerp(cam, (540, 560, 2.2), ease((t - (YAWN[0] - 0.7)) / 0.7))                       # the yawn
    return cam


def blink_amt(i, t):
    rng = np.random.default_rng(100 + i)
    ts = np.cumsum(rng.uniform(1.8, 4.5, 40)) - 1.0
    k = np.searchsorted(ts, t) - 1
    if k < 0:
        return 0.0
    dt = t - ts[k]
    return max(0.0, 1 - abs(dt - 0.06) / 0.06) if dt < 0.12 else 0.0


def look_at(head, t):
    """weighted toward the candies in flight, nearest strongest"""
    wsum, acc = 0.0, np.zeros(2)
    for c in CANDY:
        if c["t_launch"] - 0.1 <= t <= c["t_exit"]:
            p = candy_pos(c, t)
            if p is None:
                continue
            d = p - head
            w = 1.0 / (np.dot(d, d) + 4000.0)
            acc += w * d / (np.linalg.norm(d) + 1e-6)
            wsum += w
    if wsum == 0:
        d = SRC - head
        return d / np.linalg.norm(d) * 0.6
    v = acc / wsum
    n = np.linalg.norm(v)
    return v / max(n, 1e-6) * min(1.0, 0.4 + n)


def singer_state(i, t):
    s = SING[i]
    sq, mouth, happy, blush = 0.0, 0.0, 0.0, 0.0
    last = None
    for c in hits.get(i, []):
        if c["t_hit"] <= t:
            last = c
        else:
            break
    if last is not None:
        dt = t - last["t_hit"]
        amp = min(1.0, last["impact"] / 1600)
        sq = (0.28 + 0.14 * amp) * (1.7 if i == TINY else 1.0) * math.exp(-dt / 0.16) * math.cos(2 * math.pi * 5.5 * dt)
        mouth = math.exp(-dt / 0.32) * (0.6 + 0.4 * amp)
        happy = 1.0 if dt < 0.42 else 0.0
        blush = math.exp(-dt / 0.9)
    sq += 0.025 * math.sin(2 * math.pi * t / 1.7 + i * 0.9)          # breathing
    sleep = 1.0 if t > NIGHT + 0.12 * i else 0.0
    if i == GRANDPA and t < T_WAKE:
        sleep = 1.0
        sq += 0.05 * math.sin(2 * math.pi * t / 2.2)
    if DUET[2] <= t <= DUET[3] and i in DUET[:2]:
        happy, blush = (1.0 if t > DUET[2] + 0.8 else 0.0), 1.0
    if sleep:
        mouth, happy = 0.0, 0.0
        sq += 0.03 * math.sin(2 * math.pi * t / 2.6 + i)
    return sq, mouth, happy, blush, sleep


def mochi_inst(x, base, rx, ry, sq, look, blink, mouth, blush, happy, sleep, col):
    return [x, base, rx * (1 + 0.6 * sq), ry * (1 - sq), look[0], look[1], blink, mouth, *col, blush, happy, sleep, 0, 0]


def sky(t):
    u = ease((t - NIGHT + 0.6) / 2.2)
    day_t, day_b = np.array([1.0, 0.86, 0.82]), np.array([0.80, 0.88, 1.0])
    ngt_t, ngt_b = np.array([0.07, 0.09, 0.30]), np.array([0.30, 0.24, 0.62])
    return tuple(day_t * (1 - u) + ngt_t * u), tuple(day_b * (1 - u) + ngt_b * u), u


def cloud(cx, cy, sc, night):
    shade = tuple(np.array([0.86, 0.88, 0.97]) * (1 - night) + np.array([0.50, 0.52, 0.80]) * night)
    white = tuple(np.array([1.0, 1.0, 1.0]) * (1 - night) + np.array([0.86, 0.88, 1.0]) * night)
    puffs = [(-62, 4, 30), (-30, -14, 38), (8, -22, 44), (46, -8, 36), (74, 6, 26), (0, 10, 40)]
    out = [I((cx + dx * sc, cy + dy * sc + 7), (cx + dx * sc, cy + dy * sc + 7), r * sc, 4, (*shade, 1)) for dx, dy, r in puffs]
    out += [I((cx + dx * sc, cy + dy * sc), (cx + dx * sc, cy + dy * sc), r * sc * 0.96, 4, (*white, 1)) for dx, dy, r in puffs]
    return out


def frame(g, mo, t):
    cam = camera(t)
    s = cam[2]
    top, bot, night = sky(t)
    g.begin(cam, top=top, bot=bot, spot=(0.06 * (1 - night), 0.05 * (1 - night), 0.02), spotpos=(540, 760), spotr=900)
    # floating sparkles (day) / stars (night)
    rng = np.random.default_rng(7)
    fx = rng.uniform(-200, 1280, 70); fy = rng.uniform(0, 2200, 70); ph = rng.uniform(0, 6.28, 70)
    sp = []
    for k in range(70):
        y = (fy[k] - 18 * t) % 2300 - 150
        a = (0.10 + 0.08 * math.sin(t * 1.3 + ph[k])) * (1 - night) + night * (0.5 + 0.4 * math.sin(t * 3 + ph[k]))
        sp.append(I((fx[k], y), (fx[k], y), 1.6 + night, 3, (1.0, 1.0, 0.95, a), glow=4 + 2 * night))
    g.draw(sp, pad=30, additive=True)
    if night > 0:                                                         # the moon
        g.draw([I((860, 330), (860, 330), 70, 3, (1.0, 0.95, 0.75, 0.5 * night), glow=90)], pad=400, additive=True)
        g.draw([I((860, 330), (860, 330), 62, 4, (1.0, 0.97, 0.82, night))], pad=2)
    # rainbow
    rb = []
    dark = 1 - 0.18 * night
    for bi, col in enumerate(RAINBOW):
        a_, b_ = AA - 6.5 - 13 * bi, AB - 6.5 - 13 * bi
        th = np.linspace(math.pi, 0, 140)
        pts = np.stack([AC[0] + a_ * np.cos(th), AC[1] - b_ * np.sin(th)], 1)
        c = tuple(x * dark for x in col)
        rb += [I(pts[k], pts[k + 1], 7.2, 4, (*c, 1)) for k in range(len(pts) - 1)]
    g.draw(rb, pad=1)
    g.draw(cloud(AC[0] - AA + 39, AC[1] + 10, 1.1, night) + cloud(AC[0] + AA - 39, AC[1] + 10, 1.1, night))
    # halos behind singers who are singing
    halos = []
    for i, sg in enumerate(SING):
        sq, mouth, happy, blush, sleep = singer_state(i, t)
        if mouth > 0.05:
            col = MOCHI_COLS[i % 5]
            h = np.array(sg["head"])
            halos.append(I(h, h, sg["ry"] * 0.8, 3, (1.0, 0.95, 0.75, 0.55 * mouth), glow=sg["ry"] * 0.9))
    g.draw(halos, pad=450, additive=True)
    # the audience inside the arch, on their own little cloud
    g.draw(cloud(540, 1560, 1.6, night))
    aud = []
    for j, (ax, ay, ary, acol) in enumerate(AUD):
        cheer = max([math.exp(-(t - tb) / 0.25) * math.cos(2 * math.pi * 4 * (t - tb)) for tb in CHEER_BARS if 0 <= t - tb < 1.0] + [0.0])
        hap = 1.0 if any(0 <= t - tb < 0.6 for tb in CHEER_BARS) else 0.0
        asl = 1.0 if t > NIGHT - 0.4 + 0.2 * j else 0.0
        lk = look_at(np.array([ax, ay - ary]), t)
        aud.append(mochi_inst(ax, ay, 1.1 * ary, ary, 0.3 * cheer + 0.03 * math.sin(t * 2.5 + j), lk, blink_amt(60 + j, t),
                              0.5 * hap, 0.6, hap * (1 - asl), asl, tuple(x * (1 - 0.12 * night) for x in acol)))
    # conductor on its cloud
    g.draw(cloud(540, 612, 1.25, night))
    cand = []
    for k, c in enumerate(CANDY):
        p = candy_pos(c, t)
        if p is None and c is FIRST and t < c["t_launch"]:
            p = SRC + np.array([0.0, -RC])                 # the first candy waits on the conductor's head
        if p is None:
            continue
        col = CANDY_COLS[k % len(CANDY_COLS)]
        cand.append(I(p, p, RC + 3.5, 4, (1.0, 1.0, 1.0, 0.95)))
        cand.append(I(p, p, RC, 2, (*col, 1.0), param=0.0))
    # conductor bounce with each toss
    csq = 0.0
    for c in CANDY:
        dt = t - c["t_launch"]
        if 0 <= dt < 0.4:
            csq += 0.05 * math.exp(-dt / 0.08) * math.cos(2 * math.pi * 6 * dt)
    excited = EXCITE[0] <= t <= EXCITE[1]
    if excited:
        csq *= 2.2
    csq += 0.02 * math.sin(2 * math.pi * t / 1.4)
    recent = [c for c in CANDY if c["t_launch"] <= t <= c["t_hit"]]
    if recent:
        p = candy_pos(recent[-1], t)
        d = p - np.array([540, 560]); clook = d / (np.linalg.norm(d) + 1e-6)
    else:
        clook = np.array([0.0, 0.6])
    yawn = math.sin(math.pi * min(max((t - YAWN[0]) / (YAWN[1] - YAWN[0]), 0), 1)) if YAWN[0] <= t <= YAWN[1] else 0.0
    cs = 1.0 if (NIGHT + 3.2 < t < YAWN[0] - 0.4) or t > YAWN[1] else 0.0
    cblink = max(blink_amt(99, t), 0.85 * yawn)
    conductor = [mochi_inst(540, 604, 54, 46, csq + 0.12 * yawn, clook, cblink, 0.9 * yawn, 0.3,
                            1.0 if excited else 0.0, cs, tuple(x * (1 - 0.1 * night) for x in (1.0, 0.98, 0.95)))]
    if t > SLIP:                                   # one sleepy candy slips... (and the film loops to the first one)
        u = t - SLIP
        p = np.array([540 + 60 * u, 520 + 0.5 * D["g"] * 0.25 * u * u])
        cand.append(I(p, p, RC + 3.5, 4, (1.0, 1.0, 1.0, 0.95)))
        cand.append(I(p, p, RC, 2, (*CANDY_COLS[0], 1.0), param=0.0))
    # singers
    insts = []
    for i, sg in enumerate(SING):
        sq, mouth, happy, blush, sleep = singer_state(i, t)
        look = look_at(np.array(sg["head"]), t)
        if DUET[2] <= t <= DUET[3] and i in DUET[:2]:
            look = np.array([1.0 if i == DUET[0] else -1.0, 0.1])
        if T_WAKE - 0.3 <= t <= T_WAKE + 1.6 and 1 <= i <= 3:
            d_ = np.array(SING[GRANDPA]["head"]) - np.array(sg["head"]); look = d_ / np.linalg.norm(d_)
        col = tuple(x * (1 - 0.12 * night) for x in MOCHI_COLS[i % 5])
        insts.append(mochi_inst(sg["seat"][0], sg["seat"][1] + 2, sg["rx"], sg["ry"], sq, look, blink_amt(i, t),
                                mouth, blush, happy, sleep, col))
    order = np.argsort([sg["seat"][1] for sg in SING])            # higher seats behind, so every head shows
    mo.draw(cam, aud + [insts[i] for i in order] + conductor)
    # candy trails, candies, and little stars where they land
    trail, stars = [], []
    for k, c in enumerate(CANDY):
        if c["t_launch"] <= t <= c["t_exit"]:
            col = CANDY_COLS[k % len(CANDY_COLS)]
            for j in range(1, 6):
                q = candy_pos(c, t - j * 0.016)
                if q is not None:
                    trail.append(I(q, q, RC * 0.6, 3, (*col, 0.30 * (1 - j / 6)), glow=8))
        dt = t - c["t_hit"]
        if 0 <= dt < 0.35:
            col = CANDY_COLS[k % len(CANDY_COLS)]
            ph_ = np.array(c["p_hit"])
            for j in range(6):
                ang = j * math.pi / 3 + k
                q = ph_ + (30 + 160 * dt) * np.array([math.cos(ang), math.sin(ang)])
                stars.append(I(q, q, 9 * (1 - dt / 0.35) + 2, 6, (*[min(1, x + 0.3) for x in col], 1.0), param=dt * 8))
    g.draw(trail, pad=30, additive=True)
    g.draw(cand)
    g.draw(stars, pad=4)
    img = Image.fromarray(g.read())
    d = ImageDraw.Draw(img, "RGBA")

    def scr(p):
        return ((p[0] - cam[0]) * s + 540, (p[1] - cam[1]) * s + 960)
    # floating notes from singers, z's at night
    fnote = ImageFont.truetype(UNI, int(30 * s))
    for i, sg in enumerate(SING):
        for c in hits.get(i, []):
            dt = t - c["t_hit"]
            if 0 <= dt < 0.9:
                k = SING.index(sg)
                drift = 18 * math.sin(dt * 5 + k)
                x, y = scr((sg["head"][0] + drift + (1 if sg["head"][0] > 540 else -1) * 22 * dt,
                            sg["head"][1] - sg["ry"] - 55 - 90 * dt))
                a = int(255 * min(1, dt / 0.08) * (1 - dt / 0.9))
                col = CANDY_COLS[CANDY.index(c) % len(CANDY_COLS)]
                d.text((x - 9 * s, y - 15 * s), "♪" if (CANDY.index(c) % 3) else "♫", font=fnote,
                       fill=(int(col[0] * 220), int(col[1] * 200), int(col[2] * 220), a))
    fz = ImageFont.truetype(ROUND, int(30 * s))
    sleepers = []
    if t < T_WAKE:
        sleepers.append((SING[GRANDPA], 0.0))
    if t > NIGHT:
        sleepers += [(sg, NIGHT + 0.12 * i + 0.5) for i, sg in enumerate(SING) if i % 3 == 0]
        sleepers.append((dict(head=(540, 520), ry=46), YAWN[1]))
    if sleepers:
        for sg, t0 in sleepers:
            for kk in range(3):
                u = ((t - t0 - kk * 0.7) % 2.1) / 2.1 if t > t0 + kk * 0.7 else None
                if u is None:
                    continue
                x, y = scr((sg["head"][0] + 14 + 20 * u, sg["head"][1] - sg["ry"] * 0.7 - 70 * u))
                zc = (120, 110, 170) if t < NIGHT else (235, 230, 255)
                d.text((x, y), "z", font=fz, fill=(*zc, int(220 * math.sin(math.pi * u))))
    if DUET[2] + 0.7 <= t <= DUET[3]:
        a_, b_ = SING[DUET[0]]["head"], SING[DUET[1]]["head"]
        u = (t - DUET[2] - 0.7) / (DUET[3] - DUET[2] - 0.7)
        fh = ImageFont.truetype(UNI, int(46 * s))
        x, y = scr(((a_[0] + b_[0]) / 2, min(a_[1], b_[1]) - 70 - 40 * u))
        d.text((x - 16 * s, y), "♥", font=fh, fill=(240, 90, 120, int(255 * math.sin(math.pi * u))))
    if T_WAKE <= t < T_WAKE + 0.9:
        fx_ = ImageFont.truetype(ROUND, int(64 * s))
        gg = SING[GRANDPA]
        x, y = scr((gg["head"][0] - gg["rx"] - 40, gg["head"][1] - gg["ry"] * 0.9))
        d.text((x, y), "!", font=fx_, fill=(*INKC, int(255 * (1 - max(0, t - T_WAKE - 0.6) / 0.3))))
    # titles (over the action, inside the safe area)
    def centred(txt, f, y, col, a):
        w = d.textlength(txt, font=f)
        d.text(((1080 - w) / 2 + 3, y + 4), txt, font=f, fill=(255, 255, 255, int(160 * a)))
        d.text(((1080 - w) / 2, y), txt, font=f, fill=(*col, int(255 * a)))
    ta = 1 - ease((t - 3.4) / 0.6)
    if ta > 0:
        centred("The Mochi Choir", ImageFont.truetype(ROUND, 88), 700, INKC, ta)
        centred("sings Bach's Prelude in C", ImageFont.truetype(ROUND, 42), 812, INKC, ta)
    ha = ease((t - 2.4) / 0.4) * (1 - ease((t - 6.2) / 0.5))
    if ha > 0:
        fh = ImageFont.truetype(ROUND, 56)                 # v3: a soft cream pill, so it reads over passing singers
        wmax = max(d.textlength(x, font=fh) for x in ("Every note is a candy", "landing on a head"))
        d.rounded_rectangle(((1080 - wmax) / 2 - 36, 1306, (1080 + wmax) / 2 + 36, 1486), radius=40,
                            fill=(255, 249, 245, int(215 * ha)))
        centred("Every note is a candy", ImageFont.truetype(ROUND, 56), 1330, INKC, ha)
        centred("landing on a head", ImageFont.truetype(ROUND, 56), 1400, INKC, ha)
    ea = ease((t - (NIGHT + 0.3)) / 0.6) * (1 - ease((t - (NIGHT + 2.3)) / 0.5))
    if ea > 0:
        centred(f"{len(CANDY)} candies, {len(SING)} singers", ImageFont.truetype(ROUND, 60), 330, (245, 240, 255), ea)
        centred("good night", ImageFont.truetype(ROUND, 64), 1150, (245, 240, 255), ea)
    ua = ease((t - 55.1) / 0.6) * (1 - ease((t - 57.0) / 0.4))      # v3: where the code lives
    if ua > 0:
        f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 34)
        w = d.textlength(REPO, font=f)
        d.text(((1080 - w) / 2, 1380), REPO, font=f, fill=(226, 220, 255, int(235 * ua)))
    out = np.asarray(img)
    if t > DUR - LOOP:                                   # dissolve into the opening frame, so it loops
        global _F0
        if _F0 is None:
            _F0 = frame(g, mo, 0.0).astype(np.float32)
        u = ease((t - (DUR - LOOP)) / LOOP)
        out = (out.astype(np.float32) * (1 - u) + _F0 * u).astype(np.uint8)
    return out


_F0 = None


# ------------------------------------------------------------------ sound
SR = 48000


def doo(f, amp, dur=1.6):
    """a small round 'doo': harmonics shaped by an 'oo' vowel, gentle vibrato that grows"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.012 * np.minimum(1, t / 0.35) * np.sin(2 * np.pi * 5.6 * t)
    phase = 2 * np.pi * f * np.cumsum(vib) / SR
    x = np.zeros(n)
    for k in range(1, 9):
        fk = k * f
        a = math.exp(-((fk - 330) / 220) ** 2) + 0.35 * math.exp(-((fk - 850) / 260) ** 2) + 0.25 / k
        x += a * np.sin(k * phase)
    env = np.minimum(1, t / 0.025) * np.exp(-t / 0.55)
    x *= env
    # the soft 'squish' of the candy landing
    m = int(0.05 * SR)
    tt = np.arange(m) / SR
    pop = np.sin(2 * np.pi * (700 * tt - 3500 * tt * tt)) * np.exp(-tt / 0.012) * 0.25
    x[:m] += pop
    return x / 2.2 * amp


def audio():
    from scipy.signal import fftconvolve
    import pyloudnorm as pyln
    N = int(DUR * SR)
    out = np.zeros((2, N))
    rng = np.random.default_rng(11)
    for c in CANDY:
        f = 440 * 2 ** ((c["pitch"] - 69) / 12)
        amp = 0.55 + 0.45 * min(1.0, c["impact"] / 1600)
        x = doo(f, amp)
        pan = (SING[c["singer"]]["head"][0] - 540) / 650
        i = int(c["t_hit"] * SR)
        m = min(len(x), N - i)
        out[0, i:i + m] += x[:m] * math.cos((pan + 1) * math.pi / 4)
        out[1, i:i + m] += x[:m] * math.sin((pan + 1) * math.pi / 4)
    ir_n = int(2.4 * SR)
    ir = rng.standard_normal((2, ir_n)) * np.exp(-np.arange(ir_n) / SR / 0.6) * 0.02
    wet = np.stack([fftconvolve(out[k], ir[k])[:N] for k in range(2)])
    mix = out + wet * 0.5
    fade = np.ones(N); fade[-int(1.0 * SR):] = np.linspace(1, 0, int(1.0 * SR))
    mix *= fade
    meter = pyln.Meter(SR)
    mix *= 10 ** ((-14 - meter.integrated_loudness(mix.T)) / 20)
    pk = np.abs(mix).max()
    if pk > 0.89:
        mix *= 0.89 / pk
    print(f"audio: {meter.integrated_loudness(mix.T):.1f} LUFS, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS")
    import wave
    with wave.open(str(ROOT / "cache/audio.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix.T * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--audio", action="store_true")
    a = ap.parse_args()
    if a.audio:
        audio()
        return
    g = gfx.GPU()
    mo = Mochi(g)
    if a.still is not None:
        for t in a.still:
            Image.fromarray(frame(g, mo, t)).save(ROOT / f"cache/C-{t:05.2f}.png")
        return
    ff = subprocess.Popen([shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", "1080x1920", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                           "-crf", "17", "-pix_fmt", "yuv420p", str(ROOT / "cache/video.mp4")], stdin=subprocess.PIPE)
    for k in range(int(DUR * FPS)):
        ff.stdin.write(frame(g, mo, k / FPS).tobytes())
        if k % 300 == 0:
            print("frame", k, flush=True)
    ff.stdin.close(); ff.wait()


if __name__ == "__main__":
    main()
