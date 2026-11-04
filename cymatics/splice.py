"""v3.1: cut the master to the film's timing -> cache/audio_film.wav.
The film opens at sim FILM0 (22 frames after the bar-1 strike) and bar 10 (sim 23.0-25.5 s) is removed, cut on its
bar lines with an 80 ms equal-power crossfade. Picture and sound are cut identically (shots.film_t).
The last 0.5 s crossfades into the opening (the loop). Then the loudness is re-normalised to -14 LUFS and the
true peak checked (4x oversampled)."""
import numpy as np, pyloudnorm as pyln, soundfile as sf
from scipy.signal import resample_poly
import shots as S

x, SR = sf.read('out/audio.wav', always_2d=True)
i = lambda t: int(round(t * SR))
XF = 0.08
a, b = S.CUT
n = i(XF)
A = x[i(S.FILM0):i(a) + n // 2]
B = x[i(b) - n // 2:i(60.0)]
w = np.linspace(0, np.pi / 2, n)[:, None]
mid = A[-n:] * np.cos(w) + B[:n] * np.sin(w)
y = np.concatenate([A[:-n], mid, B[n:]])
y[:i(0.02)] *= np.linspace(0, 1, i(0.02))[:, None]          # 20 ms fade-in (the film opens mid-strike)
# v3.2: the loop. Over the last 0.5 s (the picture's dissolve into frame 0) the held pad crossfades into the opening
# audio, so the seam has no dead air and no jump.
nl = i(0.5); wl = np.linspace(0, np.pi / 2, nl)[:, None]
y[-nl:] = y[-nl:] * np.cos(wl) + y[:nl] * np.sin(wl)
assert abs(len(y) / SR - S.DUR) < 1 / SR + 1e-9, (len(y) / SR, S.DUR)
m = pyln.Meter(SR)
y *= 10 ** ((-14 - m.integrated_loudness(y)) / 20)
tp = 20 * np.log10(np.abs(resample_poly(y, 4, 1, axis=0)).max())
print('dur', round(len(y) / SR, 4), 'LUFS', round(m.integrated_loudness(y), 2), 'TP', round(tp, 2))
assert tp <= -1.5, 'true peak too high'
sf.write('cache/audio_film.wav', y.astype(np.float32), SR, subtype='PCM_24')
