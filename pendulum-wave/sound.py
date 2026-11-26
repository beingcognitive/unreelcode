"""Sound, synthesised from the simulation.

Each pendulum has one note of a major pentatonic scale (red/longest = lowest, C3 ... blue/shortest = A6). The note
sounds every time that ball crosses the glowing centre line, in either direction, at the instant the integrator
found the crossing (interpolated between steps, not snapped to frames). The same instants light the ball and a spot
on the line (timeline.flashes).

Display choices (disclosed): the notes' level follows a slow envelope (softer in the middle, swelling into the
realignment); at t = 30.00 s, when all 20 are lined up, a soft chord of all 20 notes blooms; the board's knock and
whoosh; a quiet low bed. Master: integrated -14 LUFS, true peak <= -1 dBTP after AAC (ffmpeg ebur128).

  python sound.py     # -> cache/audio.wav, out/audio_meas.json
"""
import json, math, os, re, subprocess, wave
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import timeline as T

SR = 48000
N = int(round(T.T_TOTAL * SR))
rng = np.random.default_rng(5)
SIM = np.load("cache/sim.npz", allow_pickle=True)
XINGS = SIM["xings"]
SCALE = [0, 2, 4, 7, 9]
FREQ = [130.8128 * 2 ** ((12 * (k // 5) + SCALE[k % 5]) / 12) for k in range(T.NP)]
TG = T.T_PRE + T.GAMMA


def pluck(f, dur=1.6):
    t = np.arange(int(dur * SR)) / SR
    dec = 0.22 + 0.45 * (130.8 / f) ** 0.6
    env = (1 - np.exp(-t / 0.003)) * np.exp(-t / dec)
    s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2.0 * f * t) * np.exp(-t / (dec * 0.4))
         + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t / (dec * 0.2))
         + 0.06 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.025))
    return env * s / (1 + 0.0009 * f)


def bloom(dur=4.5):
    """all 20 notes, soft attack peaking at t = 0.12 s, long tail"""
    t = np.arange(int(dur * SR)) / SR
    env = (1 - np.exp(-t / 0.10)) * np.exp(-t / 1.8)
    ph = np.random.default_rng(11).uniform(0, 2 * np.pi, (len(FREQ), 2))       # spread phases: lower crest factor
    s = sum((np.sin(2 * np.pi * f * t + ph[i, 0]) + 0.25 * np.sin(2 * np.pi * 2 * f * t + ph[i, 1])) / (1 + 0.0012 * f)
            for i, f in enumerate(FREQ))
    return env * s / len(FREQ)


def add(buf, x, t0, pan=0.0):
    i = int(round(t0 * SR))
    if i < 0: x = x[-i:]; i = 0
    if i >= N: return
    x = x[:N - i]
    buf[i:i + len(x), 0] += x * math.sqrt((1 - pan) / 2)
    buf[i:i + len(x), 1] += x * math.sqrt((1 + pan) / 2)


# display: a soft two-note drone that changes chord at each chapter moment (sim seconds), all in C pentatonic
C2, D2, E2, G2, A2 = 65.41, 73.42, 82.41, 98.00, 110.0
DRONE = [(0.0, (C2, G2)), (15.0, (G2, D2 * 2)), (20.0, (E2, A2)), (30.0, (C2 * 2, G2 * 2)),
         (40.0, (E2, A2)), (45.0, (G2, D2 * 2)), (50.0, (A2, E2 * 2)), (55.0, (D2, A2)), (58.0, (G2, D2 * 2)), (60.0, (C2, G2))]


def drone(t):
    out = np.zeros_like(t); ts = t - T.T_PRE
    for i, (t0, (f1, f2)) in enumerate(DRONE):
        t1 = DRONE[i + 1][0] if i + 1 < len(DRONE) else 1e9
        w = np.clip((ts - (t0 - 0.6)) / 1.2, 0, 1) * np.clip(((t1 - 0.6) - ts) / 1.2 + 1, 0, 1) if i else np.clip(((t1 - 0.6) - ts) / 1.2 + 1, 0, 1)
        out += w * (0.5 * np.sin(2 * np.pi * f1 * t) + 0.35 * np.sin(2 * np.pi * f2 * t + 1.0) + 0.08 * np.sin(2 * np.pi * 2 * f2 * t))
    return out


def level(t_film):
    """display envelope on the notes: 0.66 at the start, 0.48 through the middle, swelling to 1.0 at the line-up"""
    s = t_film - T.T_PRE
    a = 0.66 - 0.18 * T.sm((s - 2.0) / 6.0)
    return a + (0.85 - a) * T.sm((s - (T.GAMMA - 6.0)) / 6.0) - 0.4 * T.sm((s - (T.GAMMA + 0.6)) / 1.5)


def main():
    notes = np.zeros((N, 2)); fx = np.zeros((N, 2))
    pans = [0.45 * math.sin(1.7 * k) for k in range(T.NP)]
    cache = {k: pluck(FREQ[k]) for k in range(T.NP)}
    n = 0
    for k in range(T.NP):
        for tc, d in XINGS[k]:
            if tc <= T.T_SIM_END:
                t0 = T.T_PRE + tc; add(notes, cache[k] * level(t0), t0, pans[k]); n += 1
    t_meet = T.T_IDLE + T.T_IN
    tt = np.arange(int(0.25 * SR)) / SR
    knock = (np.sin(2 * np.pi * 180 * tt) * np.exp(-tt / 0.035) + 0.15 * rng.standard_normal(len(tt)) * np.exp(-tt / 0.006))
    add(fx, 0.6 * knock, t_meet)
    wl = int(0.7 * SR); w = np.convolve(rng.standard_normal(wl), np.ones(24) / 24, "same")
    add(fx, 0.9 * w * np.sin(np.pi * np.arange(wl) / wl) ** 2, T.T_PRE - 0.05, -0.3)
    BLOOM_GAIN = float(os.environ.get("BLOOM", 3.0))
    b = bloom(); add(fx, BLOOM_GAIN * b, TG - 0.12)
    t = np.arange(N) / SR
    bed = drone(t)
    shape = np.clip((t - 0.8) / 3.0, 0, 1) * (0.55 + 0.45 * np.clip((t - T.T_PRE) / T.GAMMA, 0, 1)) * np.clip((T.T_TOTAL - 0.6 - t) / 2.0, 0, 1)
    bed *= 0.07 * shape
    fade = np.clip((T.T_TOTAL - 0.3 - t) / 2.4, 0, 1) ** 1.5
    mix = (notes * 0.16 + fx + bed[:, None]) * fade[:, None]
    json.dump(dict(n_notes=n, trigger="centre-line crossing, both directions", freqs_hz=[round(f, 2) for f in FREQ],
                   t_release=T.T_PRE, t_realign=TG, bloom_gain=BLOOM_GAIN), open("cache/sound_events.json", "w"), indent=1)
    master(mix)


def write_wav(path, x):
    y = np.clip(x, -1, 1); b = (y * (2 ** 23 - 1)).astype(np.int32)
    raw = np.zeros((len(b), 2, 3), np.uint8)
    for k in range(3): raw[:, :, k] = (b >> (8 * k)) & 0xFF
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(3); w.setframerate(SR); w.writeframes(raw.tobytes())


def ebur(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-v", "verbose", "-i", path, "-filter_complex", "ebur128=peak=true:framelog=verbose",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    ebur.S = [(float(a), float(v)) for a, v in re.findall(r"t:\s*([\d.]+)\s+TARGET.*?S:\s*(-?[\d.]+)", r)]
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]); TP = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1])
    LRA = float(re.findall(r"LRA:\s+(-?[\d.]+) LU", r)[-1])
    return I, TP, LRA


def limit(x, ceiling_db, look=0.003, release=0.08):
    c = 10 ** (ceiling_db / 20); a = np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, c / np.maximum(a, 1e-12)); n = int(look * SR)
    g = sliding_window_view(np.concatenate([need, np.ones(n)]), n + 1).min(axis=1)[:len(need)]
    rel = np.exp(-1 / (release * SR)); out = np.empty_like(g); s = 1.0
    for k in range(len(g)):
        s = min(g[k], rel * s + (1 - rel) * g[k]); out[k] = s
    return x * out[:, None], 20 * np.log10(out.min())


def master(mix):
    gdb = 0.0
    for it in range(12):
        y, gr = limit(mix * 10 ** (gdb / 20), -1.5)
        write_wav("cache/audio.wav", y)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "cache/audio.wav", "-c:a", "aac", "-b:a", "256k",
                        "cache/audio_test.m4a"], check=True)
        I, TP, LRA = ebur("cache/audio_test.m4a")
        print(f"iter {it}: gain {gdb:+.2f} dB -> I {I:.2f} LUFS, TP {TP:.2f} dBTP, LRA {LRA:.1f}, limiter max GR {gr:.2f} dB", flush=True)
        if abs(I + 14) <= 0.15 and TP <= -1.0: break
        gdb += (-14 - I)
    S = ebur.S
    near = [v for a, v in S if TG - 2.0 <= a <= TG + 5.0]; far = [(v, a) for a, v in S if not (TG - 2.0 <= a <= TG + 5.0) and a > 3]
    sm_g = max(near); sm_o, at_o = max(far)
    print(f"short-term max around the line-up: {sm_g:.1f} LUFS; elsewhere max {sm_o:.1f} LUFS at {at_o:.1f} s -> margin {sm_g - sm_o:.1f} LU")
    json.dump(dict(I=I, TP=TP, LRA=LRA, gain_db=gdb, limiter_max_gr_db=gr, short_term_max_realign=sm_g,
                   short_term_max_elsewhere=sm_o, short_term_max_elsewhere_at=at_o, realign_margin_lu=sm_g - sm_o),
              open("out/audio_meas.json", "w"), indent=1)


if __name__ == "__main__":
    main()
