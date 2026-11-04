"""Plate physics: modal response of a centre-driven square plate + sand grain dynamics (torch/MPS).
Modes  phi_ab(x,y) = cos(a pi x)cos(b pi y) + cos(b pi x)cos(a pi y),  x,y in [-1,1]  (free-edge,
Neumann approximation), eigenfrequency f_ab = F (a^2+b^2).  Steady-state response to a sine drive at
the centre: W(x) = sum_m phi_m(x) phi_m(0) / (M_m (w_m^2 - w^2 + 2 i zeta w_m w)).
Grains: resting grains are launched when local plate acceleration exceeds g (amplitude > THETA), fly
ballistically (horizontal kick = random + bias down the gradient of vibration energy), land, repeat."""
import numpy as np, torch, math, os
import timeline as T

DEV = torch.device('mps')
G = 1024                       # field grid
AMAX = 15                      # modes a,b <= 15  (k <= 450)
ZETA = 0.001                   # modal damping ratio
THETA = 0.015
SIGA, SIGB = 1.4, 0.12          # random hop spread (plate units/s), scaled by excess amplitude
MM = 271.5                     # mm per plate unit (plate side 543 mm)
GRAV = 9810.0 / MM             # plate units / s^2 for vertical (z kept in plate units too)

xs = torch.linspace(-1, 1, G, device=DEV)
COS = torch.stack([torch.cos(a * math.pi * xs) for a in range(AMAX + 1)])  # [A+1, G]
MODES = [(a, b) for a in range(AMAX + 1) for b in range(a + 1) if a + b > 0]

def _mass(a, b):  # integral of phi^2 over [-1,1]^2 (analytic)
    c = lambda n: 2.0 if n == 0 else 1.0
    if a == b: return 4 * c(a) * c(b)
    return 2 * c(a) * c(b) + (0 if True else 0)  # cross term integrates to 0 for a != b

_cache = {}
def amp_field(k):
    """|W| for a drive at f = F*k, normalised to max 1.  Returned [G,G] float32 on DEV."""
    if k in _cache: return _cache[k]
    w = 2 * math.pi * T.F * k
    W = torch.zeros(G, G, dtype=torch.float32, device=DEV), torch.zeros(G, G, dtype=torch.float32, device=DEV)
    for a, b in MODES:
        wm = 2 * math.pi * T.F * (a * a + b * b)
        den = complex(wm * wm - w * w, 2 * ZETA * wm * w) * _mass(a, b)
        c = 2.0 / den                         # phi_m(0) = 2
        if abs(c) * w * w < 1e-3: continue    # negligible
        phi = torch.outer(COS[b], COS[a]) + torch.outer(COS[a], COS[b])   # [y, x]
        W[0].add_(phi, alpha=c.real); W[1].add_(phi, alpha=c.imag)
    A = torch.sqrt(W[0] ** 2 + W[1] ** 2)
    A = A / torch.quantile(A.flatten()[::97], 0.97)
    _cache[k] = A
    return A

def energy_field(drive):
    """drive: [(k, env)] -> amplitude field sqrt(sum env^2 |W_k|^2) (different frequencies add in energy)."""
    E = torch.zeros(G, G, device=DEV)
    for k, e in drive: E += (e * amp_field(k)) ** 2
    return torch.sqrt(E)

class Sand:
    def __init__(self, n, seed=1):
        g = torch.Generator(device='cpu').manual_seed(seed)
        self.n = n
        p = torch.rand(n, 2, generator=g) * 1.94 - 0.97
        self.p = p.to(DEV)                      # x, y in plate units
        self.z = torch.zeros(n, device=DEV)     # height above plate (plate units)
        self.v = torch.zeros(n, 3, device=DEV)  # vx, vy, vz
        self.fly = torch.zeros(n, dtype=torch.bool, device=DEV)
        self.attr = torch.rand(n, 4, generator=g).to(DEV)   # size, tint, facet seeds
        self.t = 0.0
        torch.manual_seed(seed)

    def sample(self, F):  # bilinear sample of [G,G] field at grain positions
        grid = self.p.view(1, -1, 1, 2)
        return torch.nn.functional.grid_sample(F[None, None], grid, align_corners=True).view(-1)

    def step(self, A, gradE, dt):
        n = self.n
        a = self.sample(A)
        # launch resting grains where acceleration exceeds g
        rest = ~self.fly
        over = (a - THETA).clamp(min=0) / (1 - THETA)
        launch = rest & (torch.rand(n, device=DEV) < (over * 120 * dt).clamp(max=1))
        if launch.any():
            gx = self.sample(gradE[0]); gy = self.sample(gradE[1])
            gn = torch.sqrt(gx * gx + gy * gy) + 1e-6
            vz = (0.25 + 0.75 * torch.rand(n, device=DEV)) * (0.4 + 2.2 * over) * 300 / MM / 1.2
            sig = SIGA * over + SIGB
            bias = 0.45 * over.sqrt()
            vx = sig * torch.randn(n, device=DEV) - bias * gx / gn * torch.tanh(gn * 3)
            vy = sig * torch.randn(n, device=DEV) - bias * gy / gn * torch.tanh(gn * 3)
            nv = torch.stack([vx, vy, vz], 1)
            self.v = torch.where(launch[:, None], nv, self.v)
            self.fly = self.fly | launch
        # ballistic flight
        f = self.fly
        self.p = torch.where(f[:, None], self.p + self.v[:, :2] * dt, self.p)
        self.z = torch.where(f, self.z + self.v[:, 2] * dt, self.z)
        self.v[:, 2] = torch.where(f, self.v[:, 2] - GRAV * dt, self.v[:, 2])
        landed = f & (self.z <= 0)
        self.z = torch.where(landed, torch.zeros_like(self.z), self.z)
        self.fly = self.fly & ~landed
        # walls: reflect inside the plate
        over_edge = self.p.abs() > 0.995
        self.p = torch.where(over_edge, torch.sign(self.p) * 0.995 - (self.p - torch.sign(self.p) * 0.995), self.p)
        self.v[:, :2] = torch.where(over_edge, -self.v[:, :2], self.v[:, :2])
        self.t += dt

    def run(self, t1, dt=0.002):
        while self.t < t1 - 1e-9:
            drive = T.plate_drive(self.t)
            A = energy_field(drive)
            E = A * A
            gy, gx = torch.gradient(E, spacing=2.0 / (G - 1))
            m = 5   # sub-steps sharing one field (10 ms)
            for _ in range(m):
                if self.t >= t1 - 1e-9: break
                self.step(A, (gx, gy), dt)

    def state(self):
        return dict(p=self.p.cpu(), z=self.z.cpu(), v=self.v.cpu(), fly=self.fly.cpu(),
                    attr=self.attr.cpu(), t=self.t, rng=torch.mps.get_rng_state())

    def load(self, s):
        self.p = s['p'].to(DEV); self.z = s['z'].to(DEV); self.v = s['v'].to(DEV)
        self.fly = s['fly'].to(DEV); self.attr = s['attr'].to(DEV); self.t = s['t']
        self.n = len(self.z); torch.mps.set_rng_state(s['rng'])
