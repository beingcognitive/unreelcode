"""The score, synthesised in code (numpy + scipy). v7: 120 BPM, 4/4, one bar = 2 s, 14 bars, D major.

How the picture drives it: render.py measures, for every frame, how much the traced light on the wall looks like
the face (`sharp`, the correlation in stats.json). That one number, normalised to 0..1 over the film and smoothed,
sets
  - how out of tune the glass pad's two voices are (25 cents apart when the light is a blur, 2 cents in focus),
  - a quiet half-step "wrong note" under the pad, which fades out as the face resolves,
  - the pad's brightness (upper harmonics),
  - which glass-bell notes play: the downbeat always, the other beats only as the image sharpens.
Pitches come from the chord of each bar, never from the picture. Fixed events: a bell chord, a sub swell and a
shimmer on the downbeat where the face first comes into focus (bar 12, 22 s). The build across the sweep
follows the glass's descent P (0 at 95 cm, 1 at 50 cm): it opens the pad's harmonics, fills in the bells, and swells
a filtered-noise riser that stops at the face, a soft tick as each code line appears.

    python music.py   -> cache/mix_raw.npy (then master.py)
"""
import json, numpy as np
from pathlib import Path
from scipy.signal import fftconvolve, butter, sosfilt
from scipy.ndimage import uniform_filter1d
import timeline as T

ROOT = Path(__file__).parent
SR = 48000
TAIL = 4.0                                    # rendered past the end, then wrapped onto the start (seamless loop)
N = int(SR * (T.DUR + TAIL))
t = np.arange(N) / SR
rng = np.random.default_rng(5)
L = np.zeros(N); R = np.zeros(N)

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}
def hz(name, octave): return 440.0 * 2 ** ((NOTE[name] + 12 * (octave + 1) - 69) / 12)

CHORDS = [  # bar (2 s) -> (bass, pad tones)   v7: 14 bars (28 s)
    ("G", [("G", 3), ("B", 3), ("D", 4), ("F#", 4), ("A", 4)]),    # 1  hook: light through water
    ("E", [("E", 3), ("G", 3), ("B", 3), ("D", 4), ("F#", 4)]),    # 2
    ("C", [("C", 3), ("E", 3), ("G", 3), ("B", 3), ("F#", 4)]),    # 3  setup
    ("A", [("A", 2), ("D", 3), ("E", 3), ("G", 3), ("B", 3)]),     # 4  "...into a face."
    ("G", [("G", 2), ("D", 3), ("F#", 3), ("B", 3), ("D", 4)]),    # 5  proof: the glass is blank
    ("A", [("A", 2), ("C#", 3), ("E", 3), ("A", 3), ("E", 4)]),    # 6
    ("C", [("C", 3), ("E", 3), ("G", 3), ("B", 3), ("F#", 4)]),    # 7  sweep: the glass comes down, folds
    ("E", [("E", 3), ("G", 3), ("B", 3), ("D", 4), ("F#", 4)]),    # 8
    ("C", [("C", 3), ("G", 3), ("B", 3), ("E", 4), ("A", 4)]),     # 9
    ("E", [("E", 2), ("B", 2), ("E", 3), ("G", 3), ("D", 4)]),     # 10 the folds collapse
    ("A", [("A", 2), ("D", 3), ("E", 3), ("G", 3), ("B", 3)]),     # 11 almost
    ("D", [("D", 3), ("F#", 3), ("A", 3), ("E", 4), ("F#", 4)]),   # 12 THE FACE (22 s); hold and code
    ("B", [("B", 2), ("D", 3), ("F#", 3), ("A", 3), ("D", 4)]),    # 13 code -> end card (25 s)
    ("G", [("G", 3), ("B", 3), ("D", 4), ("F#", 4), ("A", 4)]),    # 14 end card -> loops into bar 1 (the same chord)
]
BELLS = [  # per bar: four quarter notes from the bar's chord
    ["D5", "A5", "F#5", "B5"], ["B4", "G5", "E5", "F#5"], ["E5", "B5", "G5", "F#5"], ["E5", "A5", "D5", "B4"],
    ["D5", "B5", "G5", "F#5"], ["E5", "C#6", "A5", "E5"], ["E5", "B5", "G5", "F#5"], ["B4", "G5", "E5", "F#5"],
    ["E5", "B5", "G5", "A5"], ["B4", "G5", "E5", "D6"], ["E5", "A5", "D5", "B5"], ["F#5", "A5", "D6", "E6"],
    ["F#5", "D5", "B5", "A5"], ["D5", "A5", "F#5", "B5"],
]
def parse(n): return hz(n[:-1], int(n[-1]))


def sharp_curve():
    st = json.loads((ROOT / "cache" / f"stats{T.SUFFIX}.json").read_text())
    fr = np.array(sorted(int(k) for k in st))
    s = np.array([st[str(i)]["sharp"] for i in fr])
    s = (s - s.min()) / (s.max() - s.min())
    tf = fr / T.FPS
    x = np.interp(t, tf, s, right=s[0])                               # past the end: the loop's start
    return np.clip(uniform_filter1d(x, int(0.35 * SR)), 0.0, 1.0), s, tf     # clamp: rounding can leave 1 + 1e-16


S, S_frames, TF = sharp_curve()


def descent_curve():
    """the sweep's progress from the glass's height: 0 at 95 cm (or higher), 1 at 50 cm; 0 outside the sweep"""
    d = np.array([T.wall_d(x) for x in np.arange(0, T.DUR + TAIL, 1 / T.FPS)])
    tt = np.arange(len(d)) / T.FPS
    p = np.clip((T.FOLD_D - d) / (T.FOLD_D - T.D), 0, 1) * ((tt >= 12.0) & (tt < T.SWEEP_T))
    return uniform_filter1d(np.interp(t, tt, p), int(0.2 * SR))


P = descent_curve()


def add(sig, i0, pan=0.0, g=1.0):
    if i0 < 0: sig, i0 = sig[-i0:], 0
    i1 = min(N, i0 + len(sig)); sig = sig[:i1 - i0]
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    L[i0:i1] += sig * l * g * 1.414; R[i0:i1] += sig * r * g * 1.414


def env_ar(n, a, r, hold):
    u = np.arange(n) / SR
    e = np.clip(u / a, 0, 1) ** 2
    return e * np.where(u > hold, np.exp(-(u - hold) / r), 1.0)


def pad():
    for b, (_, tones) in enumerate(CHORDS):
        t0 = b * T.BAR - 0.35
        n = int((T.BAR + 3.0) * SR); i0 = int(t0 * SR)
        sl = S[max(i0, 0): max(i0, 0) + n]; sl = np.pad(sl, (n - len(sl) if i0 < 0 else 0, 0), mode="edge")
        sl = np.pad(sl, (0, n - len(sl)), mode="edge")
        u = np.arange(n) / SR
        env = env_ar(n, 0.6, 0.8, T.BAR + 0.35)
        cents = 2 + 23 * (1 - sl)
        pl = P[max(i0, 0): max(i0, 0) + n]; pl = np.pad(pl, (n - len(pl) if i0 < 0 else 0, 0), mode="edge")
        pl = np.pad(pl, (0, n - len(pl)), mode="edge")
        bright = 0.25 + 0.75 * np.maximum(sl, pl)                      # the build opens the pad as the glass comes down
        for name, octv in tones:
            f = hz(name, octv)
            for side, sgn in ((0, -1), (1, 1)):
                fdet = f * 2 ** (sgn * cents / 2 / 1200)
                ph = 2 * np.pi * np.cumsum(fdet) / SR + rng.uniform(0, 6.3)
                sig = np.sin(ph) + bright * (0.30 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph) + 0.05 * np.sin(4 * ph))
                sig *= 1 + 0.06 * np.sin(2 * np.pi * (0.21 + 0.05 * side) * u + side)
                add(0.045 * env * sig, i0, -1.0 if side == 0 else 1.0, 1 / 1.414)
        # the wrong note: a half step above the root, an octave up, fading as the light comes into focus
        f = hz(CHORDS[b][0], 4) * 2 ** (1 / 12)
        wn = np.sin(2 * np.pi * f * u + 1.0) * (1 - sl) ** 1.5 * env * 0.035
        add(wn, i0, 0.25)


def bass():
    for b, (root, _) in enumerate(CHORDS):
        f = hz(root, 2) if hz(root, 2) > 60 else hz(root, 3)
        n = int((T.BAR + 1.5) * SR); u = np.arange(n) / SR
        env = env_ar(n, 0.4, 0.6, T.BAR - 0.2)
        add(env * (np.sin(2 * np.pi * f * u) + 0.25 * np.sin(4 * np.pi * f * u + 0.4)), int(b * T.BAR * SR), 0, 0.11)


GLASS = [(1.0, 1.0, 3.2), (2.0, 0.22, 1.6), (3.0, 0.07, 0.9), (4.16, 0.06, 0.55), (5.43, 0.035, 0.35), (7.0, 0.015, 0.2)]


def bell(f, vel):
    n = int(4.0 * SR); u = np.arange(n) / SR
    s = np.zeros(n)
    for r, a, tau in GLASS:
        if f * r > 17000: continue
        s += a * np.exp(-u / tau) * np.sin(2 * np.pi * f * r * u * (1 + rng.normal(0, 0.0004)) + rng.uniform(0, 6))
    s *= np.clip(u / 0.004, 0, 1)
    return vel * s


THRESH = [0.0, 0.85, 0.40, 0.65]            # per quarter: how sharp the light must be to play


def bells():
    for b in range(len(CHORDS)):
        for k in range(4):
            tt = b * T.BAR + k * 0.5
            if tt >= T.DUR: continue                                    # the last bar is a half bar
            s = max(S[int(tt * SR)], 0.9 * P[int(tt * SR)])               # bells fill in as the glass comes down
            if s + 1e-9 < THRESH[k]: continue
            vel = (0.55 if k == 0 else 0.38) * (0.45 + 0.55 * s)
            add(bell(parse(BELLS[b][k]), vel), int(tt * SR), [-0.35, 0.3, -0.1, 0.4][k], 0.20)


def focus_moment():
    for tf in (T.SWEEP_T,):                                            # the face, first seen at the end of the sweep
        _resolve(tf)


def _resolve(tf):
    for k, nm in enumerate(["D4", "A4", "E5", "F#5", "A5", "D6"]):       # the bell chord, rolled
        add(bell(parse(nm), 0.5), int((tf + 0.045 * k) * SR), -0.4 + 0.16 * k, 0.24)
    n = int(1.6 * SR); u = np.arange(n) / SR                             # sub swell
    add(np.sin(2 * np.pi * 36.7 * u) * np.exp(-u / 0.5) * np.clip(u / 0.02, 0, 1), int(tf * SR), 0, 0.42)
    n = int(3.0 * SR)                                                    # air rising into the downbeat
    sw = sosfilt(butter(2, [800, 6000], "band", fs=SR, output="sos"), rng.normal(0, 1, n))
    add(sw * np.linspace(0, 1, n) ** 3 * 0.035, int((tf - 3.0) * SR), 0.0)
    n = int(5.0 * SR); u = np.arange(n) / SR                             # shimmer after it
    sh = sum(np.sin(2 * np.pi * parse(nm) * 2 * u + i) for i, nm in enumerate(["D6", "F#6", "A6"]))
    add(sh * np.exp(-u / 1.6) * np.clip(u / 0.3, 0, 1) * 0.012, int(tf * SR), 0.2)


def ticks():
    import overlay as O
    k = 0
    for s in O.CODE:
        if s is None: continue
        tt = O.CODE_T0 + O.CODE_DT * O.CODE.index(s)
        n = int(0.03 * SR)
        click = sosfilt(butter(2, [2500, 9000], "band", fs=SR, output="sos"), rng.normal(0, 1, n)) * np.exp(-np.arange(n) / (0.003 * SR))
        add(click * 0.05, int(tt * SR), 0.1 * (k % 3 - 1)); k += 1


def riser():
    """a breath of filtered noise that grows with the descent and stops at the face"""
    n = len(t); x = rng.normal(0, 1, n)
    lo = sosfilt(butter(2, [400, 2500], "band", fs=SR, output="sos"), x)
    hi = sosfilt(butter(2, [2500, 9000], "band", fs=SR, output="sos"), x)
    env = P ** 2 * (t < T.SWEEP_T)
    add((lo * (1 - P) + hi * P) * env * 0.030, 0, 0.0)


def main():
    pad(); bass(); bells(); riser(); focus_moment(); ticks()
    ni = int(3.6 * SR); ui = np.arange(ni) / SR
    irs = []
    for sd in (1, 2):
        ir = np.random.default_rng(sd).normal(0, 1, ni) * np.exp(-ui / 0.85)
        ir = sosfilt(butter(1, 5500, "low", fs=SR, output="sos"), ir)
        ir[:int(0.025 * SR)] = 0; irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    wl = fftconvolve(L, irs[0])[:N]; wr = fftconvolve(R, irs[1])[:N]
    st = np.stack([L + 0.6 * wl, R + 0.6 * wr], 1)
    st = sosfilt(butter(2, 30, "high", fs=SR, output="sos"), st, axis=0)
    n0 = int(T.DUR * SR)                                                 # wrap the tail onto the start: seamless loop
    out = st[:n0].copy(); out[:N - n0] += st[n0:]
    np.save(ROOT / "cache" / f"mix_raw{T.SUFFIX}.npy", out.astype(np.float32))
    print("raw peak", float(np.abs(out).max()), "sharp range used: frames", len(S_frames))


if __name__ == "__main__":
    main()
