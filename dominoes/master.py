"""Master: the landing thud sets the peak (its true peak about -1.5 dBTP), and the rest of the mix (clicks, bed) is
scaled so the whole film integrates to -14 LUFS. A look-ahead limiter at -1.3 dBFS is a safety net only.
Everything is measured AFTER AAC encoding with ffmpeg ebur128 (integrated, true peak, LRA, and the maximum
short-term loudness around the landing)."""
import json, os, re, subprocess
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

SR = 48000
CACHE = os.environ.get("AUDIO_DIR", "out/audio")


def write_wav(path, x):
    y = np.clip(x, -1, 1)
    b = (y * (2 ** 23 - 1)).astype(np.int32)
    raw = np.zeros((len(b), 2, 3), np.uint8)
    for k in range(3):
        raw[:, :, k] = (b >> (8 * k)) & 0xFF
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(3); w.setframerate(SR); w.writeframes(raw.tobytes())


def ebur(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-v", "verbose", "-i", path, "-filter_complex", "ebur128=peak=true:framelog=verbose",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])
    TP = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1])
    LRA = float(re.findall(r"LRA:\s+(-?[\d.]+) LU", r)[-1])
    S = [(float(t), float(v)) for t, v in re.findall(r"t:\s*([\d.]+)\s+TARGET.*?S:\s*(-?[\d.inf]+)", r) if v not in ("-inf", "inf")]
    return I, TP, LRA, S


def limit(x, ceiling_db, look=0.003, release=0.08):
    c = 10 ** (ceiling_db / 20)
    a = np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, c / np.maximum(a, 1e-12))
    n = int(look * SR)
    g = sliding_window_view(np.concatenate([need, np.ones(n)]), n + 1).min(axis=1)[:len(need)]
    rel = np.exp(-1 / (release * SR)); out = np.empty_like(g); s = 1.0
    for k in range(len(g)):
        s = min(g[k], rel * s + (1 - rel) * g[k]); out[k] = s
    return x * out[:, None], 20 * np.log10(out.min())


def main():
    rest = np.load(f"{CACHE}/stem_rest.npy").astype(np.float64)
    thud = np.load(f"{CACHE}/stem_thud.npy").astype(np.float64)
    t_land = json.load(open(f"{CACHE}/stems.json"))["t_land_video"]
    pk = np.abs(thud).max()
    thud_db = (-1.8 - 20 * np.log10(pk)) if pk > 0 else 0.0  # thud sample peak at -1.8 dBFS (if a thud stem exists)
    rest_db = 0.0
    for it in range(14):
        mix = rest * 10 ** (rest_db / 20) + thud * 10 ** (thud_db / 20)
        y, gr = limit(mix, -1.3)
        write_wav(f"{CACHE}/audio.wav", y)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{CACHE}/audio.wav", "-c:a", "aac", "-b:a", "256k",
                        f"{CACHE}/audio_test.m4a"], check=True)
        I, TP, LRA, S = ebur(f"{CACHE}/audio_test.m4a")
        sl = [v for t, v in S if t_land - 0.5 <= t <= t_land + 4.0]
        sm = max(sl) if sl else float("nan")
        print(f"iter {it}: rest {rest_db:+.2f} dB, thud {thud_db:+.2f} dB -> I {I:.2f} LUFS, TP {TP:.2f} dBTP, "
              f"LRA {LRA:.1f}, thud short-term max {sm:.1f} LUFS, limiter max GR {gr:.2f} dB", flush=True)
        ok = abs(I + 14) <= 0.15 and TP <= -1.0
        if ok: break
        if TP > -1.0:
            thud_db -= (TP + 1.0) + 0.3; continue
        rest_db += 1.2 * (-14 - I)
    json.dump(dict(I=I, TP=TP, LRA=LRA, thud_short_term_max=sm, plr_thud=sm - I, rest_db=rest_db, thud_db=thud_db,
                   limiter_max_gr_db=gr), open(f"{CACHE}/audio_meas.json", "w"), indent=1)


if __name__ == "__main__":
    main()
