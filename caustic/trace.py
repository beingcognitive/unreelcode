"""The film's light: millions of rays through the solved glass, refracted exactly, counted on the wall (torch, MPS).

The glass is the interpolating cubic B-spline through the solved heights (cache/lens.npz), so its surface and slopes
are smooth (C2) everywhere, not just at the solver's grid points. Every ray starts at a fixed, jittered point on the
glass, leaves through the curved face by the vector form of Snell's law, flies in a straight line to the wall plane
z = d, and adds its share of light to the four nearest wall pixels. Nothing is drawn from the target image.

    g = Glass(); E = g.wall(d=0.5)        # E: irradiance on the wall, 1.0 = the bare lamp beam
"""
import numpy as np, torch
from pathlib import Path
from scipy.ndimage import spline_filter

ROOT = Path(__file__).parent
DEV = "mps" if torch.backends.mps.is_available() else "cpu"
FW, FH = 1080, 1920                 # frame
PX = 0.12 / FW                      # metres of wall per pixel: the frame is 12 cm of wall wide


def bspline_w(t):
    """cubic B-spline weights and their derivatives for fractional offset t (4 taps)."""
    t2, t3, s = t * t, t * t * t, 1 - t
    w = torch.stack([s * s * s / 6, (3 * t3 - 6 * t2 + 4) / 6, (-3 * t3 + 3 * t2 + 3 * t + 1) / 6, t3 / 6])
    dw = torch.stack([-s * s / 2, (3 * t2 - 4 * t) / 2, (-3 * t2 + 2 * t + 1) / 2, t2 / 2])
    return w, dw


class Glass:
    def __init__(self, lens=ROOT / "cache" / "lens.npz", R=6144, seed=3, chunk=1 << 22):
        z = np.load(lens)
        self.H, self.W, self.D, self.n = z["H"], float(z["W"]), float(z["D"]), float(z["n"])
        M = self.H.shape[0]; self.M = M; h = self.W / M
        coef = np.pad(spline_filter(self.H, order=3, mode="mirror"), 2, mode="reflect")
        C = torch.tensor(coef, dtype=torch.float32, device=DEV)
        g = torch.Generator().manual_seed(seed)
        self.R = R
        st = self.W / R
        hs, hxs, hys, pxs, pys = [], [], [], [], []
        idx = torch.arange(R * R)
        for a in range(0, R * R, chunk):
            k = idx[a:a + chunk]
            jit = torch.rand((len(k), 2), generator=g)
            py = ((k // R).float() + jit[:, 0]) * st
            px = ((k % R).float() + jit[:, 1]) * st
            py, px = py.to(DEV), px.to(DEV)
            cy, cx = py / h - 0.5, px / h - 0.5                       # cell centres sit at (i + 0.5) h
            iy, ix = torch.floor(cy), torch.floor(cx)
            wy, dwy = bspline_w(cy - iy); wx, dwx = bspline_w(cx - ix)
            iy, ix = iy.long() + 1, ix.long() + 1                     # +2 pad, -1 first tap
            val = torch.zeros_like(px); gx = torch.zeros_like(px); gy = torch.zeros_like(px)
            for a_ in range(4):
                for b_ in range(4):
                    c = C[(iy + a_).clamp(0, M + 3), (ix + b_).clamp(0, M + 3)]
                    val += wy[a_] * wx[b_] * c
                    gx += wy[a_] * dwx[b_] * c
                    gy += dwy[a_] * wx[b_] * c
            hs.append(val); hxs.append(gx / h); hys.append(gy / h); pxs.append(px); pys.append(py)
        self.h = torch.cat(hs); self.hx = torch.cat(hxs); self.hy = torch.cat(hys)
        self.px = torch.cat(pxs); self.py = torch.cat(pys)
        self.ray_flux = (self.W / R) ** 2 / PX ** 2                   # one ray's light, in "bare beam" pixel units
        self._dirs = {}

    def directions(self, beam=(0.0, 0.0)):
        """Exit direction of every ray for a lamp tilted by beam = (about y, about x) degrees, in air."""
        key = (round(beam[0], 6), round(beam[1], 6))
        if key in self._dirs: return self._dirs[key]
        ax, ay = np.sin(np.radians(beam[0])), np.sin(np.radians(beam[1]))
        kx, ky = ax / self.n, ay / self.n                             # refracted into the flat back face
        kz = np.sqrt(1 - kx * kx - ky * ky)
        nz = 1 / torch.sqrt(1 + self.hx ** 2 + self.hy ** 2)
        nx, ny = -self.hx * nz, -self.hy * nz                          # outward normal of z = h(x, y)
        eta = self.n
        c1 = nx * kx + ny * ky + nz * kz
        k2 = 1 - eta * eta * (1 - c1 * c1)
        f = torch.sqrt(torch.clamp(k2, min=0)) - eta * c1
        t = (eta * kx + f * nx, eta * ky + f * ny, eta * kz + f * nz)  # exact vector Snell
        ok = k2 > 0
        if len(self._dirs) > 2: self._dirs.clear()
        self._dirs[key] = (t, ok)
        return t, ok

    def wall(self, d, beam=(0.0, 0.0), centre=None, size=(FH, FW), px=PX):
        """Irradiance on the wall plane z = d (1.0 = bare beam), as an image rows-down; centre = wall point at
        the image centre (default: the glass centre)."""
        (tx, ty, tz), ok = self.directions(beam)
        cx, cy = centre if centre is not None else (self.W / 2, self.W / 2)
        Hh, Ww = size
        s = (d - self.h) / tz
        X = self.px + s * tx; Y = self.py + s * ty
        fc = (X - cx) / px + Ww / 2 - 0.5                              # pixel coordinates (centres at +0.5)
        fr = (cy - Y) / px + Hh / 2 - 0.5
        c0, r0 = torch.floor(fc), torch.floor(fr)
        ac, ar = fc - c0, fr - r0
        c0, r0 = c0.long(), r0.long()
        img = torch.zeros(Hh * Ww, device=DEV)
        for dr, dc, w in ((0, 0, (1 - ar) * (1 - ac)), (0, 1, (1 - ar) * ac), (1, 0, ar * (1 - ac)), (1, 1, ar * ac)):
            rr, cc = r0 + dr, c0 + dc
            m = ok & (rr >= 0) & (rr < Hh) & (cc >= 0) & (cc < Ww)
            img.index_add_(0, (rr * Ww + cc)[m], w[m])
        return (img.reshape(Hh, Ww) * self.ray_flux).cpu().numpy()

    def sharpness(self, E, target, d=None, beam=(0.0, 0.0)):
        """How much the light on the wall looks like the target: correlation over the glass-sized square
        straight behind the glass (the design region), after a 1-cell blur. 1.0 = identical."""
        from scipy.ndimage import gaussian_filter, zoom
        Hh, Ww = E.shape
        side = self.W / PX
        r0 = int(round(Hh / 2 - side / 2)); c0 = int(round(Ww / 2 - side / 2)); n = int(round(side))
        sq = E[r0:r0 + n, c0:c0 + n]
        sq = zoom(sq, target.shape[0] / sq.shape[0], order=1)[:target.shape[0], :target.shape[1]]
        sq = gaussian_filter(sq, 1.0)
        return float(np.corrcoef(sq.ravel(), target.ravel())[0, 1])
