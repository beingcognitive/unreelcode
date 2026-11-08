"""Check every on-screen number in the notes timeline against the simulation output (independently recomputed)."""
import os, sys, json, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as T
J = json.load(open(T.ROOT + "/" + T.CHAIN + ".json")); Z = np.load(T.ROOT + "/" + T.CHAIN + ".npz")
ok = True
def chk(name, cond, info=""):
    global ok; ok &= bool(cond); print(("OK  " if cond else "FAIL"), name, info)
dom = J["dom"]; N = len(dom); ts = np.array(J["t_start"])
chk("domino count caption", f"{N} dominoes." in sum((c[2] for c in T.CAPTIONS), []), f"N={N}")
ratios = [dom[i+1]["h"] / dom[i]["h"] for i in range(N - 1)]
chk("1.5x ratio", max(abs(r - 1.5) for r in ratios) < 1e-9, f"ratios {min(ratios):.6f}-{max(ratios):.6f}")
# readout: per frame, the highest domino that has started falling, and its height
bad = 0
for f in range(T.N_SIM):
    s = T.sim_time(f)
    k_ind = max(int((ts <= s + 1e-9).sum()) - 1, 0)
    k_ro = int(min(max(math.floor(T.front_u(s) + 1e-6), 0), N - 1))
    if k_ro != k_ind: bad += 1
chk("readout domino index vs sim start times", bad == 0, f"{bad} mismatched frames of {T.N_SIM}")
chk("readout heights from the sim geometry", abs(dom[0]["h"] - 0.005) < 1e-9 and abs(dom[-1]["h"] - 0.005 * 1.5 ** (N - 1)) < 1e-6,
    f"first {dom[0]['h']*1000:.1f} mm, last {dom[-1]['h']:.2f} m")
# speed labels match the playback rate actually used to map frames to sim time
d = np.diff([T.sim_time(f) for f in range(T.N_PRE, T.N_SIM)]) * T.FPS
lab = np.array([T.rate(T.sim_time(f)) for f in range(T.N_PRE, T.N_SIM - 1)])
chk("speed label vs frame-to-sim mapping", np.abs(d - lab).max() < 1e-6 or np.mean(np.abs(d - lab) < 1e-6) > 0.995,
    f"max dev {np.abs(d-lab).max():.3g} (rate switches fall between frames)")
# energy lines, recomputed: released = m g (initial COM height - final COM height) of the last domino
q = Z["qpos"]; m = J["masses"][-1]; iz = 7 * (N - 1) + 2
rel = m * 9.81 * (q[0, iz] - q[-1, iz])
chk("released energy (from the trajectory)", abs(rel - J["released_J"]) / J["released_J"] < 0.02, f"{rel/1e6:.3f} MJ vs logged {J['released_J']/1e6:.3f} MJ")
rice_mm = J["work_J"] / (20e-6 * 9.81) * 1000; car_m = J["released_J"] / (1200 * 9.81)
txt = " ".join(sum((c[2] for c in T.CAPTIONS), []))
chk("rice line", rice_mm < 0.01 and "less than 0.01 mm" in txt, f"{rice_mm*1000:.2f} µm")
chk("car line", f"a car {car_m:.0f} metres." in txt, f"{car_m:.1f} m")
chk("push work > barrier", J["work_J"] > J["barrier_J"], f"{J['work_J']*1e9:.3f} nJ vs {J['barrier_J']*1e9:.3f} nJ")
chk("all fell", J["all_fell"])
print("ALL OK" if ok else "SOME CHECKS FAILED")
