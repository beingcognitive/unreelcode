"""Synthesised sound from the simulated impacts (out/film_chain.json events), placed on the film's timeline.

Inputs from the simulation: every new contact (domino-domino, domino-floor, needle-domino) with its time, the relative
normal speed and the two masses, giving an impact energy E = 1/2 m_eff v^2 (m_eff = m1 m2 / (m1 + m2)).
Choices (display): pitch from size, f0 = 2600 Hz * (h / 5 mm)^-0.55 (a real block's modes scale as 1/h, which would
be inaudible for the big ones); loudness rises 1.75 dB per decade of impact energy; ring time grows with size.
A sparse bed: one soft tone at each domino's first movement, one step down an A natural-minor scale per domino (each
a different pitch), ringing for its cycle, so the bed slows with the chain. The last domino's landing is a sub-bass thud, then silence.
Writes out/audio/stem_rest.npy and stem_thud.npy (48 kHz stereo float); master.py masters them to out/audio/audio.wav.
"""
import json, math, os, sys, wave
import numpy as np

import importlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render'))
film = importlib.import_module(os.environ.get('TL_MODULE', 'timeline'))  # timeline: video_time_of_sim, T_TOTAL, ...
CACHE = os.environ.get('AUDIO_DIR', 'out/audio')

SR = 48000
J = film.J
DOM = J["dom"]; N = len(DOM)
H = {f"d{D['i']+1}": D["h"] for D in DOM}
M = {f"d{i+1}": J["masses"][i] for i in range(N)}
T_TOTAL = film.T_TOTAL
L = int(T_TOTAL * SR) + SR
out = np.zeros((L, 2))
rng = np.random.default_rng(3)


def place(sig, t, gain_db, pan=0.0):
    i0 = int(round(t * SR))
    if i0 >= L: return
    n = min(len(sig), L - i0)
    g = 10 ** (gain_db / 20)
    out[i0:i0 + n, 0] += sig[:n] * g * math.cos((pan + 1) * math.pi / 4)
    out[i0:i0 + n, 1] += sig[:n] * g * math.sin((pan + 1) * math.pi / 4)


def onepole_lp(x, fc):
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x); s = 0.0
    # vectorised enough for short bursts
    for k in range(len(x)):
        s = (1 - a) * x[k] + a * s; y[k] = s
    return y


def click(h, energy_rel):
    """a struck block: 4 inharmonic modes + a short noise transient"""
    sc = h / 0.005
    f0 = 2600.0 * sc ** -0.55
    tau = 0.022 * sc ** 0.38
    dur = min(6 * tau + 0.02, 3.0)
    t = np.arange(int(dur * SR)) / SR
    sig = np.zeros_like(t)
    for r, a, dk in ((1.0, 1.0, 1.0), (2.32, 0.55, 0.7), (4.25, 0.32, 0.5), (6.63, 0.18, 0.35)):
        f = f0 * r
        if f < SR / 2.2:
            sig += a * np.sin(2 * math.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / (tau * dk))
    att = np.minimum(1.0, t / (0.0008 * sc ** 0.3))
    sig *= att
    nl = int(min(0.004 * sc ** 0.35, 0.08) * SR)
    nz = rng.normal(0, 1, nl) * np.exp(-np.arange(nl) / (nl / 4))
    nz = onepole_lp(nz, min(9000.0, 6 * f0))
    sig[:nl] += 0.6 * nz
    # big impacts: add body (a short low sine) for weight
    if sc > 100:
        fb = max(28.0, f0 * 0.5)
        sig += 0.8 * np.sin(2 * math.pi * fb * t) * np.exp(-t / (tau * 1.4)) * att
    return sig / (np.max(np.abs(sig)) + 1e-9)


def giant_thud():
    """the 66 t slab landing: a sub-bass drop (55 -> 24 Hz) with a long tail, a short low rumble and a wooden crack"""
    dur = 7.0
    t = np.arange(int(dur * SR)) / SR
    f = 24 + 31 * np.exp(-t / 0.22)
    ph = 2 * math.pi * np.cumsum(f) / SR
    tail = np.exp(-t / 2.4) * (0.55 + 0.45 * np.exp(-t / 0.3))
    sub = np.sin(ph) * tail * np.minimum(1, t / 0.006)
    nz = rng.normal(0, 1, len(t)) * np.exp(-t / 1.5) * np.minimum(1, t / 0.01)
    rum = onepole_lp(onepole_lp(nz, 380.0), 380.0)
    rum /= np.max(np.abs(rum)) + 1e-9
    crack = np.zeros_like(t)
    for r, a in ((1.0, 1.0), (2.32, 0.6), (4.25, 0.35), (6.63, 0.2)):
        crack += a * np.sin(2 * math.pi * 92 * r * t + r) * np.exp(-t / (0.16 / r ** 0.3))
    sig = 0.8 * sub + 1.3 * rum + 0.9 * crack
    sig = np.tanh(6.0 * sig / np.max(np.abs(sig)))  # saturation (tanh): a denser, heavier body
    end = np.minimum(1, (dur - t) / 1.0)          # fade the very end to true silence
    return sig * end / np.max(np.abs(sig))


def bell(freq, ring):
    """a soft struck bell: quick strike, short decay (ring seconds), upper partials decaying faster, low-passed"""
    dur = ring * 4
    t = np.arange(int(dur * SR)) / SR
    att = np.minimum(1, t / 0.006)
    sig = (np.sin(2 * math.pi * freq * t) * np.exp(-t / ring)
           + 0.10 * np.sin(2 * math.pi * 2.0 * freq * t + 0.3) * np.exp(-t / (ring * 0.45))
           + 0.025 * np.sin(2 * math.pi * 3.0 * freq * t) * np.exp(-t / (ring * 0.25))) * att
    sig = onepole_lp(sig, 2500.0)
    return sig / np.max(np.abs(sig))


def landing_chord(f_root, dur=6.0):
    """the resolution: a warm, low A-minor chord (root, octave, fifth, octave, minor third) with a slow bloom and a
    long, soft decay; slightly detuned pairs for warmth"""
    t = np.arange(int(dur * SR)) / SR
    env = (1 - np.exp(-t / 0.05)) * np.exp(-t / 1.9)
    sig = np.zeros_like(t)
    for ratio, amp in ((0.5, 0.9), (1.0, 1.0), (1.5, 0.55), (2.0, 0.45), (2.378, 0.32)):
        for det in (-0.0015, 0.0015):
            sig += amp * np.sin(2 * math.pi * f_root * ratio * (1 + det) * t) * np.exp(-t * 0.15 * ratio)
    sig = onepole_lp(sig * env, 1400.0)
    end = np.minimum(1, (dur - t) / 0.8)
    return sig * end / np.max(np.abs(sig))


def soft_thud():
    """a softened, shorter body thump under the chord"""
    dur = 0.9
    t = np.arange(int(dur * SR)) / SR
    f = 38 + 24 * np.exp(-t / 0.08)
    sub = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t / 0.28) * np.minimum(1, t / 0.008)
    nz = onepole_lp(onepole_lp(rng.normal(0, 1, len(t)) * np.exp(-t / 0.06), 300.0), 300.0)
    sig = sub + 0.35 * nz / (np.max(np.abs(nz)) + 1e-9)
    return sig / np.max(np.abs(sig))


def tap(freq):
    """a soft in-key wooden tap (for the giant's bounces)"""
    t = np.arange(int(0.6 * SR)) / SR
    sig = (np.sin(2 * math.pi * freq * t) + 0.25 * np.sin(2 * math.pi * 4.0 * freq * t) * np.exp(-t / 0.03)) \
        * np.exp(-t / 0.18) * np.minimum(1, t / 0.003)
    return sig / np.max(np.abs(sig))


def main():
    ev = J["events"]
    E1 = None
    # 1) the chain's impacts: the first contact of each neighbouring pair
    first = {}
    for e in ev:
        k = tuple(sorted((e["a"], e["b"])))
        if k not in first: first[k] = e
    impacts = []
    for k, e in first.items():
        a, b = k
        if a.startswith("d") and b.startswith("d"):
            ma, mb = M[a], M[b]
            me = ma * mb / (ma + mb)
            impacts.append((e["t"], min(H[a], H[b]), 0.5 * me * e["vn"] ** 2, "dd"))
    # 2) later hard contacts: dominoes landing on the floor or on each other (vn above 15 % of sqrt(g h)),
    #    merged per pair within a scale-dependent window
    last = {}
    for e in ev:
        k = tuple(sorted((e["a"], e["b"])))
        a, b = k
        doms = [x for x in k if x.startswith("d")]
        if not doms or "needle" in k: continue
        h = min(H[x] for x in doms)
        if e["t"] < 0.01 or e["vn"] < 0.15 * math.sqrt(9.81 * h): continue
        if first.get(k) is e and len(doms) == 2: continue
        # a domino long at rest (more than 20 of its fall times after it started) is not sounded: the stiff contacts
        # give a resting piece a rare numerical jolt (the 5 mm first domino, 18 s after it fell, read as a stray tick)
        i_small = min(int(x[1:]) for x in doms) - 1
        if e["t"] - J["t_start"][i_small] > 20 * math.sqrt(H[f"d{i_small+1}"] / 9.81): continue
        win = 0.25 * math.sqrt(h / 9.81)
        if k in last and e["t"] - last[k] < win: continue
        last[k] = e["t"]
        if len(doms) == 2:
            ma, mb = M[doms[0]], M[doms[1]]; me = ma * mb / (ma + mb)
        else:
            me = M[doms[0]]
        impacts.append((e["t"], h, 0.5 * me * e["vn"] ** 2, "floor" if "floor" in k else "dd2"))
    impacts.sort()
    E_first = [x for x in impacts if x[3] == "dd"][0][2]
    s_land = None; bounces = []
    for t, h, E, kind in impacts:
        if t > film.S_END: continue
        rel = math.log10(max(E, 1e-15) / E_first)
        gain = -30 + 1.75 * rel
        if kind != "dd": gain -= 4
        if kind == "floor" and h == DOM[-1]["h"] and E > 1e4:
            if s_land is None:
                s_land = t
            else:
                bounces.append((t, E))
            continue
        place(click(h, rel), film.video_time_of_sim(t), min(gain, -16.0), pan=rng.uniform(-0.25, 0.25))
    # needle touch: a tiny metallic tick
    tn = [e["t"] for e in ev if "needle" in (e["a"], e["b"])][0]
    tt = np.arange(int(0.05 * SR)) / SR
    tick = np.sin(2 * math.pi * 6200 * tt) * np.exp(-tt / 0.006) + 0.5 * np.sin(2 * math.pi * 9100 * tt) * np.exp(-tt / 0.004)
    place(tick, film.video_time_of_sim(tn), -40)
    # giant landing
    if s_land is None:
        s_land = film.S_LAND
    # the landing is the resolution of the music: a warm low A-minor chord with a soft, shorter thud under it,
    # and the bounces as soft in-key taps (all in the main mix, no separate peak stem)
    global out
    A1 = 55.0
    tl = film.video_time_of_sim(s_land)
    place(landing_chord(A1 * 2), tl, -14.5)
    place(soft_thud(), tl, -18.0)
    for k, (tb, Eb) in enumerate(bounces[:4]):
        place(tap(440.0 * (1.0 if k % 2 == 0 else 1.335)), film.video_time_of_sim(tb), -24.0 - 3 * k)
    thud = np.zeros_like(out)
    # the bed: one soft bell per domino start, one step down an A natural-minor scale per domino, so every domino has
    # its own pitch (20 notes, F5 -> A2) and the last one lands on the root of the closing chord;
    # short decays that grow with the domino's size (0.3 s for the smallest, ~1.4 s for the largest)
    scale = [0, 2, 3, 5, 7, 8, 10]
    steps = [45 + 12 * o + sc for o in range(4) for sc in scale]
    notes = [440 * 2 ** ((steps[N - 1 - k] - 69) / 12) for k in range(N)]
    assert len(set(notes)) == N
    ts = J["t_start"]
    for i, s in enumerate(ts):
        ring = 0.30 * 1.5 ** (i / 5.0)
        place(bell(notes[i], ring), film.video_time_of_sim(s), -21 + 0.2 * i, pan=0.3 * math.sin(i))
    # end card: one soft tone on the first note (for the loop)
    place(bell(notes[0], 0.6), film.T_CARD + 0.3, -26)
    # room: a short synthetic reverb (exponentially decaying noise, decorrelated L/R), 18 % wet; the thud dry
    ir_len = int(1.3 * SR)
    tir = np.arange(ir_len) / SR
    wet = np.zeros_like(out)
    for ch in range(2):
        ir = rng.normal(0, 1, ir_len) * np.exp(-tir / 0.32)
        ir /= np.sqrt(np.sum(ir ** 2))
        nfft = 1 << int(math.ceil(math.log2(L + ir_len)))
        wet[:, ch] = np.fft.irfft(np.fft.rfft(out[:, ch], nfft) * np.fft.rfft(ir, nfft), nfft)[:L]
    nT = int(T_TOTAL * SR)
    rest_mix = (out + 0.18 * wet)[:nT]
    thud_mix = thud[:nT]
    fade = int(0.5 * SR)
    rest_mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    os.makedirs(CACHE, exist_ok=True)
    np.save(f"{CACHE}/stem_rest.npy", rest_mix.astype(np.float32)); np.save(f"{CACHE}/stem_thud.npy", thud_mix.astype(np.float32))
    json.dump(dict(t_land_video=film.video_time_of_sim(s_land)), open(f"{CACHE}/stems.json", "w"))
    print(f"impacts placed: {len(impacts)}; giant landing at sim {s_land:.3f} s (video {film.video_time_of_sim(s_land):.2f} s); "
          f"{nT/SR:.2f} s")


if __name__ == "__main__":
    main()
