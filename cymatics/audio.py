"""Synthesises the soundtrack from score.py via timeline.py (numpy only + scipy for filters).
Every pitched note uses the exact frequency F*k that drives the plate / dish."""
import numpy as np, sys, os
from scipy.signal import fftconvolve, butter, sosfilt
import timeline as T

SR = 48000
DUR = 60.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)
L = np.zeros(N); R = np.zeros(N)

def add(sig, i0, pan=0.0, g=1.0):
    i1 = min(N, i0 + len(sig)); sig = sig[:i1 - i0]
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    L[i0:i1] += sig * l * g * 1.414; R[i0:i1] += sig * r * g * 1.414

# ---------- PLATE voice: struck + bowed metal (modal synthesis) ----------
# partial ratio, rel amp, decay (s) -- inharmonic plate-like partials above the fundamental
PARTIALS = [(1.0, 1.0, 9.0), (2.0, .30, 3.0), (2.76, .16, 1.6), (4.07, .08, .9),
            (5.40, .05, .6), (6.80, .025, .4), (0.5, .10, 6.0)]
def plate_note(ev):
    f = T.freq(ev['k']); d = ev['dur'] + 1.6
    n = int(d * SR); u = np.arange(n) / SR
    env = T.env_plate(ev['t0'] + u, ev)            # the SAME envelope the sand sees
    strike = np.exp(-u / 0.45)
    s = np.zeros(n)
    for r, a, tau in PARTIALS:
        if f * r > 16000: continue
        ph = rng.uniform(0, 2 * np.pi)
        det = 1 + rng.normal(0, 0.0006)
        if r == 1.0:
            # fundamental follows the drive envelope exactly (+ gentle bow vibrato in sustain)
            vib = 1 + 0.0012 * np.sin(2 * np.pi * 5.1 * u) * (1 - strike)
            s += env * np.sin(2 * np.pi * f * np.cumsum(vib) / SR + ph)
        else:
            # struck overtones: ring out on their own decay, damped with the note
            damp = np.where(u > ev['dur'], np.exp(-(u - ev['dur']) / 0.12), 1.0)
            s += ev['vel'] * a * np.exp(-u / tau) * strike ** 0.3 * damp * \
                np.sin(2 * np.pi * f * r * det * u + ph)
    # mallet click: very short filtered noise burst
    nk = int(0.012 * SR)
    click = rng.normal(0, 1, nk) * np.exp(-np.arange(nk) / (0.002 * SR))
    sos = butter(2, [2000, 9000], 'band', fs=SR, output='sos')
    s[:nk] += 0.05 * ev['vel'] * sosfilt(sos, click)
    return s

# ---------- GLASS pad: bowed glass, sine-rich ----------
def pad_note(ev, lvl):
    f = T.freq(ev['k']); d = ev['dur'] + 2.5
    n = int(d * SR); u = np.arange(n) / SR
    env = T.env_pad(ev['t0'] + u, ev) * lvl[int(ev['t0'] * SR): int(ev['t0'] * SR) + n]
    outL = np.zeros(n); outR = np.zeros(n)
    for h, a in [(1, 1.0), (2, .28), (3, .10), (4, .05), (6, .015)]:
        if f * h > 15000: continue
        for side, det in ((0, -1.6), (1, 1.6)):
            ff = f * h * 2 ** (det / 1200)
            trem = 1 + 0.05 * np.sin(2 * np.pi * (0.23 + 0.07 * h) * u + side + h)
            sig = a * trem * np.sin(2 * np.pi * ff * u + rng.uniform(0, 6.3))
            (outL if side == 0 else outR)[:] += sig
    # bow noise: band-passed around the fundamental
    sos = butter(2, [f * 0.97, f * 1.03], 'band', fs=SR, output='sos')
    nz = sosfilt(sos, rng.normal(0, 1, n)) * 0.25
    return env * (outL + nz), env * (outR + nz)

def bass_note(ev, lvl):
    f = T.freq(ev['k']); d = ev['dur'] + 1.5
    n = int(d * SR); u = np.arange(n) / SR
    env = T.env_pad(ev['t0'] + u, ev) * lvl[int(ev['t0'] * SR): int(ev['t0'] * SR) + n]
    s = np.sin(2 * np.pi * f * u) + 0.35 * np.sin(4 * np.pi * f * u + 0.3) + \
        0.12 * np.sin(6 * np.pi * f * u + 1.1)
    return env * s

def main(out):
    lvl = np.pad(T.pad_level(t), (0, SR * 10), mode='edge')
    for i, ev in enumerate(T.PLATE_EV):
        pan = [-.15, .1, -.05, .15][i % 4]
        add(plate_note(ev), int(ev['t0'] * SR), pan, 0.30)
    for ev in T.PAD_EV:
        l, r = pad_note(ev, lvl); i0 = int(ev['t0'] * SR); i1 = min(N, i0 + len(l))
        L[i0:i1] += 0.085 * l[:i1 - i0]; R[i0:i1] += 0.085 * r[:i1 - i0]
    for ev in T.BASS_EV:
        add(bass_note(ev, lvl), int(ev['t0'] * SR), 0, 0.16)
    # un-pitched: a rising air swell into the first downbeat, a sub thump on it and on the climax
    n0 = int(0.5 * SR); sw = rng.normal(0, 1, n0)
    sos = butter(2, [300, 3000], 'band', fs=SR, output='sos')
    add(sosfilt(sos, sw) * np.linspace(0, 1, n0) ** 3 * 0.05, 0)
    for tt, g in ((T.tbar(1), .5), (T.tbar(13), .35), (T.tbar(21), .3)):
        u = np.arange(int(0.6 * SR)) / SR
        add(np.sin(2 * np.pi * (38 + 30 * np.exp(-u / 0.03)) * u) * np.exp(-u / 0.18) * g, int(tt * SR))
    # reverb: synthetic stereo IR (decaying filtered noise), 3.2 s
    ni = int(3.2 * SR); ui = np.arange(ni) / SR
    irs = []
    for s in (1, 2):
        ir = np.random.default_rng(s).normal(0, 1, ni) * np.exp(-ui / 0.75)
        ir = sosfilt(butter(1, 6000, 'low', fs=SR, output='sos'), ir)
        ir[:int(0.022 * SR)] = 0; irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    wetL = fftconvolve(L, irs[0])[:N]; wetR = fftconvolve(R, irs[1])[:N]
    mixL = L + 0.55 * wetL; mixR = R + 0.55 * wetR
    # fade tail
    # v3.2: no fade-out: the pad holds into the loop (splice.py crossfades the end into the opening)
    fade = np.clip((DUR - t) / 0.05, 0, 1); mixL *= fade; mixR *= fade
    st = np.stack([mixL, mixR], 1)
    st = sosfilt(butter(2, 28, 'high', fs=SR, output='sos'), st, axis=0)
    np.save(out.replace('.wav', '_raw.npy'), st.astype(np.float32))
    print('raw peak', np.abs(st).max())

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'cache/mix.wav')
