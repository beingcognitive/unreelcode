"""Check the solved glass independently of the solver: shoot rays through it with exact Snell refraction
(no small-angle approximation) and count where they land on the wall.

    python verify.py [rays_per_side]   -> cache/verify.png (target | wall | glass relief), prints the match
"""
import sys, numpy as np
from pathlib import Path
from PIL import Image
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).parent; CACHE = ROOT / "cache"
z = np.load(CACHE / "lens.npz")
H, W, D, NG, N = z["H"], float(z["W"]), float(z["D"]), float(z["n"]), int(z["N"])
M = H.shape[0]; g = (np.arange(M) + 0.5) * W / M; dg = g[1] - g[0]
hy, hx = np.gradient(H, dg)                                       # H[iy, ix]
interp = lambda A: RegularGridInterpolator((g, g), A)
fH, fx, fy = interp(H), interp(hx), interp(hy)

R = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
rng = np.random.default_rng(0)
wall = np.zeros((N, N))
step = W / R
for row in range(0, R, 256):                                      # in strips, to keep memory small
    yy, xx = np.meshgrid((np.arange(row, min(row + 256, R)) + 0.5) * step, (np.arange(R) + 0.5) * step, indexing="ij")
    pts = np.stack([yy.ravel(), xx.ravel()], -1) + rng.uniform(-0.5, 0.5, (yy.size, 2)) * step
    pts = np.clip(pts, g[0], g[-1])
    h, sx, sy = fH(pts), fx(pts), fy(pts)
    nrm = np.stack([-sx, -sy, np.ones_like(sx)], -1); nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    k = np.array([0.0, 0.0, 1.0]); eta = NG / 1.0
    c1 = nrm[:, 2]                                                # cos(angle) between ray and outward normal
    k2 = 1 - eta * eta * (1 - c1 * c1)
    tir = k2 < 0
    t = eta * k[None] + (np.sqrt(np.maximum(k2, 0)) - eta * c1)[:, None] * nrm   # exact vector Snell
    s = (D - h) / t[:, 2]
    X = pts[:, 1] + s * t[:, 0]; Y = pts[:, 0] + s * t[:, 1]
    ok = ~tir
    hist, _, _ = np.histogram2d(Y[ok], X[ok], bins=N, range=[[0, W], [0, W]])
    wall += hist
wall = wall[::-1]                                                 # top-down image rows
tgt = np.asarray(Image.open(CACHE / "target.png"), np.float64) / 255
w = wall / wall.mean() * tgt.mean()
from scipy.ndimage import gaussian_filter
ws = gaussian_filter(w, 1.0)
corr = np.corrcoef(ws.ravel(), tgt.ravel())[0, 1]
print(f"rays {R * R:,}  landed on wall {wall.sum() / (R * R):.3%}  correlation with target {corr:.4f}")
print(f"glass relief {H.max() * 1e3:.2f} mm over {W * 100:.0f} cm, max slope {np.hypot(hx, hy).max():.3f}")

def tone(a): return (np.clip(a / np.percentile(a, 99.5), 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
relief = H[::-1]; relief = (relief - relief.min()) / (np.ptp(relief) + 1e-12)
shade = np.clip(0.5 + 40 * (np.gradient(relief, axis=1) - np.gradient(relief, axis=0)), 0, 1)
panels = [tone(tgt), tone(ws), (shade * 255).astype(np.uint8)]
Image.fromarray(np.concatenate(panels, 1)).save(CACHE / "verify.png")
print("-> cache/verify.png  (target | light on the wall, ray traced | glass surface, shaded)")
