"""Domino amplification chain, simulated in MuJoCo (rigid bodies, real gravity, Coulomb friction).

One simulation holds every domino at its true size (metres, kg, seconds). Only the *contact softness*
is scaled per contact pair: MuJoCo's soft-contact time constant (solref) and impedance width (solimp)
are absolute quantities, so a fixed value would make a 5 mm domino mushy and a 10 m one rigid. We set
both proportional to each pair's own scale (time ~ sqrt(h/g), length ~ h), which makes every contact
equally "hard" relative to its own domino. Everything else (gravity, friction, mass, inertia) is real.

Usage:
  python sim.py run   --r 1.5 --n 17 --s 0.35        # one chain, writes out/chain.npz + prints log
  python sim.py scan                                  # max-ratio scan (writes out/scan.json)
  python sim.py scale                                 # single-domino fall time vs size (sqrt(L/g) check)
"""
import argparse, json, math, sys, time
import numpy as np
import mujoco

G = 9.81
import os
K_T = float(os.environ.get("K_T", "0.0025"))     # contact time constant / sqrt(h/g)
K_W = float(os.environ.get("K_W", "0.000125"))    # impedance width / h
IMP = tuple(float(v) for v in os.environ.get("IMP", "0.99,0.999").split(","))
ZETA_DD = float(os.environ.get("ZETA_DD", "1.0"))        # contact damping ratio, domino-domino (1 = critically damped)
ZETA_FL = float(os.environ.get("ZETA_FL", "1.0"))        # contact damping ratio, domino-floor
# optional per-pair damping ratios (speed-dependent restitution): JSON {"dd": [z_0..z_n-2], "fl": [z_0..z_n-1]}
ZETA_FILE = os.environ.get("ZETA_FILE")
_ZP = None
if ZETA_FILE:
    import json as _json
    _ZP = _json.load(open(ZETA_FILE))
RHO = 650.0           # kg/m^3, wood-like (mass drops out of the toppling physics; kept real anyway)


def chain_geometry(n, r, h0, s, d_ratio=0.15, w_ratio=0.5, jitter=None):
    """h_i = h0 r^i; thickness d = d_ratio h; width w = w_ratio h; gap from domino i's front face
    to domino i+1's back face = s * h_i (scaled with the *hitting* domino)."""
    dom = []
    x = 0.0
    rng = np.random.default_rng(jitter[0]) if jitter else None
    for i in range(n):
        h = h0 * r**i
        d, w = d_ratio * h, w_ratio * h
        if i > 0:
            gap = s * dom[-1]["h"]
            if rng is not None:
                gap *= 1 + jitter[1] * rng.uniform(-1, 1)
            x = dom[-1]["x"] + dom[-1]["d"] / 2 + gap + d / 2
        dom.append(dict(i=i, h=h, d=d, w=w, x=x))
    return dom


def build_xml(dom, mu_floor=0.6, mu_dd=0.3, k_t=None, k_w=None, dt=None, imp=None):
    k_t = K_T if k_t is None else k_t
    k_w = K_W if k_w is None else k_w
    imp = IMP if imp is None else imp
    h0 = dom[0]["h"]
    if dt is None:
        dt = k_t * math.sqrt(h0 / G) / 8          # 8 steps per smallest contact time constant
    bodies, pairs = [], []
    for D in dom:
        i = D["i"]
        bodies.append(
            f'<body name="d{i}" pos="{D["x"]:.9g} 0 {D["h"]/2:.9g}"><freejoint/>'
            f'<geom name="g{i}" type="box" size="{D["d"]/2:.9g} {D["w"]/2:.9g} {D["h"]/2:.9g}" '
            f'density="{RHO}" contype="0" conaffinity="0" rgba="0.93 0.91 0.86 1"/></body>')

    def pair(a, b, h, mu, zeta):
        tc = k_t * math.sqrt(h / G)
        wd = k_w * h
        return (f'<pair geom1="{a}" geom2="{b}" condim="3" friction="{mu} {mu} 0.005 0.0001 0.0001" '
                f'solref="{tc:.6g} {zeta:.6g}" solimp="{imp[0]} {imp[1]} {wd:.6g} 0.5 2"/>')

    for D in dom:
        i = D["i"]
        zf = _ZP["fl"][i] if _ZP else ZETA_FL
        pairs.append(pair("floor", f"g{i}", D["h"], mu_floor, zf))
        for j in (i + 1, i + 2):
            if j < len(dom):
                zd = _ZP["dd"][min(i, len(_ZP["dd"]) - 1)] if _ZP else ZETA_DD
                pairs.append(pair(f"g{i}", f"g{j}", D["h"], mu_dd, zd))
    ext = dom[-1]["x"] + dom[-1]["h"]
    return f"""<mujoco model="dominoes">
  <option timestep="{dt:.6g}" gravity="0 0 -{G}" cone="elliptic" impratio="1" integrator="implicitfast"/>
  <visual><global offwidth="1080" offheight="1920"/><quality shadowsize="8192"/>
    <map znear="0.0001" zfar="200"/></visual>
  <asset><texture name="grid" type="2d" builtin="checker" rgb1=".24 .25 .27" rgb2=".20 .21 .23" width="512" height="512"/>
    <material name="grid" texture="grid" texrepeat="1 1" texuniform="true" reflectance="0.05"/></asset>
  <worldbody>
    <light name="sun" directional="true" pos="0 0 1" dir="-0.4 0.5 -1" castshadow="true"/>
    <geom name="floor" type="plane" size="{ext*3:.6g} {ext*3:.6g} 0.1" material="grid" contype="0" conaffinity="0"/>
    {''.join(bodies)}
  </worldbody>
  <contact>{''.join(pairs)}</contact>
</mujoco>"""


def tilt(d, m, i):
    """tilt angle (deg) of domino i from vertical: angle between body z axis and world z."""
    R = d.xmat[m.body(f"d{i}").id].reshape(3, 3)
    return math.degrees(math.acos(max(-1, min(1, R[2, 2]))))


def simulate(dom, push=1.3, t_max=None, record_fps=0, **kw):
    """push: initial kinetic energy of domino 0 as a multiple of its tipping barrier
    (the smallest push that topples it is push > 1)."""
    xml = build_xml(dom, **kw)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    n = len(dom)
    D0 = dom[0]
    # barrier: raise COM from h/2 to half-diagonal
    hd = 0.5 * math.hypot(D0["h"], D0["d"])
    I_edge = (D0["h"]**2 + D0["d"]**2) / 3.0           # per unit mass, about the bottom edge
    w0 = math.sqrt(2 * push * G * (hd - D0["h"] / 2) / I_edge)
    # rigid rotation about the front-bottom edge (y axis): omega_y = +w0 tips toward +x
    adr = m.jnt_dofadr[m.body("d0").jntadr[0]]
    d.qvel[adr + 4] = w0
    # velocity of COM = omega x r, r from pivot (front-bottom edge) to COM = (-d/2, 0, h/2)
    d.qvel[adr + 0] = w0 * (D0["h"] / 2)
    d.qvel[adr + 2] = w0 * (D0["d"] / 2)
    if t_max is None:
        t_max = 6 * sum(math.sqrt(D["h"] / G) for D in dom) + 2 * math.sqrt(dom[-1]["h"] / G)
    t_start = [None] * n; t_flat = [None] * n
    t_start[0] = 0.0
    frames = []; next_rec = 0.0
    bid = [m.body(f"d{i}").id for i in range(n)]
    base0 = np.array([d.xpos[b][0] for b in bid])
    max_slip = np.zeros(n)
    while d.time < t_max:
        mujoco.mj_step(m, d)
        for i in range(n):
            R22 = d.xmat[bid[i]][8]
            a = math.degrees(math.acos(max(-1, min(1, R22))))
            if t_start[i] is None and a > 0.5:
                t_start[i] = d.time
            if t_flat[i] is None and a > 60:
                t_flat[i] = d.time
        if record_fps and d.time >= next_rec:
            frames.append((d.time, d.qpos.copy()))
            next_rec += 1.0 / record_fps
        if t_flat[-1] is not None and record_fps == 0:
            break
        if t_flat[-1] is not None and d.time > t_flat[-1] + 1.5 * math.sqrt(dom[-1]["h"] / G) + 0.5:
            break
    # slip: horizontal motion of each domino's front-bottom edge is hard to define after falling;
    # report how far the *rear* bottom edge (pivot side for a forward fall: front edge) moved, as a fraction of h
    for i in range(n):
        R = d.xmat[bid[i]].reshape(3, 3)
        # front-bottom edge midpoint in body frame: (+d/2, 0, -h/2)
        p = d.xpos[bid[i]] + R @ np.array([dom[i]["d"] / 2, 0, -dom[i]["h"] / 2])
        front0 = dom[i]["x"] + dom[i]["d"] / 2
        max_slip[i] = (p[0] - front0) / dom[i]["h"]
    final_tilt = [tilt(d, m, i) for i in range(n)]
    return dict(m=m, frames=frames, t_start=t_start, t_flat=t_flat, final_tilt=final_tilt,
                slip=max_slip.tolist(), dt=m.opt.timestep, steps=int(d.time / m.opt.timestep), t_end=d.time,
                push_w0=w0)


def all_fell(res):
    return all(t is not None for t in res["t_start"]) and res["t_flat"][-1] is not None


def cmd_run(a):
    dom = chain_geometry(a.n, a.r, a.h0, a.s)
    t0 = time.time()
    res = simulate(dom, push=a.push, record_fps=a.fps, k_t=a.kt, mu_floor=a.mufloor, mu_dd=a.mudd)
    wall = time.time() - t0
    print(f"r={a.r} n={a.n} s={a.s} h0={a.h0*1000:.1f} mm -> last h={dom[-1]['h']:.3f} m; dt={res['dt']*1e6:.1f} us,"
          f" {res['steps']} steps, {wall:.1f} s wall; all fell: {all_fell(res)}")
    print(" i     h(m)       starts(s)   >60deg(s)  final tilt  front-edge slip/h")
    for i, D in enumerate(dom):
        ts, tf = res["t_start"][i], res["t_flat"][i]
        print(f"{i:2d} {D['h']:9.4f}  {ts if ts is None else f'{ts:9.4f}'}  {tf if tf is None else f'{tf:9.4f}'}"
              f"  {res['final_tilt'][i]:7.1f}  {res['slip'][i]:+.4f}")
    out = dict(r=a.r, n=a.n, s=a.s, h0=a.h0, push=a.push, kt=a.kt, dom=dom, dt=res["dt"],
               t_start=res["t_start"], t_flat=res["t_flat"], final_tilt=res["final_tilt"], slip=res["slip"],
               all_fell=all_fell(res), wall_s=wall)
    with open(a.out + ".json", "w") as f:
        json.dump(out, f, indent=1)
    if res["frames"]:
        np.savez_compressed(a.out + ".npz", t=np.array([f[0] for f in res["frames"]]),
                            qpos=np.array([f[1] for f in res["frames"]]))
        with open(a.out + ".xml", "w") as f:
            f.write(build_xml(dom, k_t=a.kt, mu_floor=a.mufloor, mu_dd=a.mudd))


def _scan_one(args):
    s, r, n, trials, push, mufloor, mudd, kt = args
    for trial in range(trials):
        mu_f = mufloor * (1.0, 2.0 / 3.0)[trial % 2]
        dom = chain_geometry(n, r, 0.005, s, jitter=(trial, 0.05) if trial else None)
        res = simulate(dom, push=push, mu_floor=mu_f, mu_dd=mudd, k_t=kt)
        if not all_fell(res):
            first_fail = next((i for i, t in enumerate(res["t_flat"]) if t is None), None)
            return s, r, False, trial, first_fail
    return s, r, True, None, None


def cmd_scan(a):
    """Grid over spacing s and ratio r. 'Reliable' = every trial topples the whole chain:
    trial 0 exact geometry, floor mu 0.6; trial 1 gaps jittered +-5 %, floor mu 0.4; trial 2 jitter, mu 0.6; ..."""
    from multiprocessing import Pool
    rs = [round(float(x), 3) for x in np.arange(1.4, 2.61, 0.05)]
    jobs = [(s, r, a.n, a.trials, a.push, a.mufloor, a.mudd, a.kt) for s in a.svals for r in rs]
    with Pool(a.procs) as pool:
        out = pool.map(_scan_one, jobs, chunksize=1)
    results = []
    for s in a.svals:
        rows = sorted([o for o in out if o[0] == s], key=lambda o: o[1])
        ok = [o[1] for o in rows if o[2]]
        # largest r such that it and every smaller r in the grid succeeded
        maxc = None
        for o in rows:
            if o[2]: maxc = o[1]
            else: break
        results.append(dict(s=s, ok=ok, fail=[[o[1], o[3], o[4]] for o in rows if not o[2]], max_contiguous_ok=maxc))
        print(f"s/h={s:.2f}: all r from 1.40 to {maxc} topple; ok set {ok}")
    with open(a.out + "_scan.json", "w") as f:
        json.dump(dict(n=a.n, trials=a.trials, h0=0.005, push=a.push, mufloor=a.mufloor, mudd=a.mudd, kt=a.kt, results=results), f, indent=1)


def cmd_scale(a):
    """Single domino, same proportions, same relative push, at sizes 5 mm .. 50 m: time to reach 60 deg."""
    rows = []
    for h in [0.005, 0.05, 0.5, 5.0, 50.0]:
        dom = [dict(i=0, h=h, d=0.15 * h, w=0.5 * h, x=0.0)]
        res = simulate(dom, push=1.3)
        rows.append((h, res["t_flat"][0]))
        print(f"h={h:8.3f} m  t(0->60deg)={res['t_flat'][0]:.5f} s   t/sqrt(h/g)={res['t_flat'][0]/math.sqrt(h/G):.4f}")
    hs, ts = np.log([r[0] for r in rows]), np.log([r[1] for r in rows])
    print("fitted exponent t ~ h^p, p =", np.polyfit(hs, ts, 1)[0])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd")
    p.add_argument("--r", type=float, default=1.5)
    p.add_argument("--n", type=int, default=17)
    p.add_argument("--s", type=float, default=0.35)
    p.add_argument("--h0", type=float, default=0.005)
    p.add_argument("--push", type=float, default=1.3)
    p.add_argument("--kt", type=float, default=None)
    p.add_argument("--fps", type=float, default=0)
    p.add_argument("--out", default="out/chain")
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--mufloor", type=float, default=0.6)
    p.add_argument("--mudd", type=float, default=0.3)
    p.add_argument("--procs", type=int, default=10)
    p.add_argument("--svals", type=float, nargs="+", default=[0.5, 0.6, 0.7, 0.8, 0.9])
    a = p.parse_args()
    {"run": cmd_run, "scan": cmd_scan, "scale": cmd_scale}[a.cmd](a)
