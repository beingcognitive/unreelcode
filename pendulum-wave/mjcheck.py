"""Independent check in MuJoCo: 20 hinge joints, each carrying a solid steel sphere (inertia from the geom) at the
lengths sim.py chose. No contacts. Reports each pendulum's angle and phase at GAMMA.   python mjcheck.py"""
import json, math
import numpy as np, mujoco
J = json.load(open("out/sim.json"))
L, r, G = J["lengths_m"], J["r_bob_m"], J["gamma_s"]
th0 = np.arcsin(J["x0_m"] / np.array(L))      # same offset for all: each its own angle
bodies = "".join(f'<body pos="{0.040*k} 0 0.7"><joint name="j{k}" type="hinge" axis="1 0 0"/>'
                 f'<geom type="sphere" size="{r}" pos="0 0 {-l}" density="7850"/></body>' for k, l in enumerate(L))
xml = f'''<mujoco><option timestep="{1/12000}" integrator="RK4" gravity="0 0 -{J["g"]}"><flag contact="disable"/></option>
<worldbody>{bodies}</worldbody></mujoco>'''
m = mujoco.MjModel.from_xml_string(xml); d = mujoco.MjData(m)
d.qpos[:] = th0; mujoco.mj_forward(m, d)
n = int(round(G / m.opt.timestep)); prev = d.qvel.copy(); last_peak = np.zeros(len(L))
for i in range(n + 600):
    mujoco.mj_step(m, d)
    cross = (prev > 0) & (d.qvel <= 0)
    for k in np.nonzero(cross)[0]:
        s = prev[k] / (prev[k] - d.qvel[k]); tpk = (i + s) * m.opt.timestep
        if abs(tpk - G) < 0.2: last_peak[k] = tpk
    prev = d.qvel.copy()
    if i + 1 == n: thG = d.qpos.copy()
yG = np.array(L) * np.sin(thG)
out = dict(mujoco=mujoco.__version__, theta_at_gamma_max_dev_deg=float(np.degrees(np.abs(thG - th0)).max()),
           line_error_at_gamma_mm=float(np.abs(yG - J["x0_m"]).max() * 1000),
           peak_times_near_gamma_s=[round(float(v), 6) for v in last_peak],
           peak_spread_ms=float((last_peak.max() - last_peak.min()) * 1000), peak_mean_error_ms=float((last_peak.mean() - G) * 1000))
json.dump(out, open("out/mjcheck.json", "w"), indent=1); print({k: v for k, v in out.items() if k != "peak_times_near_gamma_s"})
