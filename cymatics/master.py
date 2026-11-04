"""Masters cache/mix_raw.npy -> out/audio.wav at -14 LUFS, true peak about -2 dBTP (4x oversampled)."""
import numpy as np, pyloudnorm as pyln, soundfile as sf
from scipy.signal import resample_poly
SR = 48000
x = np.load('cache/mix_raw.npy').astype(np.float64)
meter = pyln.Meter(SR)
def tp(y): return 20 * np.log10(np.abs(resample_poly(y, 4, 1, axis=0)).max())
def limit(y, ceil_db):
    # look-ahead peak limiter on the 4x oversampled envelope, smooth gain
    c = 10 ** (ceil_db / 20)
    pk = np.abs(resample_poly(y, 4, 1, axis=0)).max(1).reshape(-1, 4).max(1)[:len(y)]
    g = np.minimum(1, c / np.maximum(pk, 1e-9))
    la = int(0.003 * SR); from scipy.ndimage import minimum_filter1d, uniform_filter1d
    g = minimum_filter1d(g, 2 * la + 1); g = uniform_filter1d(g, la)
    g = minimum_filter1d(g, la)  # keep below after smoothing
    rel = np.empty_like(g); cur = 1.0; a = np.exp(-1 / (0.08 * SR))
    for i in range(len(g)):  # release smoothing
        cur = g[i] if g[i] < cur else a * cur + (1 - a) * g[i]; rel[i] = cur
    return y * rel[:, None]
for it in range(4):
    lu = meter.integrated_loudness(x); x *= 10 ** ((-14 - lu) / 20)
    x = limit(x, -2.3)
    print(it, 'LUFS', round(meter.integrated_loudness(x), 2), 'TP', round(tp(x), 2))
sf.write('out/audio.wav', x.astype(np.float32), SR, subtype='PCM_24')
