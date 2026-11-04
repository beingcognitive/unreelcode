"""Faraday waves in a 60 mm dish of water, driven by the GLASS voice of score.py.
Pattern dynamics: a Lifshitz-Petrich / Swift-Hohenberg-type amplitude equation (pseudo-spectral, torch MPS)
  du/dt = eps(t) u - c [(k1^2-K^2)(k2^2-K^2)]^2/k1^8 u + alpha u^2 - u^3 - wall(x) u
k1, k2 = Faraday wavenumbers of the two lowest dish notes: the surface responds at HALF the drive frequency
f/2 and k follows the capillary-gravity dispersion w^2 = (g k + s k^3/rho) tanh(k h).  eps follows the drive
amplitude (the same envelope the synth uses).  The surface height is u(x) cos(phase): shown stroboscopically."""
import numpy as np, torch, math
import timeline as T
DEV = torch.device('mps')
N = 1024
LBOX = 0.068                       # m, simulated square
DISH = 0.060                       # m, dish diameter
G, SIG, RHO, DEPTH = 9.81, 0.0728, 1000.0, 0.004

def faraday_k(f_drive):
    w = 2 * math.pi * f_drive / 2
    k = 1000.0
    for _ in range(60):  # Newton on w^2 = (g k + s k^3/rho) tanh(k h)
        th = math.tanh(k * DEPTH)
        F = (G * k + SIG * k ** 3 / RHO) * th - w * w
        dF = (G + 3 * SIG * k ** 2 / RHO) * th + (G * k + SIG * k ** 3 / RHO) * DEPTH * (1 - th * th)
        k -= F / dF
    return k

x = (torch.arange(N, device=DEV) - N / 2 + 0.5) * (LBOX / N)
Y, X = torch.meshgrid(x, x, indexing='ij')
Rr = torch.sqrt(X * X + Y * Y)
fk = torch.fft.fftfreq(N, d=LBOX / N, device=DEV) * 2 * math.pi
KY, KX = torch.meshgrid(fk, fk, indexing='ij'); K2 = KX * KX + KY * KY
WALL = 30.0 * torch.sigmoid((Rr - DISH / 2 + 0.0015) / 0.0006)

def dish_state(t):
    """(k1, k2, drive) from the dish voice at time t."""
    d = sorted(T.dish_drive(t))
    if not d: return None
    amp = math.sqrt(sum(a * a for _, a in d))
    k1 = faraday_k(T.freq(d[0][0]))
    k2 = faraday_k(T.freq(d[1][0])) if len(d) > 1 else k1
    return k1, k2, amp

class Dish:
    def __init__(self, seed=3):
        g = torch.Generator(device='cpu').manual_seed(seed)
        self.u = (torch.randn(N, N, generator=g) * 0.02).to(DEV)
        self.t = 0.0; self.key = None; self.amp = 0.0

    BLOOMS = [(T.tbar(12), 8), (T.tbar(13), 12)]   # art-directed: centred n-fold seeds that bloom outward

    def seed_field(self, k1, k2, n):
        s = torch.zeros_like(self.u)
        for j in range(n):
            th = math.pi * 2 * j / n
            s += torch.cos(k1 * (X * math.cos(th) + Y * math.sin(th)))
            s += torch.cos(k2 * (X * math.cos(th + math.pi / n) + Y * math.sin(th + math.pi / n)))
        return 0.6 * s / (2 * n) / 0.5

    def seed_sym(self, k1, k2, n=12, a=0.05):
        """centred n-fold symmetric seed (stylised: picks the mandala centre at the dish centre)"""
        s = torch.zeros_like(self.u)
        for j in range(n):
            th = math.pi * 2 * j / n
            s += torch.cos(k1 * (X * math.cos(th) + Y * math.sin(th)))
            s += torch.cos(k2 * (X * math.cos(th + math.pi / n) + Y * math.sin(th + math.pi / n)))
        win = torch.exp(-(Rr / 0.022) ** 4)
        self.u = self.u * (1 - win) + a * s / (2 * n) * win

    def run(self, t1, dt=0.05, steps_per_s=1800):
        """advance; each sounding dish note makes its own Faraday ring unstable, with growth
        rate from its envelope (the same one the synth uses)."""
        Kmag = torch.sqrt(K2)
        while self.t < t1 - 1e-9:
            d = T.dish_drive(self.t)
            self.amp = math.sqrt(sum(a * a for _, a in d)) if d else 0.0
            Lk = -0.03 - 0.02 * (Kmag / 1500.0) ** 2 - 2.0 * torch.exp(-(Kmag / 700.0) ** 2)
            for k, a in d:
                kk = faraday_k(T.freq(k))
                Lk = Lk + 0.26 * a * torch.exp(-((Kmag - kk) / (0.07 * kk)) ** 2)
            for tb, nf in self.BLOOMS:
                if tb <= self.t < tb + 1.4:
                    if getattr(self, 'seedkey', None) != tb:
                        st = dish_state(tb + 0.01); self.S = self.seed_field(st[0], st[1], nf); self.seedkey = tb
                    rad = 0.031 * ((self.t - tb) / 1.2) ** 0.7
                    w = torch.sigmoid((rad - Rr) / 0.0015) * 0.25
                    self.u = self.u * (1 - w) + self.S * w * self.u.abs().max().clamp(min=0.3)
            n = int(steps_per_s / 30)
            for _ in range(n):
                u = self.u
                nl = 0.8 * u * u - u * u * u - WALL * u
                uh = (torch.fft.fft2(u) + dt * torch.fft.fft2(nl)) / (1 - dt * Lk)
                self.u = torch.fft.ifft2(uh).real
            self.u = self.u + 3e-3 * torch.randn_like(self.u)
            self.t += 1 / 30
