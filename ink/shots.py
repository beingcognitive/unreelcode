"""shots.py -- the scenes (v2: native 1080x1920 vertical tank; splat radii x0.58 keep the old pixel sizes). Each shot = solver constants + initial state + injectors + look.

All motion comes from the solver in shaders/ink.glsl. Injectors (pipettes / jets) add ink
and momentum at fixed places, like a nozzle in a tank. Times are seconds of shot time.
"""
import numpy as np

FPS = 24


def noise_vel(f, rng, amp, smooth=6):
    """small smooth random velocity to seed instabilities (water is never perfectly still)"""
    from scipy.ndimage import gaussian_filter
    v = rng.normal(0, 1, (f.VH, f.VW, 2))
    v[..., 0] = gaussian_filter(v[..., 0], smooth, mode="wrap")
    v[..., 1] = gaussian_filter(v[..., 1], smooth, mode="wrap")
    v *= amp / (v.std() + 1e-9)
    f.set_vel(v)


# ---------------------------------------------------------------- 1: hook
def hook_init(f, rng):
    noise_vel(f, rng, 2.0)


def hook_drive0(f, t, dt, rng):
    pass


def hook_drive(f, t, dt, rng):
    # a pipette squeezed hard, just above frame, then released
    if t < 3.0:
        k = 1.0 if t < 2.2 else (3.0 - t) / 0.8
        k *= 0.75 + 0.25 * np.sin(t * 2 * np.pi * 1.6) ** 2
        wob = 0.015 * np.sin(t * 5.0) + 0.006 * np.sin(t * 17.0)
        a, b = rng.uniform(0.0, 1.0, 2) ** 2
        f.splat((0.46 + wob, 1.0), 0.0093, vel=(rng.normal(0, 60), -520 * k), ink=(0.5 * a * k, 0.35 * b * k, 0, 0))


HOOK = dict(
    consts={"CURL": "1.5", "SINK": "40.0"}, init=hook_init, drive=hook_drive,
    preroll=1.8, frames=120, substeps=2, grid=(540, 960),
    look=dict(
        pig=[(1.0, 0.30, 0.10), (1.0, 0.62, 0.22), (0.2, 0.6, 1.0), (0.8, 0.8, 0.85)],
        absb=[(0.55, 3.0, 4.2), (0.2, 1.1, 3.2), (2.5, 1.2, 0.4), (1, 1, 1)],
        blcol=(1.35, 1.0, 0.68), blpos=(0.55, 0.62, 0.5), rim=0.0, bg0=(0.01, 0.006, 0.004), bg1=(0.02, 0.012, 0.008),
        lcol=(0.12, 0.08, 0.05), ldir=(0.0012, 0.0022), bump=2.0, opac=0.7, deep=0.35, view=(0.0, 0.0, 1.0, 1.0),
    ),
)

SHOTS = {"hook": HOOK}


# ---------------------------------------------------------------- the code, as ink
TEXT_LOOK = dict(
    pig=[(0.1, 0.1, 0.12)] * 4,
    absb=[(2.3, 2.1, 1.6), (0.5, 2.8, 3.9), (0.25, 1.2, 3.4), (1.1, 1.0, 0.8)],
    blcol=(1.30, 1.08, 0.82), blpos=(0.5, 0.55, 0.62), rim=0.0,
    bg0=(0.012, 0.01, 0.008), bg1=(0.02, 0.016, 0.012),
    lcol=(0.06, 0.05, 0.04), bump=1.5, opac=0.7, deep=0.3, vign=0.45,
    view=(0.0, 0.0, 1.0, 1.0),
)
TEXT_CONSTS = {"CURL": "0.0", "SINK": "30.0"}


def code_init(f, rng):
    from text import Layout, excerpt
    lay = Layout(f.DW, f.DH, f.DH)
    f.set_dye(lay.render(excerpt(f.source)))
    noise_vel(f, rng, 22.0, smooth=35)


CODE_A = dict(consts=TEXT_CONSTS, init=code_init, drive=lambda *a: None,
              preroll=0.0, frames=180, substeps=2, grid=(540, 960), look=TEXT_LOOK)
SHOTS["codeA"] = CODE_A


# ---------------------------------------------------------------- B: hold, edit one line, release
B_PAUSE = 5.0                      # seconds of held frame (sim paused)
EDIT_NAME, EDIT_NEW = "SINK", "-30.0"   # one line changes: the ink becomes lighter than water
B_EDIT = [1.25 + i * 0.15625 for i in range(9)]          # 16th notes at 96 BPM: 4 deletes, 5 keystrokes
C_OLD, C_NEW = "heavier", "lighter"                      # v2: the comment is retyped too, so it stays true
C_EDIT = [2.75 + i * 0.078125 for i in range(14)]        # 32nd notes: 7 deletes, 7 keystrokes
EDITED_SOURCE = None


def _typed(old, new, k):
    nd = min(k, len(old))
    na = max(0, k - len(old))
    return old[:len(old) - nd] + new[:na]


def codeB_init(f, rng):
    from text import Layout, excerpt
    f.lay = Layout(f.DW, f.DH, f.DH)
    f.rows = excerpt(f.source)
    f.set_dye(f.lay.render(f.rows))
    noise_vel(f, rng, 6.0, smooth=35)
    f.edited = False
    f.shown = None


def edit_rows(rows, T):
    """the rows as they read at hold time T (value retyped on 16ths, then the comment on 32nds)"""
    rows = list(rows)
    r = next(i for i, (_, l) in enumerate(rows) if l.startswith(f"const float {EDIT_NAME}"))
    line = rows[r][1]
    c0 = line.index("=") + 2
    old = line[c0:line.index(";")]
    k = sum(T >= x for x in B_EDIT)
    rows[r] = (rows[r][0], line[:c0] + _typed(old, EDIT_NEW, k) + line[c0 + len(old):])
    rc = r - 1
    cl = rows[rc][1]
    assert C_OLD in cl
    i0 = cl.index(C_OLD)
    kc = sum(T >= x for x in C_EDIT)
    rows[rc] = (rows[rc][0], cl[:i0] + _typed(C_OLD, C_NEW, kc) + cl[i0 + len(C_OLD):])
    done = k >= len(old) + len(EDIT_NEW) and kc >= 2 * len(C_OLD)
    return rows, done


def codeB_frame(f, T, rng):
    """during the pause: retype the SINK value and its comment, one keystroke per 16th/32nd note (ink re-set in
    the paused tank: a guided/composited edit, not a simulated one). Then recompile from the new text."""
    global EDITED_SOURCE
    if T >= B_PAUSE or f.edited:
        return
    rows, done = edit_rows(f.rows, T)
    if rows != f.shown:
        f.set_dye(f.lay.render(rows))
        f.shown = rows
    if done:
        # the edited lines are now the file: recompile the solver from exactly this text
        from ink import SRC, patch
        consts = dict(TEXT_CONSTS)
        consts[EDIT_NAME] = EDIT_NEW
        src = patch(SRC, consts).replace(f"// ink is {C_OLD} than water", f"// ink is {C_NEW} than water")
        f.compile(consts, source=src)
        for _, l in rows:
            assert l in f.source.split("\n"), ("shown text must equal compiled source", l)
        EDITED_SOURCE = f.source
        f.edited = True


def _rows_rect(f, which):
    """tank-uv rect (x0, y0, x1, y1; y up) around excerpt rows `which`"""
    L = f.lay
    x0 = L.x0 - 18
    x1 = L.x0 + L.maxc * L.cw + 18
    ya = L.y0 + min(which) * L.lh - 12
    yb = L.y0 + (max(which) + 1) * L.lh + 4
    return (x0 / f.DW, 1 - yb / f.DH, x1 / f.DW, 1 - ya / f.DH)


def codeB_look_f(f):
    rows = f.rows
    r = next(i for i, (_, l) in enumerate(rows) if l.startswith(f"const float {EDIT_NAME}"))
    rect = _rows_rect(f, [r - 1, r])
    cy = 0.5 * (rect[1] + rect[3])
    cx = 0.5 * (rect[0] + rect[2])

    def look(T):
        L = dict(TEXT_LOOK)
        # display-only camera: push in on the edited lines during the hold, back out for the release
        zin = min(1.0, max(0.0, (T - 0.2) / 0.9))
        zout = min(1.0, max(0.0, (T - 4.15) / 0.8))
        u = zin * (1 - zout)
        u = u * u * (3 - 2 * u)
        z = 1.0 - 0.17 * u                       # the whole line block stays in frame
        ccx = 0.5 + (cx - 0.5) * u
        ccy = 0.5 + (cy - 0.5) * u
        L["view"] = (ccx - 0.5 * z, ccy - 0.5 * z, z, z)
        v = L["view"]
        L["hl"] = ((rect[0] - v[0]) / z, (rect[1] - v[1]) / z, (rect[2] - v[0]) / z, (rect[3] - v[1]) / z)
        L["hlk"] = u
        return L
    return look


CODE_B = dict(consts=TEXT_CONSTS, init=codeB_init, drive=lambda *a: None, hook_frame=codeB_frame,
              paused=lambda T: T < B_PAUSE, preroll=0.0, frames=420, substeps=2, grid=(540, 960),
              look_f=codeB_look_f, seed=7)
SHOTS["codeB"] = CODE_B


VIEW = (0.0, 0.0, 1.0, 1.0)


def look(**kw):
    L = dict(rim=0.0, bg0=(0.01, 0.006, 0.004), bg1=(0.02, 0.012, 0.008), lcol=(0.12, 0.08, 0.05),
             bump=2.0, opac=0.7, deep=0.35, view=VIEW)
    L.update(kw)
    return L


# ---------------------------------------------------------------- 2: Rayleigh-Taylor (indigo layer falls)
def rt_init(f, rng):
    from scipy.ndimage import gaussian_filter
    H, W = f.DH, f.DW
    y = np.arange(H)[:, None] / H
    x = np.arange(W)[None, :] / W
    wav = 0.007 * gaussian_filter(rng.normal(0, 1, W), 10, mode="wrap")[None, :] * 4
    edge = 0.80 + wav
    m = 1 / (1 + np.exp(-(y - edge) * 400))
    d = np.zeros((H, W, 4), np.float32)
    band = 0.5 + 0.5 * np.sin(x * 23 + 2 * np.sin(x * 7))
    d[..., 0] = m * (1.2 + 0.6 * band)
    d[..., 1] = m * 0.9 * (1 - band)
    f.set_dye(d)
    noise_vel(f, rng, 3.0, smooth=4)


RT = dict(consts={"CURL": "0.8", "SINK": "45.0"}, init=rt_init, drive=lambda *a: None,
          preroll=0.9, frames=120, substeps=2, grid=(540, 960), seed=3,
          look=look(absb=[(2.6, 1.6, 0.35), (2.2, 0.5, 0.25), (0, 0, 0), (0, 0, 0)],
                    blcol=(0.95, 1.08, 1.3), blpos=(0.48, 0.5, 0.55),
                    bg0=(0.004, 0.006, 0.01), bg1=(0.008, 0.01, 0.016)))
SHOTS["rt"] = RT


# ---------------------------------------------------------------- 3: two jets collide (magenta vs teal)
def clash_drive(f, t, dt, rng):
    if t < 4.0:
        w = 0.8 + 0.2 * np.sin(t * 3.1)
        # v2: the jets come from the top and the bottom of the tall tank and meet in the middle
        f.splat((0.47 + 0.03 * np.sin(t * 2.3), 1.0), 0.0116, vel=(rng.normal(0, 30), -420 * w),
                ink=(0.45 * rng.uniform() ** 2, 0, 0, 0))
        f.splat((0.53 + 0.03 * np.sin(t * 1.7), 0.0), 0.0116, vel=(rng.normal(0, 30), 420 * w),
                ink=(0, 0.45 * rng.uniform() ** 2, 0, 0))


CLASH = dict(consts={"CURL": "1.0", "SINK": "8.0"}, init=lambda f, r: noise_vel(f, r, 2.0),
             drive=clash_drive, preroll=1.6, frames=120, substeps=2, grid=(540, 960), seed=5,
             look=look(absb=[(0.4, 2.8, 0.9), (2.8, 0.45, 0.6), (0, 0, 0), (0, 0, 0)],
                       blcol=(1.25, 1.12, 1.0), blpos=(0.5, 0.6, 0.6)))
SHOTS["clash"] = CLASH


# ---------------------------------------------------------------- 4: drops on the beat (sumi + gold)
BEAT = 60 / 96


def drops_drive(f, t, dt, rng):
    # v2 fix: a beat line falls inside this step (the old exact-match test never fired once the 1.3 s pre-roll
    # put the clock off the beat grid, so v1's drops shot was empty)
    k = int(np.floor((t + dt) / BEAT))
    if k > int(np.floor(t / BEAT)) and k >= -1:
        r = np.random.default_rng(100 + k)
        x = 0.15 + 0.7 * r.uniform()
        gold = k % 3 == 1
        y = 0.97 - 0.5 * r.uniform() ** 1.5          # v2: the pipette tip goes in at different depths of the tall tank
        f.splat((x, y), 0.028, vel=(0, -420), ink=(0, 1.6, 0, 0) if gold else (1.8, 0, 0, 0))


DROPS = dict(consts={"CURL": "1.0", "SINK": "35.0"}, init=lambda f, r: noise_vel(f, r, 2.0),
             drive=drops_drive, preroll=2.6, frames=120, substeps=2, grid=(540, 960), seed=9,
             look=look(absb=[(2.0, 1.9, 1.7), (0.15, 0.8, 2.6), (0, 0, 0), (0, 0, 0)],
                       blcol=(1.3, 1.1, 0.85), blpos=(0.5, 0.58, 0.55)))
SHOTS["drops"] = DROPS


# ---------------------------------------------------------------- final: three inks pour together
def bloom_drive(f, t, dt, rng):
    if t < 9.0:
        for i, (x, c) in enumerate([(0.3, 0), (0.5, 1), (0.7, 2)]):
            ph = t * (1.3 + 0.2 * i) + i
            ink = [0, 0, 0, 0]
            ink[c] = 0.35 * rng.uniform() ** 2
            f.splat((x + 0.02 * np.sin(ph), 1.0), 0.0081, vel=(rng.normal(0, 50), -380), ink=tuple(ink))


BLOOM = dict(consts={"CURL": "1.0", "SINK": "30.0"}, init=lambda f, r: noise_vel(f, r, 2.0),
             drive=bloom_drive, preroll=0.6, frames=360, substeps=2, grid=(540, 960), seed=11,
             look=look(absb=[(0.55, 3.0, 4.2), (2.6, 1.6, 0.35), (0.15, 0.8, 2.6), (0, 0, 0)],
                       blcol=(1.3, 1.08, 0.85), blpos=(0.5, 0.58, 0.55)))
SHOTS["bloom"] = BLOOM
