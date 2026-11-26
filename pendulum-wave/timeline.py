"""Film timeline: which simulated instant each frame shows, the push board, the camera, the flashes.

After the release every pendulum angle comes straight from cache/sim.npz (one sim frame per film frame, real time).
Before it, a flat vertical board (display, kinematic) slides in along +y and pushes every bob's centre out to the
same offset X0 from the centre line; the bobs ride on it. Then it pulls back faster than any bob can follow.

  python timeline.py        # writes cache/anim.json for the Blender render, prints the timing and checks
"""
import json, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = np.load(os.path.join(HERE, "cache/sim.npz"), allow_pickle=True)
TH, L, FPS, GAMMA = SIM["theta"], SIM["L"], int(SIM["fps"]), float(SIM["gamma"])
TH0, X0 = SIM["th0"], float(SIM["x0"])
J = json.load(open(os.path.join(HERE, "out/sim.json")))
NP = len(L)
W, H = 1080, 1920
R_BOB = J["r_bob_m"]
XINGS = SIM["xings"]

# ---------------------------------------------------------------- timing (film seconds)
T_IDLE = 0.25            # all hanging still
T_IN = 0.55              # board slides in to just touch them
T_PUSH = 0.85            # pushes every bob out to the offset X0 (smoothstep)
T_HOLD = 0.35            # held
T_PRE = T_IDLE + T_IN + T_PUSH + T_HOLD          # release instant = sim t 0
T_SIM_END = GAMMA + 2.4  # last simulated instant shown: a beat on the line, then home to the frame-0 pose
T_CARD = T_PRE + T_SIM_END
T_CARD_LEN = 2.8
LOOP_DISSOLVE = 0.5
T_TOTAL = T_CARD + T_CARD_LEN
N_TOTAL = int(round(T_TOTAL * FPS))
N_3D = int(round(T_CARD * FPS))
SIMT = lambda s: T_PRE + s


def sm(x):                                      # smootherstep: zero velocity and acceleration at both ends
    x = min(max(x, 0.0), 1.0); return x * x * x * (x * (x * 6 - 15) + 10)


def sstep(x):
    x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)


def sim_time(t):
    return t - T_PRE


# ---------------------------------------------------------------- the board (display): y of its face
Y_PARK = -0.30           # where it waits, behind the row
Y_OUT = -0.95            # where it goes after the release (out of the top view)
FACE_PUSH = X0 - R_BOB   # face position that holds every bob centre at X0


def board_y(t):
    if t < T_IDLE:
        return Y_PARK
    if t < T_IDLE + T_IN:                                       # ease-out into contact with the resting bobs
        u = (t - T_IDLE) / T_IN; return Y_PARK + (-R_BOB - Y_PARK) * (1 - (1 - u) ** 3)
    if t < T_IDLE + T_IN + T_PUSH:
        return -R_BOB + (FACE_PUSH + R_BOB) * sstep((t - T_IDLE - T_IN) / T_PUSH)
    if t < T_PRE:
        return FACE_PUSH
    s = sim_time(t)
    if s < 0.45:                                                # pulls back faster than any bob can follow (checked)
        u = s / 0.45; return FACE_PUSH + (-0.52 - FACE_PUSH) * (1 - (1 - u) ** 3)
    y = -0.52 + (Y_OUT + 0.52) * sm((s - 0.45) / 1.6)
    return y + (Y_PARK - y) * sm((s - (T_SIM_END - 1.8)) / 1.6)  # back to its waiting place for the loop


def angles(f):
    t = f / FPS
    if t < T_PRE:
        y = max(0.0, board_y(t) + R_BOB)                        # every bob centre sits on the board face
        return np.arcsin(np.minimum(y / L, np.sin(TH0)))
    n = f - int(round(T_PRE * FPS))
    return TH[min(n, len(TH) - 1)]


assert abs(T_PRE * FPS - round(T_PRE * FPS)) < 1e-6, "release must fall on a frame"

# ---------------------------------------------------------------- geometry
SPACING = 0.040
ROW_X = [k * SPACING for k in range(NP)]
ZP = 0.70
C = np.array([ROW_X[-1] / 2, 0.0, 0.32])


def bob_positions(f):
    th = angles(f)
    return np.stack([np.array(ROW_X), L * np.sin(th), ZP - L * np.cos(th)], 1)


# ---------------------------------------------------------------- camera (display only)
def pose(pos, target, up, fov, fstop):
    return dict(pos=np.array(pos, float), target=np.array(target, float), up=np.array(up, float), fov=fov, fstop=fstop)


Z, X = (0, 0, 1), (1, 0, 0)
TOP_H = 6.0              # a high camera with a long lens: close to orthographic
COL_PX = 540             # the rig exactly centred


ROW_DOWN_PX = 0


def top(fov, xc=None, push=0.0, tilt_deg=0.0):
    """straight down from TOP_H (optionally tilted along the row), short end at the top of frame"""
    xc = C[0] if xc is None else xc
    xc += ROW_DOWN_PX / ((H / 2) / math.tan(math.radians(fov) / 2)) * (TOP_H - C[2])
    f = (H / 2) / math.tan(math.radians(fov) / 2)
    dist = TOP_H - C[2]
    yc = (COL_PX - W / 2) / f * dist                     # screen right is -y: shift so y = 0 lands at COL_PX
    tz = math.tan(math.radians(tilt_deg)) * (TOP_H - push)
    return pose([xc - tz, yc, TOP_H - push], [xc, yc, 0.0], X, fov, 22.0)


TOP = top(9.5)                            # the whole row, centred, with margin for a phone's UI
TOP_OUT = top(10.4)                        # where the slow zoom-out through the middle ends (same centre)
P0 = pose([-0.30, 0.46, 0.46], [0.12, -0.02, 0.34], Z, 36.0, 8.0)         # close on the long end, the board coming
PA = pose([-0.72, 0.85, 1.05], [0.42, -0.12, 0.25], Z, 50.0, 22.0)        # 3/4 view
PA2 = pose([-0.70, 0.95, 0.80], [0.45, -0.10, 0.25], Z, 50.0, 9.0)        # lower 3/4 from the long end, before the end


def sph(p):
    d = p["pos"] - C; r = np.linalg.norm(d)
    return r, math.atan2(d[1], d[0]), math.asin(max(-1.0, min(1.0, d[2] / r)))


def mix(a, b, s, pos=None):
    up = a["up"] * (1 - s) + b["up"] * s
    fa, fb = math.tan(math.radians(a["fov"]) / 2), math.tan(math.radians(b["fov"]) / 2)
    return dict(pos=(a["pos"] * (1 - s) + b["pos"] * s) if pos is None else pos,
                target=a["target"] * (1 - s) + b["target"] * s, up=up / np.linalg.norm(up),
                fov=2 * math.degrees(math.atan(math.exp(math.log(fa) * (1 - s) + math.log(fb) * s))),
                fstop=math.exp(math.log(a["fstop"]) * (1 - s) + math.log(b["fstop"]) * s))


def orbit(a, b, s):
    """move about C in spherical coordinates (a crane/orbit), blending target, up, fov and f-stop"""
    ra, aa, ea = sph(a); rb, ab, eb = sph(b)
    if eb > math.radians(80): ab = aa
    if ea > math.radians(80): aa = ab
    r = math.exp(math.log(ra) * (1 - s) + math.log(rb) * s)
    az, el = aa + (ab - aa) * s, ea + (eb - ea) * s
    pos = C + r * np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    return mix(a, b, s, pos)


CHAPTERS = [(15.0, 4), (20.0, 3), (30.0, 2), (40.0, 3), (45.0, 4), (60.0, 1)]    # still moments (no labels)
MOVES = [  # (film start, film end, from, to, how); a hold is from == to
    (0.00, 0.35, P0, P0, mix),
    (0.35, 1.90, P0, PA, mix),                    # pull back as the board pushes
    (1.90, SIMT(5.0), PA, PA, mix),               # the release and the first crossings of the line
    (SIMT(5.0), SIMT(9.6), PA, TOP, orbit),       # crane up to straight down
    (SIMT(9.6), SIMT(46.4), TOP, TOP_OUT, mix),   # one very slow, monotonic zoom-out (no zoom-in): 9.5 -> 10.4 deg
    (SIMT(46.4), SIMT(49.4), TOP_OUT, PA2, orbit),   # down to a low 3/4 view of the tangle
    (SIMT(49.4), SIMT(52.6), PA2, PA2, mix),
    (SIMT(52.6), SIMT(60.0), PA2, TOP, orbit),      # back up; settles straight down exactly at t = 60.00
    (SIMT(60.0), SIMT(61.0), TOP, TOP, mix),        # still on the line
    (SIMT(61.0), T_CARD, TOP, P0, orbit),           # home to the frame-0 pose (the end card then dissolves into frame 0)
]


def camera(f):
    t = f / FPS
    p = None
    for t0, t1, a, b, how in MOVES:
        if t <= t1 + 1e-9:
            p = how(a, b, sm((t - t0) / (t1 - t0)) if t1 > t0 else 1.0); break
    if p is None: p = mix(TOP, TOP, 0)
    fwd = p["target"] - p["pos"]
    return dict(pos=p["pos"].tolist(), target=p["target"].tolist(), up=p["up"].tolist(), fov=float(p["fov"]),
                fstop=float(p["fstop"]), focus=float(np.linalg.norm(fwd)))


def project(cam, P):
    p = np.array(cam["pos"]); fwd = np.array(cam["target"]) - p; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, cam["up"]); right /= np.linalg.norm(right); up = np.cross(right, fwd)
    d = P - p; z = d @ fwd
    fpx = (H / 2) / math.tan(math.radians(cam["fov"]) / 2)
    return W / 2 + fpx * (d @ right) / z, H / 2 - fpx * (d @ up) / z, fpx / z


# ---------------------------------------------------------------- flashes: each crossing of the centre line
TAU_FLASH = 0.05         # fast fade: no trail of spots lingers after a crossing


def flashes(f):
    t = sim_time(f / FPS); out = np.zeros(NP)
    if t <= 0: return out
    for k in range(NP):
        xs = XINGS[k]
        past = xs[(xs[:, 0] <= t) & (xs[:, 0] > t - 6 * TAU_FLASH), 0]
        if len(past): out[k] = min(1.0, float(np.sum(np.exp(-(t - past) / TAU_FLASH))))
        if out[k] < 0.02: out[k] = 0.0
    return out


def check_board():
    """after the release no bob may touch the board: min over bobs of (bob centre y - R) - face y, over the pull-back"""
    worst = 1e9
    for n in range(1, int(2.2 * FPS * 20)):
        s = n / (FPS * 20); fi = s * FPS; i0 = int(fi); w = fi - i0
        th = TH[i0] * (1 - w) + TH[i0 + 1] * w
        worst = min(worst, float(np.min(L * np.sin(th) - R_BOB - board_y(T_PRE + s))))
    return worst * 1000


if __name__ == "__main__":
    margin = check_board()
    print(f"release at {T_PRE:.2f} s (frame {int(round(T_PRE*FPS))}); realign at {T_PRE+GAMMA:.2f} s; "
          f"end card {T_CARD:.2f}; total {T_TOTAL:.2f} s = {N_TOTAL} frames, 3D frames {N_3D}")
    print(f"board clearance after the release: {margin:.2f} mm (must be > 0)")
    assert margin > 0
    p0 = bob_positions(int(round(T_PRE * FPS)))
    print("offsets at release (mm):", np.round(p0[:, 1] * 1000, 6).min(), np.round(p0[:, 1] * 1000, 6).max())
    frames = [dict(th=[float(v) for v in angles(f)], board_y=board_y(f / FPS), flash=[round(float(v), 4) for v in flashes(f)],
                   **camera(f)) for f in range(N_3D)]
    json.dump(dict(fps=FPS, frames=frames, L=[float(v) for v in L], row_x=ROW_X, zp=ZP), open(os.path.join(HERE, "cache/anim.json"), "w"))
    print("wrote cache/anim.json")
