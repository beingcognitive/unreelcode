"""One clock for picture and sound (v7). 30 fps, 120 BPM in 4/4: one bar is 2 s; every beat starts on a bar line.
The rig stands vertically: lamp above, the glass, the light on the floor D = 0.50 m below the glass."""
import os, numpy as np

FPS = 30
BAR = 2.0
DUR = 28.0
NF = int(DUR * FPS)
D = 0.50
SWEEP_T = 22.0                                 # bar 12: the face, sharp for the first time (the reveal)
SETUP_D = 0.50                                 # the glass's height in the setup shot (the camera stays focused on the glass)
FOLD_D = 0.95                                  # variant a starts here (ease-in-out down to D)
SWEEP = os.environ.get("SWEEP", "b")              # b (the film): brisk 110->95 cm, slow 95->62, accelerating into focus; a: ease-in-out from 95 cm
SUFFIX = "" if SWEEP == "a" else "_" + SWEEP

SHOTS = [  # (name, t0, t1)
    ("hook",   0.0,  4.0),    # bars 1-2   light through water (sum of 5 sines), traced
    ("setup",  4.0,  8.0),    # bars 3-4   3/4 view of the rig, real rays; the floor light stays soft (focus on the glass)
    ("proof",  8.0, 12.0),    # bars 5-6   the glass alone: clear; a real cut through its surface
    ("sweep", 12.0, 22.0),    # bars 7-11  the glass from 110 cm down to 50 cm: folded light -> the face (the reveal)
    ("code",  22.0, 25.0),    # bar 12 + half of 13: a 1 s hold, then the code card (~2 s)
    ("end",   25.0, 28.0),    # half of bar 13 + bar 14: end card 3.0 s, its last 0.5 s dissolving into frame 0
]
LOOP = 0.5


def ease(x):
    x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)


def shot_at(t):
    for s in SHOTS:
        if s[1] <= t < s[2]: return s
    return SHOTS[-1]


def wall_d(t):
    """distance from the glass to the floor (m). The setup shows the glass 50 cm up. The sweep (v7) is one smooth
    ease-in-out from 95 cm to 50 cm over 10 s: it starts gently, is fastest in the middle and settles softly, sharp on
    the bar-12 downbeat (22 s). It starts at 95 cm because the ease-in lingers at the start, and 95 cm is the highest
    clean state (a fold line with bright blobs); 100-110 cm shows a pointed cusp between wing-like folds and from
    ~115 cm a central upright column, so those heights are not used."""
    if t < 12.0: return SETUP_D
    if t >= SWEEP_T: return D
    if SWEEP == "b":                       # the click: brisk 110 -> 95 cm, slow 95 -> 62 cm, accelerating 62 -> 50 cm
        if t < 12.8:
            u = (t - 12.0) / 0.8; return 1.10 + (FOLD_D - 1.10) * (u * (2 - u) * 0.6 + u * 0.4)
        if t < 20.6: return FOLD_D + (0.62 - FOLD_D) * ((t - 12.8) / 7.8)
        u = (t - 20.6) / (SWEEP_T - 20.6); return 0.62 + (D - 0.62) * u ** 1.8
    return FOLD_D + (D - FOLD_D) * ease((t - 12.0) / (SWEEP_T - 12.0))


def beam(t):
    """the lamp stays straight in v4 (v3's tilt beat was cut)"""
    return (0.0, 0.0)


def bar(t): return int(t // BAR) + 1
