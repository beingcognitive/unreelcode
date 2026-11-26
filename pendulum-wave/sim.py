"""20 pendulums, 1 push: the simulation (released like a real demo).

One flat board pushes every bob to the SAME horizontal offset X0 from the centre line, so seen from above they start
in one straight line. Each pendulum therefore has its own amplitude, theta0_k = asin(X0 / L_k).

Pendulum k (k = 0..19) must complete N0 + k full swings in GAMMA. Its period depends on its own amplitude (complete
elliptic integral) and on the bob being a solid sphere (a physical pendulum), and the amplitude depends on the length,
so each length is solved by fixed-point iteration. After the release every pendulum is the full nonlinear equation
    theta'' = -g L / (L^2 + 2/5 r^2) sin(theta)
integrated with classical RK4 at DT. Nothing after the release is timed by hand.

Writes cache/sim.npz (theta at every film frame, turning points, centre-line crossings) and out/sim.json.
  Run: python sim.py
"""
import json, math, os
import numpy as np

g = 9.81
GAMMA = 60.0           # s, one full cycle of the pattern
N0 = 40                # swings of the longest pendulum per cycle
NP = 20                # pendulums
X0 = 0.120             # m, the board's push: every bob's centre starts this far from the centre line
R_BOB = 0.019          # bob radius, m: a solid sphere, not a point
DT = 1.0 / (30 * 400)  # s (exactly 400 steps per film frame)
FPS = 30
T_END = GAMMA + 6.0    # simulate past the realignment for the film's tail


def ellipk(m):
    a, b = 1.0, math.sqrt(1.0 - m)
    for _ in range(40):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


NSW = N0 + np.arange(NP)                       # swings per cycle
PER = GAMMA / NSW                              # wanted period


def solve_length(T, x0=X0, r=R_BOB):
    """pivot-to-centre length L whose period at amplitude asin(x0/L), for a solid sphere, is exactly T"""
    L = g * (T / (2 * math.pi)) ** 2
    for _ in range(200):
        th = math.asin(x0 / L)
        Leq = g * (T / (4 * ellipk(math.sin(th / 2) ** 2))) ** 2
        Ln = (Leq + math.sqrt(Leq ** 2 - 1.6 * r ** 2)) / 2
        if abs(Ln - L) < 1e-15: break
        L = Ln
    return Ln


L = np.array([solve_length(T) for T in PER])
TH0 = np.arcsin(X0 / L)                        # each pendulum's own release angle
L_SMALL = g * (PER / (2 * math.pi)) ** 2       # what the small-angle point-mass formula would give


def run(lengths, t_end, th0, dt=DT, fps=FPS):
    w2 = g * lengths / (lengths ** 2 + 0.4 * R_BOB ** 2)
    th = np.array(th0, float).copy(); om = np.zeros(len(lengths))
    f = lambda th, om: (om, -w2 * np.sin(th))
    nsteps = int(round(t_end / dt)); per_frame = int(round(1 / (fps * dt)))
    frames = [th.copy()]; frames_om = [om.copy()]
    peaks = [[] for _ in lengths]; peak_th = [[] for _ in lengths]
    xings = [[] for _ in lengths]              # centre-line crossings: (time, direction +1 toward +y / -1)
    for n in range(1, nsteps + 1):
        k1 = f(th, om); k2 = f(th + dt / 2 * k1[0], om + dt / 2 * k1[1])
        k3 = f(th + dt / 2 * k2[0], om + dt / 2 * k2[1]); k4 = f(th + dt * k3[0], om + dt * k3[1])
        th_n = th + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        om_n = om + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        cross = (om > 0) & (om_n <= 0)
        for i in np.nonzero(cross)[0]:
            s = om[i] / (om[i] - om_n[i])
            peaks[i].append((n - 1 + s) * dt); peak_th[i].append(th[i] + s * (th_n[i] - th[i]))
        cz = np.signbit(th) != np.signbit(th_n)
        for i in np.nonzero(cz)[0]:
            s = th[i] / (th[i] - th_n[i])
            xings[i].append(((n - 1 + s) * dt, 1 if om_n[i] > 0 else -1))
        th, om = th_n, om_n
        if n % per_frame == 0:
            frames.append(th.copy()); frames_om.append(om.copy())
    return np.array(frames), np.array(frames_om), peaks, peak_th, xings


def realign(peaks, nsw):
    """time of the (nsw)-th right-hand turning point after release (the release itself is turning point 0)"""
    return np.array([p[n - 1] for p, n in zip(peaks, nsw)])


if __name__ == "__main__":
    fr, fom, peaks, pth, xings = run(L, T_END, TH0)
    tg = realign(peaks, NSW)
    fG = int(round(GAMMA * FPS)); thG = fr[fG]
    yG = L * np.sin(thG)                                   # offset from the centre line seen from above
    w2 = g * L / (L ** 2 + 0.4 * R_BOB ** 2)
    E0 = -np.cos(TH0); E1 = 0.5 * fom[-1] ** 2 / w2 - np.cos(fr[-1])
    amp = np.array([max(p) for p in pth])
    # naive comparison: small-angle point-mass lengths, released to the same offset
    th0_s = np.arcsin(X0 / L_SMALL)
    fr_s, _, peaks_s, _, _ = run(L_SMALL, GAMMA + 2.0, th0_s)
    tg_s = realign(peaks_s, NSW); yG_s = L_SMALL * np.sin(fr_s[fG])
    out = dict(
        g=g, gamma_s=GAMMA, n0=N0, n=NP, x0_m=X0, dt_s=DT, r_bob_m=R_BOB,
        theta0_deg=[round(float(math.degrees(v)), 4) for v in TH0],
        lengths_m=[round(float(v), 6) for v in L], lengths_small_angle_m=[round(float(v), 5) for v in L_SMALL],
        swings=NSW.tolist(), periods_s=[round(float(v), 6) for v in PER],
        realign_times_s=[round(float(v), 6) for v in tg], realign_spread_ms=float((tg.max() - tg.min()) * 1000),
        realign_mean_error_ms=float((tg.mean() - GAMMA) * 1000),
        offset_at_gamma_mm=[round(float(v) * 1000, 6) for v in yG],
        line_error_at_gamma_mm=float(np.abs(yG - X0).max() * 1000),
        theta_at_gamma_max_dev_deg=float(np.abs(np.degrees(thG - TH0)).max()),
        amplitude_drift_max_deg=float(np.abs(np.degrees(amp - TH0)).max()),
        energy_drift_rel_max=float(np.abs((E1 - E0) / (1 - np.cos(TH0))).max()),
        naive_realign_times_range_s=[float(tg_s.min()), float(tg_s.max())],
        naive_realign_spread_ms=float((tg_s.max() - tg_s.min()) * 1000),
        naive_offset_at_gamma_range_mm=[float(yG_s.min() * 1000), float(yG_s.max() * 1000)],
        bob_speed_max_mps=float(np.max(np.abs(fom) * L)),
    )
    chapters = {}
    for n_, j_ in ((5, 1), (4, 1), (3, 1), (2, 1), (3, 2), (4, 3), (5, 4), (1, 1)):
        tc = GAMMA * j_ / n_; fi = int(round(tc * FPS)); y_ = L * np.sin(fr[fi]) * 1000
        spread = max(float(np.ptp(y_[q::n_])) for q in range(n_))
        chapters[f"{tc:.1f}"] = dict(n=n_, frame_exact=abs(fi / FPS - tc) < 1e-9, max_group_spread_mm=round(spread, 3),
                                     group_offsets_mm=[round(float(np.mean(y_[q::n_])), 1) for q in range(n_)])
    out["chapters"] = chapters
    os.makedirs("cache", exist_ok=True); os.makedirs("out", exist_ok=True)
    np.savez("cache/sim.npz", theta=fr, omega=fom, L=L, fps=FPS, gamma=GAMMA, th0=TH0, x0=X0,
             peaks=np.array([np.array(p) for p in peaks], dtype=object),
             xings=np.array([np.array(x) for x in xings], dtype=object), allow_pickle=True)
    pre = [max(t for t, _ in x if t < GAMMA) for x in xings]; post = [min(t for t, _ in x if t > GAMMA) for x in xings]
    out.update(xing_sweep_before_gamma_s=[round(min(pre), 4), round(max(pre), 4)],
               xing_sweep_after_gamma_s=[round(min(post), 4), round(max(post), 4)],
               xing_first_sweep_s=[round(min(x[0][0] for x in xings), 4), round(max(x[0][0] for x in xings), 4)],
               n_xings_to_gamma=int(sum(1 for x in xings for t, _ in x if t <= GAMMA)))
    json.dump(out, open("out/sim.json", "w"), indent=1)
    for k in ("realign_spread_ms", "realign_mean_error_ms", "line_error_at_gamma_mm", "theta_at_gamma_max_dev_deg",
              "amplitude_drift_max_deg", "energy_drift_rel_max", "naive_realign_times_range_s", "naive_realign_spread_ms",
              "naive_offset_at_gamma_range_mm", "bob_speed_max_mps", "xing_first_sweep_s", "xing_sweep_before_gamma_s"):
        print(k, out[k])
    print("L", out["lengths_m"][0], out["lengths_m"][-1], "theta0", out["theta0_deg"][0], out["theta0_deg"][-1])
    for k, v in chapters.items(): print(k, v)
