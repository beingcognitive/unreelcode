"""music.py -- the score, synthesised in numpy (no samples).

D minor, 96 BPM, 4/4: one bar = 2.5 s, 24 bars = 60 s. Every cut and the text-forming
moment sit on a bar line. Sonification: the simulation's measured kinetic energy per frame
drives note *density* and filter brightness of the pulse layer; pitch always comes from the
chord of the bar.
"""
import json, os
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve, lfilter, resample_poly

SR = 48000
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
DUR = 52.5                       # v2: 21 bars
HERE = os.path.dirname(os.path.abspath(__file__))
N = int(SR * DUR)
rng = np.random.default_rng(3)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}


def m(name, octv):
    return 12 * (octv + 1) + NOTE[name]


# chord per bar (24 bars). Root + voicing as midi lists.
CH = {
    "Dm9": [m("D", 3), m("A", 3), m("F", 4), m("A", 4), m("E", 5)],
    "Bbmaj7": [m("Bb", 2), m("F", 3), m("D", 4), m("A", 4), m("F", 5)],
    "F": [m("F", 2), m("C", 3), m("A", 3), m("C", 5), m("F", 5)],
    "C": [m("C", 3), m("G", 3), m("E", 4), m("G", 4), m("D", 5)],
    "Gm7": [m("G", 2), m("D", 3), m("Bb", 3), m("F", 4), m("D", 5)],
    "Asus": [m("A", 2), m("E", 3), m("D", 4), m("A", 4), m("E", 5)],
    "A": [m("A", 2), m("E", 3), m("C#", 4), m("A", 4), m("E", 5)],
    "Bb/A": [m("A", 2), m("F", 3), m("Bb", 3), m("D", 4), m("F", 5)],
    "Gm/A": [m("A", 2), m("G", 3), m("Bb", 3), m("D", 4), m("G", 5)],
    "Dadd9": [m("D", 3), m("A", 3), m("F#", 4), m("A", 4), m("E", 5)],
}
BARS = ["Dm9", "Dm9",                                   # 1-2  hook (pipette plume)
        "Bbmaj7", "F", "C", "Gm7",                      # 3-6  build (rt on 3, clash on 4, drops on 5-6)
        "Gm/A", "Bb/A", "Asus",                         # 7-9  formation over an A pedal (played backwards), v3: 3 bars
        "Dm9", "Dm9",                                   # 10-11 the code is readable; the edit
        "Dm9", "Bbmaj7", "F", "A",                      # 12-15 release (ink now lighter than water)
        "Bbmaj7", "F", "Gm7", "Asus",                   # 16-19 final bloom
        "Dm9", "Dm9"]                                   # 20-21 end card, then the loop
assert len(BARS) == 21
import assemble as _asm
# the motif: scale degrees as midi, quarter notes; the edit changes ONE note (the 5th: G -> Bb)
MOTIF = [m("D", 5), m("F", 5), m("A", 5), m("G", 5), m("F", 5), m("E", 5)]
MOTIF_EDIT = [m("D", 5), m("F", 5), m("A", 5), m("G", 5), m("Bb", 5), m("A", 5)]


# ---------------------------------------------------------------- energy (sonification input)
def load_energy():
    """film-time -> normalised log kinetic energy of the shot on screen (0..1), from the v2 cut list"""
    fps = 24
    e = np.zeros(int(DUR * fps))
    for name, a0, n, rev, t0 in _asm.SEGS:
        p = f"{HERE}/cache/{name}/stats.json"
        ke = np.array([s["ke"] for s in json.load(open(p))["stats"]], float)
        ke = np.nan_to_num(ke, nan=0.0, posinf=0.0)
        seg = ke[a0:a0 + n][::-1] if rev else ke[a0:a0 + n]
        i = int(round(t0 * fps))
        e[i:i + len(seg)] = np.log1p(seg)
    lo, hi = np.percentile(e, 5), np.percentile(e, 98)
    e = np.clip((e - lo) / (hi - lo + 1e-9), 0, 1)
    k = np.ones(12) / 12  # half-second smoothing
    e = np.convolve(e, k, mode="same")
    return lambda t: float(e[min(int(t * fps), len(e) - 1)])


ENERGY = load_energy()


# ---------------------------------------------------------------- instruments
def env_adsr(n, a, d, s, r, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    a = max(a, 1)
    e = np.full(n, s, float)
    e[:a] = np.linspace(0, 1, a)
    e[a:a + d] = np.linspace(1, s, len(e[a:a + d]))
    if r > 0:
        e[-r:] *= np.linspace(1, 0, min(r, n))[-len(e[-r:]):]
    return e


def lp(x, fc, order=2):
    fc = min(max(fc, 20), SR * 0.45)
    return sosfilt(butter(order, fc, fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, "high", fs=SR, output="sos"), x)


def pad_voice(f0, dur, bright=2500, amp=0.1):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for det in (-0.07, 0.0, 0.06):          # three detuned 'saws' from 14 harmonics
        f = f0 * 2 ** (det / 12)
        ph = rng.uniform(0, 2 * np.pi)
        for h in range(1, 15):
            if f * h > 9000:
                break
            y += np.sin(2 * np.pi * f * h * t + ph * h) / h
    y = lp(y, bright, 2)
    return y * env_adsr(n, min(0.9, dur * 0.4), 0.3, 0.8, min(1.2, dur * 0.4)) * amp


def bell(f0, dur=3.0, amp=0.12, ratio=3.5, index=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    mod = index * np.exp(-t * 2.5) * np.sin(2 * np.pi * f0 * ratio * t)
    y = np.sin(2 * np.pi * f0 * t + mod) + 0.25 * np.sin(2 * np.pi * f0 * 2.0 * t) * np.exp(-t * 3)
    return y * np.exp(-t * 1.4) * np.minimum(1, t / 0.004) * amp


def pluck(f0, dur=1.2, amp=0.1, damp=0.996, bright=0.5):
    """Karplus-Strong via a single IIR (lfilter)"""
    n = int(dur * SR)
    P = int(SR / f0)
    x = np.zeros(n)
    burst = rng.uniform(-1, 1, P)
    burst = lp(burst, 1500 + 6000 * bright, 1)
    x[:P] = burst
    a = np.zeros(P + 2)
    a[0] = 1
    a[P] = -damp * 0.5
    a[P + 1] = -damp * 0.5
    y = lfilter([1.0], a, x)
    return y * env_adsr(n, 0.002, 0.0, 1.0, 0.05) * amp


def sine_bass(f0, dur, amp=0.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f0 * t) + 0.18 * np.sin(2 * np.pi * 2 * f0 * t)
    return y * env_adsr(n, 0.02, 0.2, 0.85, 0.3) * amp


def kick(amp=0.5, dur=0.9):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 42 + 90 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 4.5) * amp


def boom(amp=0.7, dur=4.0):
    """the opening impact: falling sub + a short noise transient"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 36 + 70 * np.exp(-t * 6)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.1)
    nz = lp(rng.normal(0, 1, n), 2500) * np.exp(-t * 18) * 0.5
    return (y + nz) * amp


def tom(f0=80, amp=0.35, dur=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 0.6 * np.exp(-t * 20))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
    y += lp(rng.normal(0, 1, n), 900) * np.exp(-t * 30) * 0.3
    return y * amp


def shaker(amp=0.05, dur=0.09):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return hp(rng.normal(0, 1, n), 6000) * np.exp(-t * 60) * amp


def click(amp=0.08):
    """keystroke: a tiny filtered tick + a pitched glint"""
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return hp(rng.normal(0, 1, n), 3000) * np.exp(-t * 200) * amp


def swell(dur, amp=0.1, f_lo=300, f_hi=6000):
    """reversed-envelope noise riser (things running backwards)"""
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    y = rng.normal(0, 1, n)
    out = np.zeros(n)
    blk = 2048
    for i in range(0, n, blk):
        fc = f_lo * (f_hi / f_lo) ** t[i]
        out[i:i + blk] = lp(y[i:i + blk + 0], fc, 1)[:len(out[i:i + blk])]
    return lp(out, f_hi) * (t ** 2.5) * amp


def reverse_bell(f0, dur, amp):
    b = bell(f0, dur, amp)
    return b[::-1]


# ---------------------------------------------------------------- arrangement
class Bus:
    def __init__(self):
        self.L = np.zeros(N + SR * 6)
        self.R = np.zeros(N + SR * 6)

    def add(self, t, y, pan=0.0, gain=1.0):
        i = int(t * SR)
        if i < 0:
            y = y[-i:]; i = 0
        j = min(i + len(y), len(self.L))
        y = y[:j - i] * gain
        self.L[i:j] += y * np.cos((pan + 1) * np.pi / 4)
        self.R[i:j] += y * np.sin((pan + 1) * np.pi / 4)


dry, wet = Bus(), Bus()   # wet goes through the hall reverb


def bar_t(b):  # bar index from 1
    return (b - 1) * BAR


def section(b):
    return ("hook" if b <= 2 else "build" if b <= 6 else "turn" if b <= 9 else
            "reveal" if b <= 11 else "release" if b <= 15 else "bloom" if b <= 19 else "end")


def compose():
    # opening impact on frame 1
    dry.add(0.0, boom(0.8))
    wet.add(0.0, swell(0.6, 0.0) + 0, 0)
    for b in range(1, 22):
        t0 = bar_t(b)
        ch = CH[BARS[b - 1]]
        sec = section(b)
        # ---- pads (always; level per section)
        pl = {"hook": 0.05, "build": 0.06, "turn": 0.07, "reveal": 0.022, "release": 0.09,
              "bloom": 0.06, "end": 0.05}[sec]
        br = {"hook": 1400, "build": 1800, "turn": 2600, "reveal": 1200, "release": 3200,
              "bloom": 2200, "end": 1100}[sec]
        if sec == "turn":
            # reversed swells: each voice fades IN to the bar line (time running backwards)
            for k, note in enumerate(ch):
                v = pad_voice(hz(note), BAR, br, pl)
                v = v[::-1] * np.linspace(0.2, 1, len(v)) ** 2
                wet.add(t0, v, pan=-0.6 + 0.3 * k)
        else:
            dur = BAR + 0.6 if sec != "end" else (5.5 if b == 20 else 0.0)
            for k, note in enumerate(ch):
                if dur > 0:
                    wet.add(t0, pad_voice(hz(note), dur, br, pl), pan=-0.6 + 0.3 * k)
        # ---- low drone / bass
        root = ch[0]
        while root > m("D", 3):
            root -= 12
        if sec in ("hook", "reveal", "end"):
            dry.add(t0, sine_bass(hz(root - 12), BAR + 0.3, 0.14 if sec != "reveal" else 0.07))
        elif sec in ("build", "bloom"):
            for q in range(2):
                dry.add(t0 + q * 2 * BEAT, sine_bass(hz(root - 12), 2 * BEAT, 0.16))
        elif sec == "turn":
            dry.add(t0, sine_bass(hz(m("A", 1)), BAR + 0.2, 0.17 + 0.03 * (b - 9)))
        elif sec == "release":
            for q in range(8):   # driving eighths
                dry.add(t0 + q * BEAT / 2, sine_bass(hz(root - 12), BEAT / 2 * 0.9, 0.17))
        # ---- motif
        if sec == "hook" and b == 1:
            for i, note in enumerate(MOTIF):
                wet.add(t0 + BEAT * (1 + i * 0.5 if i < 4 else 1 + i * 0.5), bell(hz(note), 3.0, 0.07), pan=0.2)
        if sec == "build" and b in (3, 5, 6):
            off = 0 if b < 6 else -2
            for i, note in enumerate(MOTIF[:4] if b == 3 else MOTIF):
                wet.add(t0 + BEAT * i * (0.5 if b == 6 else 1), bell(hz(note + off), 3.0, 0.06), pan=-0.2)
        if b == 10:
            # the code is readable: the motif alone, clear, quarter notes
            for i, note in enumerate(MOTIF):
                wet.add(t0 + BEAT * i * 0.66, bell(hz(note), 3.5, 0.06), pan=0.0)
        if b == 11:
            # the edit (v2): a keystroke tick at each retyped character of the value (16ths) and of the comment
            # (32nds), at the exact hold times the shot uses; then the motif returns with one note changed
            import shots as _sh
            hold0 = bar_t(10)
            for i, x in enumerate(_sh.B_EDIT):
                dry.add(hold0 + x, click(0.05 if i < 4 else 0.06), pan=0.3)
            for i, x in enumerate(_sh.C_EDIT):
                dry.add(hold0 + x, click(0.035 if i < 7 else 0.045), pan=-0.2)
            for i, note in enumerate(MOTIF_EDIT):
                wet.add(t0 + BEAT * 2.5 + BEAT * i * 0.25, bell(hz(note), 3.0, 0.07), pan=0.1)
        if sec == "release" and b in (12, 14):
            for i, note in enumerate(MOTIF_EDIT):
                for o in (0, 12):
                    wet.add(t0 + BEAT * i * 0.5, bell(hz(note + o - 12), 2.5, 0.05 if o else 0.07), pan=0.25 * (1 if o else -1))
        if b == 20:
            for i, note in enumerate(MOTIF[:3] + [m("D", 6)]):
                wet.add(t0 + BEAT * i * 0.75, bell(hz(note), 5.0, 0.07))
        # ---- data-driven pulse: plucked chord tones; energy -> density + brightness (never pitch)
        if sec in ("build", "release", "bloom", "turn"):
            tones = sorted(set([n + 12 for n in ch[1:]] + [n for n in ch[2:]]))
            for s16 in range(16):
                t = t0 + s16 * BEAT / 4
                e = ENERGY(t)
                base = {"build": 0.25, "release": 0.55, "bloom": 0.2, "turn": 0.1}[sec]
                p = base + 0.6 * e
                on_grid = s16 % 2 == 0
                if rng.random() < (p if on_grid else p * 0.6):
                    note = tones[(s16 * 3 + b) % len(tones)]
                    amp = 0.035 + 0.035 * e
                    wet.add(t, pluck(hz(note), 1.0, amp, 0.995, bright=0.3 + 0.6 * e), pan=rng.uniform(-0.7, 0.7), gain=0.6)
                    dry.add(t, pluck(hz(note), 1.0, amp, 0.995, bright=0.3 + 0.6 * e), pan=rng.uniform(-0.5, 0.5), gain=0.5)
        # ---- percussion
        if b in (3, 4, 5, 7):
            dry.add(t0, tom(70, 0.32))           # cut hits (v3 cut list)
        if b == 4 or b == 6 or b == 8:
            pass
        if sec == "build" and b >= 5:
            # drops shot: every beat a drop lands -> a soft tom on each beat
            for q in range(4):
                dry.add(t0 + q * BEAT, tom(95 if q % 2 else 75, 0.16))
        if sec == "release":
            for q in range(4):
                dry.add(t0 + q * BEAT, kick(0.42 if q in (0, 2) else 0.26))
            for s16 in range(16):
                e = ENERGY(t0 + s16 * BEAT / 4)
                if s16 % 2 == 1 or rng.random() < e:
                    dry.add(t0 + s16 * BEAT / 4, shaker(0.008 + 0.014 * e), pan=0.4)
            dry.add(t0 + 3.5 * BEAT, tom(110, 0.12))
        if sec == "bloom" and b in (16, 18):
            dry.add(t0, tom(65, 0.25))
    # the turn: riser into the reveal (bars 7-9 -> downbeat of 10)
    wet.add(bar_t(7), swell(3 * BAR, 0.07, 200, 6000))
    for i, note in enumerate(reversed(MOTIF)):
        wet.add(bar_t(9) + i * BEAT * 0.5, reverse_bell(hz(note), 1.2, 0.05), pan=0.3)
    # reveal downbeat: the release of tension, a soft low hit
    dry.add(bar_t(10), tom(55, 0.22))
    # release downbeat (fluid let go at 27.5 s): big impact
    dry.add(bar_t(12), boom(0.65, 3.0))
    wet.add(bar_t(11) + 2 * BEAT, swell(2 * BEAT, 0.05, 300, 5000))


def hall(dur=3.2, pre=0.02):
    n = int(dur * SR)
    t = np.arange(n) / SR
    irs = []
    for s in range(2):
        nz = rng.normal(0, 1, n) * np.exp(-t * 6.9 / dur)
        # darker tail: blend toward lowpassed noise over time
        nzl = lp(nz, 2500, 1)
        mix = np.clip(t / dur * 1.5, 0, 1)
        ir = nz * (1 - mix) + nzl * mix
        ir[: int(pre * SR)] = 0
        irs.append(ir / np.sqrt((ir ** 2).sum()))
    return irs


def true_peak(x):
    return max(np.abs(resample_poly(c, 4, 1)).max() for c in x)


def master():
    import pyloudnorm as pyln
    compose()
    irL, irR = hall()
    wl = fftconvolve(wet.L, irL)[: len(wet.L)]
    wr = fftconvolve(wet.R, irR)[: len(wet.R)]
    L = dry.L + 0.55 * wl + 0.25 * wet.L
    R = dry.R + 0.55 * wr + 0.25 * wet.R
    x = np.stack([L, R])[:, :N]
    x = hp(x, 28)
    # gentle bus compression (RMS, 4:1 above threshold), slow
    lvl = np.sqrt(lp(np.mean(x ** 2, 0), 8, 1).clip(1e-12))
    thr = np.percentile(lvl, 92)
    g = np.where(lvl > thr, (lvl / thr) ** (-0.4), 1.0)
    x = x * g
    # fade the end
    fo = int(0.5 * SR)                       # v2: short tail fade; the film loops into its opening boom
    x[:, -fo:] *= np.linspace(1, 0, fo) ** 2
    meter = pyln.Meter(SR)
    for _ in range(4):
        lufs = meter.integrated_loudness(x.T)
        x *= 10 ** ((-14.0 - lufs) / 20)
        # soft limiter: oversampled peak, smooth gain toward -2.3 dBTP ceiling
        ceil = 10 ** (-2.3 / 20)
        up = np.stack([resample_poly(c, 4, 1) for c in x])
        pk = np.abs(up).max(0).reshape(-1, 4).max(1)[: x.shape[1]]
        need = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
        # lookahead min + smoothing (2 ms attack, 80 ms release)
        from scipy.ndimage import minimum_filter1d
        need = minimum_filter1d(need, int(0.004 * SR))
        a = np.exp(-1 / (0.08 * SR))
        gg = lfilter([1 - a], [1, -a], need)
        gg = np.minimum(gg, minimum_filter1d(need, int(0.002 * SR)))
        x = x * gg
    lufs = meter.integrated_loudness(x.T)
    tp = 20 * np.log10(true_peak(x))
    return x, lufs, tp


if __name__ == "__main__":
    import sys
    from scipy.io import wavfile
    x, lufs, tp = master()
    out = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/cache/music.wav"
    wavfile.write(out, SR, (x.T * 32767).clip(-32768, 32767).astype(np.int16))
    print(f"integrated {lufs:.2f} LUFS, true peak {tp:.2f} dBTP -> {out}")
