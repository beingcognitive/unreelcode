"""What reads as bouncy: from a chain run's 1 kHz poses, measure per domino
 - landing on the floor: peak rebound lift of the far end (cm and fraction of h), number of bounces (lift above
   0.2 % of h between ground contacts), settle time (until the far end stays within 0.05 % of h of its final height);
 - domino-on-domino: peak gap opened between the striker's top edge and the struck face after first contact,
   number of re-contacts;
 - unphysical checks: total mechanical energy of the last three dominoes after the giant lands (must not rise),
   residual jitter after settling (rms angular speed in the last 0.5 s).
usage: python render/bounce_metrics.py out/film_chain"""
import json, math, sys
import numpy as np

P = sys.argv[1]
J = json.load(open(P + ".json")); Z = np.load(P + ".npz")
T, Q = Z["t"], Z["qpos"]; DOM = J["dom"]; N = len(DOM); M = J["masses"]; G = 9.81


def R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def pt(j, i, local):
    q = Q[j]; return q[7 * i:7 * i + 3] + R(q[7 * i + 3:7 * i + 7]) @ np.asarray(local)


def series(i, local, j0, j1, step=1):
    return np.array([pt(j, i, local) for j in range(j0, j1, step)])


out = {"landing": [], "dd": []}
t85 = J["t_85"]
for i in range(N):
    if t85[i] is None:
        continue
    D = DOM[i]; h, d = D["h"], D["d"]
    j0 = np.searchsorted(T, t85[i] - 0.02); j1 = len(T)
    # far end of the slab (top edge, centre) height over time
    z = series(i, (0, 0, h / 2), j0, j1)[:, 2]
    zf = z[-1]
    # first time it reaches its lowest point near the floor = first impact
    k_imp = int(np.argmin(z[: max(10, int(0.6 * len(z)))]))
    after = z[k_imp:]
    lift = float(after.max() - zf)
    # count bounces: excursions above 0.2 % h separated by returns below 0.05 % h
    thr_up, thr_dn = 0.002 * h, 0.0005 * h
    nb = 0; up = False
    for v in after - zf:
        if not up and v > thr_up: nb += 1; up = True
        elif up and v < thr_dn: up = False
    dev = np.abs(after - zf) > 0.0005 * h
    settle = float((np.nonzero(dev)[0].max() + 1) / 1000.0) if dev.any() else 0.0
    out["landing"].append(dict(domino=i + 1, h=h, lift_cm=lift * 100, lift_frac=lift / h, bounces=nb, settle_s=settle,
                               impact_t=float(T[j0 + k_imp])))
first = {}
for e in J["events"]:
    k = tuple(sorted((e["a"], e["b"])))
    first.setdefault(k, []).append(e["t"])
for i in range(N - 1):
    a, b = f"d{i+1}", f"d{i+2}"
    ts = first.get(tuple(sorted((a, b))), [])
    if not ts: continue
    t0 = ts[0]
    D, E = DOM[i], DOM[i + 1]
    j0 = np.searchsorted(T, t0); j1 = min(len(T), j0 + int(1.5 * 1000 * math.sqrt(E["h"] / G)) + 50)
    tip = series(i, (D["d"] / 2, 0, D["h"] / 2), j0, j1)            # striker's top front edge
    gaps = []
    for k, j in enumerate(range(j0, j1)):
        q = Q[j]; Rj = R(q[7 * (i + 1) + 3:7 * (i + 1) + 7]); c = q[7 * (i + 1):7 * (i + 1) + 3]
        n = Rj @ np.array([-1.0, 0, 0]); p0 = c + Rj @ np.array([-E["d"] / 2, 0, 0])
        gaps.append(float((tip[k] - p0) @ n))
    gaps = np.array(gaps)
    # separations: the gap opening above 0.5 % of the striker's height, then closing again
    recont = 0; opened = False
    for g in gaps:
        if not opened and g > 0.005 * D["h"]: recont += 1; opened = True
        elif opened and g < 0.001 * D["h"]: opened = False
    out["dd"].append(dict(pair=f"{a}->{b}", h=D["h"], gap_cm=max(0.0, gaps.max()) * 100, gap_frac=max(0.0, gaps.max()) / D["h"],
                          recontacts=recont))
# energy check after the giant's first landing: last 3 dominoes
jl = np.searchsorted(T, t85[-1]); E = []
for j in range(jl, len(T) - 1, 5):
    e = 0.0
    for i in (N - 3, N - 2, N - 1):
        p1 = Q[j][7 * i:7 * i + 3]; p2 = Q[j + 1][7 * i:7 * i + 3]
        v = (p2 - p1) / (T[j + 1] - T[j])
        R1 = R(Q[j][7 * i + 3:7 * i + 7]); R2 = R(Q[j + 1][7 * i + 3:7 * i + 7])
        W = (R2 @ R1.T - R1 @ R2.T) / 2 / (T[j + 1] - T[j]); w = np.array([W[2, 1], W[0, 2], W[1, 0]])
        D = DOM[i]; m = M[i]
        Ib = m / 12 * np.array([D["w"] ** 2 + D["h"] ** 2, D["d"] ** 2 + D["h"] ** 2, D["d"] ** 2 + D["w"] ** 2])
        wl = R1.T @ w
        e += 0.5 * m * v @ v + 0.5 * (Ib * wl * wl).sum() + m * G * p1[2]
    E.append(e)
E = np.array(E); rise = np.maximum.accumulate(E[::-1])[::-1]
dE = np.diff(E)
out["energy"] = dict(E0_MJ=float(E[0] / 1e6), Eend_MJ=float(E[-1] / 1e6),
                     max_rise_between_samples_kJ=float(max(0.0, dE.max()) / 1e3),
                     max_rise_frac_of_E0=float(max(0.0, dE.max()) / max(E[0] - E.min(), 1)))
# jitter: rms angular speed of each domino over the last 0.5 s
jj = len(T) - 500
jit = []
for i in range(N):
    a = [math.degrees(math.acos(max(-1, min(1, R(Q[j][7 * i + 3:7 * i + 7])[2, 2])))) for j in range(jj, len(T), 10)]
    jit.append(float(np.std(np.diff(a)) * 100))  # deg/s
out["jitter_deg_s_max"] = max(jit)
json.dump(out, open(P + "_bounce_metrics.json", "w"), indent=1)
print("LANDINGS (far end):")
for r in out["landing"]:
    print(f"  d{r['domino']:2d} h={r['h']:7.3f} m  lift {r['lift_cm']:8.3f} cm ({100*r['lift_frac']:.2f} % h)  bounces {r['bounces']}  settle {r['settle_s']:.2f} s")
print("DOMINO ON DOMINO (largest 6):")
for r in out["dd"][-6:]:
    print(f"  {r['pair']:8s} gap {r['gap_cm']:7.3f} cm ({100*r['gap_frac']:.2f} % h)  separations {r['recontacts']}")
print("ENERGY after giant landing (last 3 dominoes):", {k: round(v, 4) for k, v in out["energy"].items()})
print("max residual jitter (last 0.5 s): %.3f deg/s" % out["jitter_deg_s_max"])
