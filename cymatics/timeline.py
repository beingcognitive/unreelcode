"""Turns score.py into timed events, and defines the envelopes that BOTH the synth
(audio.py) and the physics (sand.py, water.py) read.  Film bars 16-18 replay bar 15
of the score after each live edit shown on screen (EDITS), re-executed from text."""
import numpy as np, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, 'score.py')).read()
EDIT_LINE = "(15, 1, E5, 4, .7)"
EDITS = ["E6", "A5", "Gs4"]          # film bars 16, 17, 18
T0 = 0.5

def load(src):
    ns = {}; exec(src, ns); return ns

S = load(SRC)
VERSIONS = [S] + [load(SRC.replace(EDIT_LINE, EDIT_LINE.replace("E5", e))) for e in EDITS]
F, BPM = S['F'], S['BPM']
BEAT = 60.0 / BPM; BAR = 4 * BEAT
def tbar(bar, beat=1): return T0 + (bar - 1) * BAR + (beat - 1) * BEAT

def plate_events():
    ev = []
    for (bar, beat, k, beats, vel) in S['PLATE']:
        if bar == 15:
            for j, V in enumerate(VERSIONS):
                b15 = [e for e in V['PLATE'] if e[0] == 15][0]
                ev.append(dict(t0=tbar(15 + j, beat), dur=beats * BEAT, k=b15[2], vel=vel, ver=j))
        else:
            ev.append(dict(t0=tbar(bar, beat), dur=beats * BEAT, k=k, vel=vel, ver=0))
    return ev

def held(d, last=24):
    keys = sorted(d); out = []
    for i, b in enumerate(keys):
        e = keys[i + 1] if i + 1 < len(keys) else last + 1
        out.append((b, e, d[b]))
    return out

def dyn(t):
    v = 0.0
    for b, e, x in held(S['DYN']):
        if t >= tbar(b): v = x
    return v

def pad_events():
    ev = []
    for b, e, notes in held(S['CHORDS']):
        for k in notes:
            ev.append(dict(t0=tbar(b), dur=(e - b) * BAR, k=k, vel=1.0))
    return ev

def bass_events():
    return [dict(t0=tbar(b), dur=(e - b) * BAR, k=k, vel=1.0)
            for b, e, k in held(S['BASS']) if k]

# ---- envelopes (vectorised over t) ----
def env_plate(t, ev):
    """Struck then bowed: strike decays onto a bowed sustain, damped at note end."""
    u = t - ev['t0']; d = ev['dur']
    a = np.clip(u / 0.004, 0, 1)
    body = 0.30 + 0.70 * np.exp(-np.maximum(u, 0) / 0.45)
    rel = np.where(u > d, np.exp(-(u - d) / 0.12), 1.0)
    return np.where(u < 0, 0.0, ev['vel'] * a * body * rel)

def env_pad(t, ev):
    u = t - ev['t0']; d = ev['dur']
    a = 0.5 - 0.5 * np.cos(np.pi * np.clip(u / 0.9, 0, 1))
    rel = np.where(u > d, np.exp(-(u - d) / 0.6), 1.0)
    return np.where(u < 0, 0.0, a * rel)

def pad_level(t):   # dynamics shaped smoothly (0.4 s glide)
    tt = np.atleast_1d(t)
    raw = np.array([dyn(x) for x in np.arange(0, 62, 0.01)])
    ker = np.ones(40) / 40; sm = np.convolve(np.pad(raw, (39, 0), mode='edge'), ker, 'valid')
    return np.interp(tt, np.arange(0, 62, 0.01), sm)

def freq(k): return F * k

def plate_drive(t):
    """[(k, amplitude)] of plate notes sounding at time t (amplitude = audio envelope)."""
    out = []
    for ev in PLATE_EV:
        a = float(env_plate(np.array(t), ev))
        if a > 1e-3: out.append((ev['k'], a))
    return out

def dish_drive(t):
    lvl = float(pad_level(t)[0]); out = []
    for ev in PAD_EV:
        a = float(env_pad(np.array(t), ev)) * lvl
        if a > 1e-3: out.append((ev['k'], a))
    return out

PLATE_EV = plate_events(); PAD_EV = pad_events(); BASS_EV = bass_events()

if __name__ == '__main__':
    for e in PLATE_EV: print('plate', round(e['t0'], 2), e['k'], round(freq(e['k']), 1), 'v', e['ver'])
    for e in PAD_EV: print('pad', round(e['t0'], 2), round(e['dur'], 2), e['k'])
    print(plate_drive(0.6), dish_drive(32))
