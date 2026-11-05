"""Solve a glass surface whose refraction alone draws an image in light.

Collimated light enters the flat back of a clear slab and leaves through a curved front surface z = h(x, y).
Each part of the surface tilts its light toward one point on a screen at distance D (the floor, in the film). So the problem has two steps:
  1. where must each part of the glass send its light? An optimal-transport map from the uniform light on the glass
     to the target brightness on the wall (ot.py).
  2. which surface sends it there? At every point, Snell's law gives the surface normal that turns the ray toward
     its wall point; the surface is the height field whose slopes best match those normals (a Poisson solve).
The result is checked separately by verify.py, which ray-traces the surface with exact refraction.

    python design.py [N]      -> cache/lens.npz, cache/target.png
"""
import sys, time, numpy as np
from pathlib import Path
from scipy.fft import dctn, idctn
from PIL import Image, ImageDraw, ImageFilter
import ot

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"; CACHE.mkdir(exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 256   # cells per side
W = 0.10  # glass: 10 cm
D = 0.50  # floor: 50 cm
N_GLASS = 1.49  # acrylic
K_IN = np.array([0.0, 0.0, N_GLASS])   # the light inside the glass, travelling toward the wall
FLOOR = 0.025   # dimmest wall brightness relative to the brightest; light has to land somewhere


def face_target(n):
    """The unreel() avatar ( ^ ‿ ^ ) as a brightness map, same geometry as avatar_selfportrait.py, on a square."""
    S = 1024; s = S / 1100
    img = Image.new("L", (S, S), 0); d = ImageDraw.Draw(img)
    cx, cy = S / 2, S / 2 + 20 * s
    def box(x0, y0, x1, y1): return (cx + x0 * s, cy + y0 * s, cx + x1 * s, cy + y1 * s)
    d.arc(box(-360, -330, 0, 330), 125, 235, fill=255, width=int(78 * s))      # (
    d.arc(box(0, -330, 360, 330), -55, 55, fill=255, width=int(78 * s))        # )
    for ex in (-120, 120):                                                     # ^ ^
        d.arc(box(ex - 62, -150, ex + 62, -30), 200, 340, fill=255, width=int(34 * s))
    d.chord(box(-135, -40, 135, 180), 0, 180, fill=255)                         # open smile
    blush = Image.new("L", (S, S), 0)
    for bx in (-215, 215):
        ImageDraw.Draw(blush).ellipse(box(bx - 55, 5, bx + 55, 60), fill=255)
    a = np.asarray(img.filter(ImageFilter.GaussianBlur(3 * s)), np.float64) / 255
    a = np.maximum(a, np.asarray(blush.filter(ImageFilter.GaussianBlur(12 * s)), np.float64) / 255 * 0.35)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((n, n), Image.LANCZOS), np.float64) / 255
    return FLOOR + (1 - FLOOR) * a


def neumann_solve(c):
    """Solve L u = c, L the grid graph Laplacian (degree - adjacency), mean(u) = 0. Diagonalised by DCT-II."""
    m0, m1 = c.shape
    lam = (2 - 2 * np.cos(np.pi * np.arange(m0) / m0))[:, None] + (2 - 2 * np.cos(np.pi * np.arange(m1) / m1))[None]
    lam[0, 0] = 1.0
    u = dctn(c, type=2, norm="ortho") / lam
    u[0, 0] = 0.0
    return idctn(u, type=2, norm="ortho")


def surface(Qy, Qx, n, passes=3):
    """Height field on the n x n cell centres of the glass whose refraction sends cell (iy, ix) to wall (Qy, Qx)."""
    h = W / n
    c = (np.arange(n) + 0.5) * h
    Py, Px = np.meshgrid(c, c, indexing="ij")
    H = np.zeros((n, n))
    for _ in range(passes):                                      # the ray leaves from z = H, so refine twice
        u = np.stack([Qx - Px, Qy - Py, D - H], -1)
        u /= np.linalg.norm(u, axis=-1, keepdims=True)
        # Snell: n1·k_in − n2·k_out
        # is along the normal
        nrm = K_IN - u
        sx, sy = -nrm[..., 0] / nrm[..., 2], -nrm[..., 1] / nrm[..., 2]
        Ex = 0.5 * (sx[:, 1:] + sx[:, :-1]) * h                  # wanted height steps between neighbours
        Ey = 0.5 * (sy[1:, :] + sy[:-1, :]) * h
        b = np.zeros((n, n))
        b[:, 1:] += Ex; b[:, :-1] -= Ex
        b[1:, :] += Ey; b[:-1, :] -= Ey
        H = neumann_solve(b); H -= H.min()
    rx = np.diff(H, axis=1) - Ex; ry = np.diff(H, axis=0) - Ey
    fit = np.sqrt((np.sum(rx ** 2) + np.sum(ry ** 2)) / (np.sum(Ex ** 2) + np.sum(Ey ** 2)))
    return H, fit


if __name__ == "__main__":
    t0 = time.time()
    tgt = face_target(N)                                         # image rows top-down
    Image.fromarray((tgt * 255).astype(np.uint8)).save(CACHE / "target.png")
    T = tgt[::-1].copy()                                         # rows bottom-up, so row index is y
    print(f"N={N}: optimal transport", flush=True)
    Y1, Y2 = ot.transport_map(T)                                 # wall cell coordinates (row = y, col = x)
    h = W / N
    Qy, Qx = (Y1 + 0.5) * h, (Y2 + 0.5) * h
    print(f"  map done ({time.time() - t0:.0f} s); largest shift {np.hypot(Qy - (np.arange(N)[:, None] + .5) * h, Qx - (np.arange(N)[None] + .5) * h).max() * 100:.2f} cm", flush=True)
    H, fit = surface(Qy, Qx, N)
    print(f"  surface: relief {H.max() * 1e3:.2f} mm, slope mismatch {fit:.2%} (curl the surface cannot follow)")
    np.savez_compressed(CACHE / "lens.npz", H=H, W=W, D=D, n=N_GLASS, N=N)
    print(f"done in {time.time() - t0:.0f} s -> cache/lens.npz", flush=True)
