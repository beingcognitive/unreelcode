"""Exact ballistic physics shared by both films. World units are pixels at zoom 1, y grows downward.

Balls fly on parabolas p(t) = p0 + v t + g t^2 / 2. Bars are capsules (segment + radius). A ball hits a bar when its
centre comes within r_ball + r_bar of the segment. Bounces are frictionless reflections with restitution E on the
normal component. `first_hit` finds the earliest contact by dense sampling (0.25 ms) and bisection, so it also
catches glancing hits on bar ends; it is the verifier for both films.
"""
import numpy as np

G = np.array([0.0, 3500.0])   # overridden per film by set_scale (real Earth gravity)
G0 = 9.80665


def set_scale(px_per_m):
    """Earth gravity in px/s^2 for a world where 1 m = px_per_m px."""
    G[1] = G0 * px_per_m
    return G[1]
E = 0.9


def pos(p0, v, t):
    t = np.asarray(t)[..., None]
    return p0 + v * t + 0.5 * G * t * t


def vel(v, t):
    return v + G * t


def seg_dist(P, A, B):
    """distance from points P (n,2) to segments A,B (m,2) -> (n,m)"""
    AB = B - A
    L2 = np.maximum((AB * AB).sum(1), 1e-9)
    AP = P[:, None, :] - A[None]
    h = np.clip((AP * AB[None]).sum(2) / L2[None], 0, 1)
    Q = A[None] + h[..., None] * AB[None]
    return np.linalg.norm(P[:, None, :] - Q, axis=2)


def first_hit(p0, v, A, B, rad, t_max, skip=(), dt=0.00025):
    """Earliest contact of the ball (centre p0, velocity v) with any capsule (A,B,rad= r_ball + r_bar).
    Returns (t, index) or (None, None). `skip`: indices to ignore during the first 2 ms (the bar just left)."""
    ts = np.arange(dt, t_max + dt, dt)
    P = pos(p0, v, ts)
    D = seg_dist(P, A, B) - rad[None]
    if len(skip):
        early = ts < 0.002
        D[np.ix_(early, list(skip))] = 1e9
    hit = np.where((D <= 0).any(1))[0]
    if len(hit) == 0:
        return None, None
    k = hit[0]
    j = int(np.argmin(D[k]))
    lo, hi = (ts[k - 1] if k > 0 else 0.0), ts[k]
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        d = seg_dist(pos(p0, v, [mid]), A[j:j + 1], B[j:j + 1])[0, 0] - rad[j]
        if d <= 0:
            hi = mid
        else:
            lo = mid
    return hi, j


def reflect(v, n, e=None):
    e = E if e is None else e
    vn = np.dot(v, n)
    return v - (1 + e) * vn * n
