"""The film's chain: sim.py's 20 dominoes (r = 1.5, gap 0.75 h, floor mu 0.8, domino mu 0.3), started by a pencil.

The pencil (called the needle in the code) is a MuJoCo mocap body: kinematic, it moves on a fixed path whatever the
forces, as a motorised stage would. Only its graphite tip is a collision geom: a sphere of radius 0.25 mm at 85 % of
domino 1's height. It moves +x at 3 mm/s, touches domino 1, pushes it slowly past its balance point and is stopped
once domino 1 leaves it. The work it does on the domino is measured: the sum of contact force (x) times needle speed
times dt.

Bounce: each contact pair's damping ratio comes from ZETA_FILE (render/speed_zeta.py), see sim.py.

Also logged, for the sound: every new contact between two bodies (domino-domino, domino-floor, needle-domino), with
the relative normal speed at the contact point and the two masses.

Writes out/film_chain.json (log, events), out/film_chain.npz (qpos at 1 kHz), out/film_chain.xml.
"""
import json, math, os, time
import numpy as np
import mujoco
import sim

R, NDOM, S = 1.5, int(os.environ.get('NDOM', '20')), 0.75
MU_F, MU_D = 0.8, 0.3
NEEDLE_V = 0.003            # m/s
NEEDLE_GAP = 0.0012         # m: tip starts this far behind domino 1's back face
NEEDLE_ZF = 0.85            # tip height as a fraction of domino 1's height
TIP_R = float(os.environ.get("TIP_R", "0.00025"))  # m: the pencil's graphite tip, 0.25 mm
REC_HZ = 1000.0


def build():
    dom = sim.chain_geometry(NDOM, R, 0.005, S)
    xml = sim.build_xml(dom, mu_floor=MU_F, mu_dd=MU_D)
    D0 = dom[0]
    x0 = D0["x"] - D0["d"] / 2 - NEEDLE_GAP - TIP_R
    z0 = NEEDLE_ZF * D0["h"]
    body = (f'<body name="needle" mocap="true" pos="{x0:.9g} 0 {z0:.9g}">'
            f'<geom name="tip" type="sphere" size="{TIP_R}" contype="0" conaffinity="0" rgba=".7 .7 .7 1"/></body>')
    tc = sim.K_T * math.sqrt(D0["h"] / sim.G); wd = sim.K_W * D0["h"]
    pair = (f'<pair geom1="tip" geom2="g0" condim="3" friction="0.2 0.2 0.005 0.0001 0.0001" '
            f'solref="{tc:.6g} 1" solimp="{sim.IMP[0]} {sim.IMP[1]} {wd:.6g} 0.5 2"/>')
    xml = xml.replace("  </worldbody>", f"    {body}\n  </worldbody>").replace("<contact>", "<contact>" + pair)
    return dom, xml, np.array([x0, 0, z0])


def main():
    dom, xml, n0 = build()
    m = mujoco.MjModel.from_xml_string(xml); d = mujoco.MjData(m)
    n = len(dom)
    bid = [m.body(f"d{i}").id for i in range(n)]
    gid = {m.geom(f"g{i}").id: i for i in range(n)}
    g_floor, g_tip = m.geom("floor").id, m.geom("tip").id
    mass = [float(m.body_mass[b]) for b in bid]
    dof = [m.jnt_dofadr[m.body(f"d{i}").jntadr[0]] for i in range(n)]
    dt = m.opt.timestep
    needle_x = n0[0]; needle_moving = True; t_stop = None
    work = 0.0
    t_start = [None] * n; t_60 = [None] * n; t_85 = [None] * n
    active = set(); events = []; pen_max = {}
    frames_t, frames_q, frames_n = [], [], []
    next_rec = 0.0
    f6 = np.zeros(6)
    t_max = 40.0

    def point_vel(i, p):
        a = dof[i]
        v = d.qvel[a:a + 3]; w_loc = d.qvel[a + 3:a + 6]
        Rm = d.xmat[bid[i]].reshape(3, 3)
        return v + np.cross(Rm @ w_loc, p - d.xpos[bid[i]])

    t0 = time.time()
    while d.time < t_max:
        # needle path
        if needle_moving:
            needle_x += NEEDLE_V * dt
        d.mocap_pos[0] = [needle_x, 0, n0[2]]
        mujoco.mj_step(m, d)
        # contacts: work by the needle, new-contact events
        cur = set()
        for k in range(d.ncon):
            c = d.contact[k]
            g1, g2 = int(c.geom1), int(c.geom2)
            key = (min(g1, g2), max(g1, g2))
            cur.add(key)
            if g1 in gid or g2 in gid:
                th = min(dom[gid[g]]["d"] for g in (g1, g2) if g in gid)
                pen = -float(c.dist) / th
                if pen > pen_max.get(key, (0, 0))[0]:
                    pen_max[key] = (pen, d.time)
            if g_tip in key:
                mujoco.mj_contactForce(m, d, k, f6)
                fw = c.frame.reshape(3, 3).T @ f6[:3]
                if needle_moving:
                    work += abs(fw[0]) * NEEDLE_V * dt
            if key not in active:
                p = c.pos.copy(); nrm = c.frame[:3].copy()
                def vel(g):
                    if g in gid: return point_vel(gid[g], p)
                    if g == g_tip: return np.array([NEEDLE_V if needle_moving else 0.0, 0, 0])
                    return np.zeros(3)
                vn = abs(float((vel(g1) - vel(g2)) @ nrm))
                names = [("d%d" % (gid[g] + 1)) if g in gid else ("floor" if g == g_floor else "needle") for g in (g1, g2)]
                ms = [mass[gid[g]] if g in gid else math.inf for g in (g1, g2)]
                events.append(dict(t=d.time, a=names[0], b=names[1], vn=vn, ma=ms[0], mb=ms[1], p=p.tolist()))
        active = cur
        for i in range(n):
            a = math.degrees(math.acos(max(-1.0, min(1.0, d.xmat[bid[i]][8]))))
            if t_start[i] is None and a > 0.5: t_start[i] = d.time
            if t_60[i] is None and a > 60: t_60[i] = d.time
            if t_85[i] is None and a > 85: t_85[i] = d.time
        # stop the needle when domino 1 has left it (tilt > 15 deg)
        if needle_moving and t_start[0] is not None:
            a0 = math.degrees(math.acos(max(-1.0, min(1.0, d.xmat[bid[0]][8]))))
            if a0 > 15:
                needle_moving = False; t_stop = d.time
        if d.time >= next_rec:
            frames_t.append(d.time); frames_q.append(d.qpos.copy()); frames_n.append(needle_x)
            next_rec += 1.0 / REC_HZ
        if t_85[-1] is not None and d.time > t_85[-1] + 3.0:
            break
    wall = time.time() - t0
    # domino 1's tipping barrier, for comparison
    D0 = dom[0]; m0 = mass[0]
    barrier = m0 * sim.G * (0.5 * math.hypot(D0["h"], D0["d"]) - D0["h"] / 2)
    last = dom[-1]
    released = mass[-1] * sim.G * (last["h"] - last["d"]) / 2
    ok = all(t is not None for t in t_60)
    print(f"{n} dominoes, all past 60 deg: {ok}; wall {wall:.0f} s, dt {dt*1e6:.1f} us, end t {d.time:.2f} s")
    print(f"needle: first contact ~{(NEEDLE_GAP)/NEEDLE_V:.3f} s, stopped at {t_stop:.4f} s; work {work*1e9:.3f} nJ "
          f"(domino 1 barrier {barrier*1e9:.3f} nJ); last domino releases {released/1e6:.3f} MJ; ratio {released/work:.3g}")
    for i in range(n):
        print(f"{i+1:2d} h={dom[i]['h']:8.4f}  start {t_start[i]:8.4f}  60deg {t_60[i]:8.4f}  85deg {t_85[i] if t_85[i] else float('nan'):8.4f}")
    print("events:", len(events))
    gname = lambda g: ("d%d" % (gid[g] + 1)) if g in gid else ("floor" if g == g_floor else "needle")
    pens = sorted(((v[0], v[1], gname(k[0]), gname(k[1])) for k, v in pen_max.items()), reverse=True)
    print("max penetration / thickness of the thinner body (top 8):")
    for p, t, a, b in pens[:8]:
        print(f"   {a:>6s}-{b:<6s} {100*p:6.3f} %  at t={t:.3f}")
    dd = {f"{a}-{b}": (p, t) for p, t, a, b in pens}
    out = dict(R=R, n=n, s=S, mu_floor=MU_F, mu_dd=MU_D, needle=dict(v=NEEDLE_V, gap=NEEDLE_GAP, zf=NEEDLE_ZF,
               tip_r=TIP_R, x0=float(n0[0]), z=float(n0[2]), t_stop=t_stop), work_J=work, barrier_J=barrier,
               released_J=released, masses=mass, dom=dom, dt=dt, t_start=t_start, t_60=t_60, t_85=t_85,
               all_fell=ok, events=events, t_end=d.time,
               contact=dict(k_t=sim.K_T, k_w=sim.K_W, imp=list(sim.IMP)), penetration=dd)
    json.dump(out, open(os.environ.get("OUT", "out/film_chain") + ".json", "w"), indent=1)
    np.savez_compressed(os.environ.get("OUT", "out/film_chain") + ".npz", t=np.array(frames_t), qpos=np.array(frames_q), needle_x=np.array(frames_n))
    open(os.environ.get("OUT", "out/film_chain") + ".xml", "w").write(xml)


if __name__ == "__main__":
    main()
