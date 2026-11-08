"""The timeline: tempo (with honest speed labels), the camera path, captions, readout, end card and loop.
Run with the dominoes venv:  python render/timeline.py info | json
The Blender renderer reads out/timeline.json (one camera + sim time per frame)."""
import json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CHAIN = os.environ.get("CHAIN", "out/film_chain")
J = json.load(open(os.path.join(ROOT, CHAIN + ".json")))
_Z = np.load(os.path.join(ROOT, CHAIN + ".npz"))
ZT, ZQ = _Z["t"], _Z["qpos"]
DOM = J["dom"]; N = len(DOM)
FPS = 30
W, H = 1080, 1920

# props (must match scene.py)
MUG = (0.160, 0.100); CHAIR = (0.98, 0.62); LAMP = (17.5, 4.6)
CAR = (36.2, -5.2); HOUSE = (29.0, 12.6)

# ------------------------------------------------------------------------------------------------ tempo
S_LAND = J["t_85"][-1]
S_END = min(J["t_end"], S_LAND + 1.6)
RATES = [(0.0, 0.25), (1.0, 0.5), (float(os.environ.get("RATE_HALF_END", "6.0")), 1.0)]   # (from sim time, speed); display only


def rate(s):
    r = RATES[0][1]
    for s0, rr in RATES:
        if s >= s0: r = rr
    return r


def speed_label(s):
    return {0.25: "¼× speed", 0.5: "½× speed", 1.0: "real speed"}[rate(s)]


def build_smap():
    sm = [0.0]
    while sm[-1] < S_END:
        sm.append(sm[-1] + rate(sm[-1]) / FPS)
    return np.array(sm[:-1])


SMAP = build_smap()
# a calm opening before the push (display): the chain stands still at its initial state (sim time 0) while the
# pencil glides in from the edge; the simulation clock starts when the pencil reaches its start position
T_PRE = float(os.environ.get("PREROLL", "3.5"))
N_PRE = int(round(T_PRE * FPS))
N_SIM = N_PRE + len(SMAP)          # frames that show the simulated chain (including the still pre-roll)
T_LAND = T_PRE + float(np.interp(S_LAND, SMAP, np.arange(len(SMAP)))) / FPS
T_CAP_END = T_LAND + 6.6
T_CARD = T_CAP_END
T_TOTAL = T_CARD + 2.8
N_TOTAL = int(round(T_TOTAL * FPS))
LOOP_DISSOLVE = 0.5


def sim_time(f):
    if f < N_PRE:
        return 0.0
    return float(SMAP[min(f - N_PRE, len(SMAP) - 1)])


PENCIL_V_VIDEO = 0.003 * RATES[0][1]          # the pencil's simulated 3 mm/s, seen at the opening playback speed


def pencil_back(f):
    """display only, pre-roll: how far (m) the pencil still is behind its simulated start position, along its own
    axis. Out of frame for the first second, then a smooth glide that arrives with the simulated speed."""
    if f >= N_PRE:
        return 0.0
    t = f / FPS; t0 = 1.0; D0 = 0.060
    if t <= t0:
        return D0
    T = T_PRE - t0; tau = (t - t0) / T
    h00 = 2 * tau ** 3 - 3 * tau ** 2 + 1; h11 = tau ** 3 - tau ** 2
    return D0 * h00 + (-PENCIL_V_VIDEO * T) * h11


def video_time_of_sim(s):
    return T_PRE + float(np.interp(s, SMAP, np.arange(len(SMAP)))) / FPS


# ------------------------------------------------------------------------------------------------ camera
def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def dpts(i):
    D = DOM[i]
    return [(D["x"], -D["w"] / 2, 0), (D["x"], D["w"] / 2, 0), (D["x"], 0, D["h"])]


def rows(k):
    return sum([dpts(i) for i in range(k)], [])


def autoframe(dirn, fov, box, P):
    P = np.array(P, float)
    f = -np.array(dirn, float); f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r); u = np.cross(r, f)
    th = math.tan(math.radians(fov) / 2); ax = th * W / H
    x0, x1, y0, y1 = box
    c = P.mean(0); D = 3 * np.ptp(P, 0).max()
    for _ in range(300):
        v = P - (c - D * f); z = v @ f
        sx = ((v @ r) / z / ax + 1) / 2; sy = (1 - (v @ u) / z / th) / 2
        ex = (sx.min() + sx.max()) / 2 - (x0 + x1) / 2; ey = (sy.min() + sy.max()) / 2 - (y0 + y1) / 2
        c = c + 0.5 * (ex * 2 * ax * D * r - ey * 2 * th * D * u)
        k = max((sx.max() - sx.min()) / (x1 - x0), (sy.max() - sy.min()) / (y1 - y0))
        D *= k ** 0.3
    return c, D


def unit(*v):
    v = np.array(v, float); return v / np.linalg.norm(v)


# keyframes along the toppling front u (0 = before domino 1 moves, 19 = domino 20 moving)
# fstop: 0 = no depth of field (deep focus); macro shots use f/16 (the shallow focus says "tiny")
KEYS = [
    dict(u=0.0, target=(-0.0035, 0.0, 0.0030), dirn=unit(-0.12, -1.0, 0.30), D=0.085, fov=30, fstop=16),
    dict(u=2.6, target=(0.0160, 0.0, 0.0055), dirn=unit(-0.75, -1.0, 0.42), D=0.115, fov=30, fstop=16),
    # hold the counting shot (dominoes 1-6 readable) while "The dots count them" is on screen
    dict(u=4.6, target=(0.0200, 0.0, 0.0065), dirn=unit(-0.75, -1.0, 0.45), D=0.135, fov=30, fstop=16),
    dict(u=7.0, dirn=(-1.0, -0.6, 0.70), fov=36, fstop=22, box=(0.10, 0.82, 0.30, 0.76),
         pts=lambda: rows(8) + [(MUG[0], MUG[1] + 0.045, 0.095)]),
    dict(u=11.0, dirn=(-1.0, -0.45, 0.65), fov=40, fstop=0, box=(0.08, 0.82, 0.22, 0.74),
         pts=lambda: rows(13) + [(CHAIR[0], CHAIR[1] + 0.21, 0.93)]),
    dict(u=15.3, target=(4.6, 1.6, 1.1), dirn=unit(-1.0, -0.55, 0.55), D=9.5, fov=40, fstop=0),
    dict(u=17.5, dirn=(-0.75, -0.85, 0.55), fov=40, fstop=0, box=(0.08, 0.82, 0.22, 0.74),
         pts=lambda: rows(18) + [(LAMP[0], LAMP[1], 4.4)]),
    dict(u=19.0, pos=(8.0, -15.0, 1.7), target=(27.0, 3.0, 5.2), fov=58, fstop=0),
]
OVERVIEW = dict(target=(23.0, 0.0, 1.0), dirn=unit(-0.45, -1.0, 0.95), D=78.0, fov=40)

for K in KEYS:
    if "pos" in K:
        K["c"] = np.array(K["target"], float); v = np.array(K["pos"], float) - K["c"]
        K["D"] = float(np.linalg.norm(v)); K["dirn"] = v / K["D"]
    elif "target" in K:
        K["c"] = np.array(K["target"], float)
    else:
        K["c"], K["D"] = autoframe(K["dirn"], K["fov"], K["box"], K["pts"]())
    d = unit(*K["dirn"]); K["az"] = math.atan2(d[1], d[0]); K["el"] = math.asin(d[2])
    K["inv_f"] = 0.0 if not K["fstop"] else 1.0 / K["fstop"]
OVERVIEW["c"] = np.array(OVERVIEW["target"], float)
d = OVERVIEW["dirn"]; OVERVIEW["az"] = math.atan2(d[1], d[0]); OVERVIEW["el"] = math.asin(d[2])


def front_u(s):
    ts = np.array(J["t_start"])
    if s <= ts[0]: return 0.0
    return float(np.interp(s, ts, np.arange(N)))


def _u_track():
    u = np.array([front_u(sim_time(f)) for f in range(N_TOTAL)])
    sig = 12.0; k = np.arange(-48, 49); g = np.exp(-0.5 * (k / sig) ** 2); g /= g.sum()
    return np.convolve(np.pad(u, 48, mode="edge"), g, mode="valid")


U = _u_track()


_pd = np.array([-0.80, -1.0, 0.62]); _pd = _pd / np.linalg.norm(_pd)
PRE_CAM = dict(c=np.array([0.0110, 0.0, 0.0045]), D=0.070, az=math.atan2(_pd[1], _pd[0]), el=math.asin(_pd[2]),
               fov=30.0, inv_f=1.0 / 16)      # the calm opening: dominoes 1-4 from the front, their pips readable


def camera_raw(f):
    u = U[min(f, N_TOTAL - 1)]
    a = b = KEYS[0]; w = 0.0
    if u > KEYS[0]["u"]:
        a = b = KEYS[-1]
        for k in range(len(KEYS) - 1):
            if KEYS[k]["u"] <= u <= KEYS[k + 1]["u"]:
                a, b = KEYS[k], KEYS[k + 1]; w = (u - a["u"]) / (b["u"] - a["u"]); break
    w = w * w * (3 - 2 * w) * 0.35 + w * 0.65
    D = math.exp((1 - w) * math.log(a["D"]) + w * math.log(b["D"]))
    wt = w if abs(b["D"] - a["D"]) < 1e-12 else (D - a["D"]) / (b["D"] - a["D"])
    c = a["c"] + (b["c"] - a["c"]) * wt
    az = a["az"] + (b["az"] - a["az"]) * w; el = a["el"] + (b["el"] - a["el"]) * w
    fov = a["fov"] + (b["fov"] - a["fov"]) * w
    invf = a["inv_f"] + (b["inv_f"] - a["inv_f"]) * w
    # during the giant's fall: a slow push-in, 9 % closer (display)
    ts19 = J["t_start"][-1]; s_now = sim_time(f)
    p = min(max((s_now - ts19) / (S_LAND - ts19), 0.0), 1.0)
    D *= 1 - 0.09 * (p * p * (3 - 2 * p))
    # after the landing: a crane up to the overview (display)
    tq = f / FPS - (T_LAND + 0.8)
    if tq > 0:
        q = min(tq / 3.2, 1.0); q = q * q * (3 - 2 * q)
        O = OVERVIEW
        D = math.exp((1 - q) * math.log(D) + q * math.log(O["D"]))
        c = c + (O["c"] - c) * q
        az = az + (O["az"] - az) * q; el = el + (O["el"] - el) * q
        fov = fov + (O["fov"] - fov) * q
    if f < N_PRE:          # the calm opening shot, easing into the push framing
        q = min(max((f / FPS - 0.8) / (T_PRE - 0.8), 0.0), 1.0); q = q * q * (3 - 2 * q)
        P = PRE_CAM
        D = math.exp((1 - q) * math.log(P["D"]) + q * math.log(D)); c = P["c"] + (c - P["c"]) * q
        az = P["az"] + (az - P["az"]) * q; el = P["el"] + (el - P["el"]) * q
        fov = P["fov"] + (fov - P["fov"]) * q; invf = P["inv_f"] + (invf - P["inv_f"]) * q
    return np.array([c[0], c[1], c[2], math.log(D), az, el, fov, invf])


CAM_SMOOTH_S = float(os.environ.get("CAM_SMOOTH", "0.7"))   # Gaussian sigma (s) applied to every camera track


def _camera_tracks():
    raw = np.array([camera_raw(f) for f in range(N_TOTAL)])
    if CAM_SMOOTH_S <= 0:
        return raw
    sig = CAM_SMOOTH_S * FPS; R = int(4 * sig)
    k = np.arange(-R, R + 1); g = np.exp(-0.5 * (k / sig) ** 2); g /= g.sum()
    out = np.empty_like(raw)
    for j in range(raw.shape[1]):
        out[:, j] = np.convolve(np.pad(raw[:, j], R, mode="edge"), g, mode="valid")
    # the depth-of-field track only: no smoothing across the hard switch to deep focus is needed, keep it smooth too
    return out


TRACKS = None


def camera(f):
    global TRACKS
    if TRACKS is None:
        TRACKS = _camera_tracks()
    cx, cy, cz, lD, az, el, fov, invf = TRACKS[min(f, N_TOTAL - 1)]
    c = np.array([cx, cy, cz]); D = math.exp(lD)
    dn = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    return dict(pos=(c + D * dn).tolist(), target=c.tolist(), fov=fov,
                fstop=(1.0 / invf if invf > 1e-4 else 0.0), focus=D, s=sim_time(f), pencil_back=pencil_back(f))


# ------------------------------------------------------------------------------------------------ overlays
FONT = "/System/Library/Fonts/Avenir Next.ttc"
F_CAP = ImageFont.truetype(FONT, 62, index=2)
F_URL = ImageFont.truetype(FONT, 40, index=5)
F_RO = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
INK = (28, 28, 30)
PANEL = (247, 245, 239); CARD_BG = (245, 242, 235); URL_INK = (60, 60, 66); RO_INK = (40, 40, 44)
RICE_MG = 20.0; CAR_KG = 1200.0
LIFT_RICE_MM = J["work_J"] / (RICE_MG * 1e-6 * 9.81) * 1000
LIFT_CAR_M = J["released_J"] / (CAR_KG * 9.81)

CAPTIONS = [
    (1.2, T_PRE + 1.4, ["How big can a", "tiny push get?"]),
    (T_PRE + 7.0, T_PRE + 11.0, ["Each domino is 1.5×", "bigger than the last."]),
    (T_LAND + 0.6, T_LAND + 2.2, [f"{N} dominoes."]),
    (T_LAND + 2.3, T_CAP_END - 0.2, ["The push could lift a grain", "of rice less than 0.01 mm."]),
    (T_LAND + 3.5, T_CAP_END - 0.2, ["The last fall could lift", f"a car {LIFT_CAR_M:.0f} metres."]),
]
SAFE = (40, 220, 940, 1540)


def fade(t, a, b, r=0.25):
    if t < a or t > b: return 0.0
    return min(1.0, (t - a) / r, (b - t) / r)


def layout(xy, lines, font, spacing=10):
    x, y = xy; out = []
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    for ln in lines:
        bb = d.textbbox((x, y), ln, font=font); out.append((ln, (x, y), bb)); y = bb[3] + spacing
    return out, y


def text_block(dr, xy, lines, font, alpha, fill=INK, spacing=10, panel=None):
    lay, y = layout(xy, lines, font, spacing)
    boxes = [bb for _, _, bb in lay]
    if panel is not None:
        pd, col = panel
        pd.rounded_rectangle((min(b[0] for b in boxes) - 18, min(b[1] for b in boxes) - 14,
                              max(b[2] for b in boxes) + 18, max(b[3] for b in boxes) + 16),
                             radius=18, fill=col[:3] + (int(col[3] * alpha),))
    for ln, (x, yy), bb in lay:
        dr.text((x, yy), ln, font=font, fill=fill + (int(255 * alpha),))
    return boxes, y


def overlay(img, f):
    """img: PIL RGB at 1080x1920"""
    t = f / FPS
    base = img.convert("RGBA")
    pan = Image.new("RGBA", base.size, (0, 0, 0, 0)); pdr = ImageDraw.Draw(pan)
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
    boxes = []; y = 262
    for a, b, lines in CAPTIONS:
        al = fade(t, a, b)
        if al > 0:
            bx, y2 = text_block(dr, (70, y), lines, F_CAP, al, panel=(pdr, PANEL + (200,)))
            boxes += bx; y = y2 + 40
    if f < N_SIM + FPS:
        s = sim_time(f)
        k = int(min(max(math.floor(front_u(s) + 1e-6), 0), N - 1))
        h = DOM[k]["h"]
        hs = f"{h*1000:.0f} mm" if h < 0.1 else (f"{h*100:.0f} cm" if h < 1 else f"{h:.1f} m")
        al = 1.0 if f < N_SIM else max(0.0, 1 - (f - N_SIM) / FPS)
        lines = [f"domino {k+1:2d}/{N}   {hs:>7s}"] + ([speed_label(s)] if f >= N_PRE else [])
        bx, _ = text_block(dr, (70, 1432), lines, F_RO, al * 0.88,
                           fill=RO_INK, spacing=8, panel=(pdr, PANEL + (160,)))
        boxes += bx
    for bb in boxes:
        assert SAFE[0] <= bb[0] and bb[2] <= SAFE[2] - 18 and SAFE[1] <= bb[1] - 14 and bb[3] + 16 <= SAFE[3], (bb, f)
    return Image.alpha_composite(Image.alpha_composite(base, pan), lay).convert("RGB")


def end_card(last_img, frame0_img, f):
    t = f / FPS - T_CARD
    bg = Image.new("RGB", (W, H), CARD_BG)
    k = min(1.0, t / 0.5); k = k * k * (3 - 2 * k)
    img = Image.blend(last_img, bg, k)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
    al = fade(t, 0.35, T_TOTAL - T_CARD - LOOP_DISSOLVE, 0.3)
    x = 72; base = 700
    for i in range(6):
        hh = 24 * 1.5 ** i; ww = hh / 2
        dr.rounded_rectangle((x, base - hh, x + ww, base), radius=max(2, ww * 0.12), fill=(18, 18, 20, int(255 * al)))
        rr = max(1.5, ww * 0.09)
        n = i + 1; top, bot = n // 2, n - n // 2
        for half, cnt in ((-1, top), (1, bot)):
            cy = base - hh / 2 + half * hh / 4
            for j in range(cnt):
                cx = x + ww / 2 + (j - (cnt - 1) / 2) * ww * 0.28
                dr.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(236, 232, 220, int(255 * al)))
        x += ww + 14
    bx, y = text_block(dr, (70, 760), ["Made by code.", "Every fall is simulated."], F_CAP, al)
    bx2, _ = text_block(dr, (70, y + 40), ["github.com/beingcognitive/unreelcode"], F_URL, al, fill=URL_INK)
    for bb in bx + bx2:
        assert SAFE[0] <= bb[0] and bb[2] <= SAFE[2] and SAFE[1] <= bb[1] and bb[3] <= SAFE[3], bb
    img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")
    td = T_TOTAL - LOOP_DISSOLVE
    if f / FPS >= td:
        q = min(1.0, (f / FPS - td) / LOOP_DISSOLVE); q = q * q * (3 - 2 * q)
        img = Image.blend(img, frame0_img, q)
    return img


def export(path):
    """camera + sim time for every frame that needs a 3D render (up to the end card)"""
    n3d = int(T_CARD * FPS)
    json.dump(dict(fps=FPS, frames=[camera(f) for f in range(n3d)], n_total=N_TOTAL), open(path, "w"))
    return n3d


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "info"
    if cmd in ("info", "json"):
        print(f"sim frames {N_SIM} ({N_SIM/FPS:.2f} s); landing at video {T_LAND:.2f} s; end card {T_CARD:.2f}; "
              f"total {T_TOTAL:.2f} s = {N_TOTAL} frames")
        print("domino starts (video s):", [round(video_time_of_sim(t), 2) for t in J["t_start"]])
        print("rate changes (video s):", [(s0, round(video_time_of_sim(s0), 2), r) for s0, r in RATES])
        print(f"push {J['work_J']*1e9:.3f} nJ -> rice {LIFT_RICE_MM:.4f} mm; fall {J['released_J']/1e6:.3f} MJ -> car {LIFT_CAR_M:.1f} m")
        print("keys D:", [(K["u"], round(K["D"], 3)) for K in KEYS])
    if cmd == "json":
        n = export(os.path.join(ROOT, os.environ.get("TL_OUT", "out/timeline.json"))); print("exported", n, "3D frames")
