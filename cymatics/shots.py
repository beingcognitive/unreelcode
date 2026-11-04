"""Camera plan.  cam = (eye, target, fov, focus_dist, aperture_px, exposure, lens_shift, glint).

v3.1 film timing: the film opens 22 frames after the bar-1 strike (sim 22/30 s), when the first figure has formed,
and bar 10 (sim 23.0-25.5 s, the still-flat dish) is cut from picture and sound together."""
import math
import numpy as np
FPS = 30
FILM0 = 22 / 30                  # film time 0 = sim time FILM0
CUT = (23.0, 25.5)               # bar 10, removed
def film_t(t):
    """sim time -> film time"""
    return t - FILM0 - (CUT[1] - CUT[0] if t >= CUT[1] else 0.0)
DUR = film_t(60.0)               # 56.767 s

def ease(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def lerp(a, b, u): return tuple(np.array(a) * (1 - u) + np.array(b) * u)
def orbit(r, h, ang, tgt=(0, 0, 0)):
    a = np.radians(ang); return (tgt[0] + r * np.cos(a), tgt[1] + r * np.sin(a), h)

BACK = (-0.35, 0.92, -0.2)      # raking key from behind-right
SIDE = (-0.95, 0.25, -0.18)
# name, t0, t1, light, fn(u, t) -> (eye, target, fov, focus_point, aperture, exposure, shift, glint)
# v3: cameras re-framed for a vertical 1080x1920 frame (fov is the vertical field of view)
def s1(u, t):
    e = lerp((0.78, -1.50, 1.10), (0.52, -1.02, 0.78), ease(u)); g = lerp((0.04, 0.10, 0), (0.0, 0.02, 0), u)
    return e, g, 50, (0.0, -0.15, 0), 9, 1.5, (0, 0), 3.0
def s2(u, t):
    # v3.2: a little higher and sharper (the extreme low macro read as hair at phone size)
    e = lerp((0.34, -0.66, 0.32), (0.26, -0.55, 0.26), ease(u))
    return e, (0.10, -0.15, 0), 38, (0.13, -0.24, 0), 12, 1.6, (0, 0), 3.0
def s3(u, t):
    # v3.1: a slow rotation and push-in, so the top-down view is not static
    return orbit(0.0001, 3.1, 14 * ease(u)), (0, 0.0002, 0), 60 - 7 * ease(u), (0, 0, 0), 2, 1.6, (0, 0), 3.0
def s4(u, t):
    # v3: was a dark low slide under a side key; now a back-lit three-quarter travel, so the ridges glint
    e = lerp((-1.05, -1.35, 1.05), (-0.15, -1.55, 0.92), ease(u))
    return e, lerp((-0.12, 0.05, 0), (0.18, 0.05, 0), ease(u)), 48, lerp((-0.3, -0.25, 0), (0.05, -0.3, 0), ease(u)), 10, 1.9, (0, 0), 3.5
def s5(u, t):
    return orbit(1.45, 2.45, -110 + 45 * ease(u)), (0, 0.06, 0), 50, (0, 0, 0), 5, 1.55, (0, 0), 3.0
def s6(u, t):
    # v3.2: the rest bar: the motionless figure, well lit from a high three-quarter view, slow push-in
    e = lerp((0.62, -1.30, 1.55), (0.45, -1.00, 1.20), ease(u))
    return e, (0.0, 0.05, 0), 48, (0.0, -0.1, 0), 6, 1.9, (0, 0), 3.5
def c1(u, t):
    # top-down. v3.2: the plate is 74-80 % of the frame width (800 -> 864 px, a slow push-in) and its bottom edge
    # stays above y 1540 (the platform's caption overlay); no turn, so its corners stay put
    z = 2.877 - 0.213 * u
    return (0, -0.0001, z), (0, 0, 0), 79.7, (0, 0, 0), 2, 1.6, (0, 0.150), 3.0
def f1(u, t):
    uu = ease(min(u * 1.35, 1))
    # v3.2: the crane ends closer and steeper, so the plate fills the frame's width at every row (from further back
    # its receding sides showed as dark wedges at the top corners)
    e = lerp((0.36, -0.60, 0.17), (0.0, -0.95, 2.30), uu)
    g = lerp((0.10, -0.12, 0), (0, 0.05, 0), uu)
    # after the crane, keep moving so the end card is not frozen: a straight slow dolly in
    v = ease((u - 0.62) / 0.38)
    e = (e[0], e[1] + 0.10 * v, e[2] - 0.20 * v)
    return e, g, lerp((34,), (52,), uu)[0], \
        lerp((0.15, -0.2, 0), (0, 0, 0), uu), 26 * (1 - uu) + 3, 1.55, (0, 0), 3.0

SHOTS = [('s1', 0.0, 5.5, BACK, s1), ('s2', 5.5, 8.0, BACK, s2), ('s3', 8.0, 10.5, SIDE, s3),
         ('s4', 10.5, 15.5, BACK, s4), ('s5', 15.5, 20.5, SIDE, s5), ('s6', 20.5, 23.0, BACK, s6),
         ('c1', 35.5, 45.5, SIDE, c1), ('f1', 45.5, 60.0, BACK, f1)]

def cam_at(fn, t0, t1, t):
    e, g, fov, fp, ap, ex, sh, gl = fn((t - t0) / (t1 - t0), t)
    focus = float(np.linalg.norm(np.array(fp) - np.array(e)))
    return (e, g, fov, focus, ap, ex, sh, gl)
