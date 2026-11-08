"""Measure the effective coefficient of restitution of MuJoCo's soft contact, as used in the film (time constant
0.0025 sqrt(h/g), impedance width 0.000125 h, solimp 0.99/0.999), as a function of the damping ratio zeta, at three
scales. Two drop tests per point: a flat domino falling face-down onto the floor, and onto a fixed second domino.
Impact speed sqrt(g h) (scale-consistent). e = (max upward speed after first contact) / (impact speed)."""
import json, math, sys, os
import numpy as np
import mujoco
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim

G = 9.81


def drop(h, zeta, onto="floor"):
    d, w = 0.15 * h, 0.5 * h
    tc = sim.K_T * math.sqrt(h / G); wd = sim.K_W * h
    dt = tc / 8
    v_in = math.sqrt(G * h)
    gap = 0.02 * h                                       # start just above the contact, with the impact speed
    base = 0.0 if onto == "floor" else d
    z0 = base + d / 2 + gap
    lower = (f'<geom name="low" type="box" size="{w/2} {h/2} {d/2}" pos="0 0 {d/2}" contype="0" conaffinity="0"/>'
             if onto == "box" else "")
    pair_with = "low" if onto == "box" else "floor"
    xml = f"""<mujoco><option timestep="{dt:.6g}" gravity="0 0 -{G}" cone="elliptic" integrator="implicitfast"/>
      <worldbody><geom name="floor" type="plane" size="{50*h} {50*h} 1" contype="0" conaffinity="0"/>{lower}
        <body name="b" pos="0 0 {z0}"><freejoint/>
          <geom name="g" type="box" size="{w/2} {h/2} {d/2}" density="650" contype="0" conaffinity="0"/></body>
      </worldbody>
      <contact><pair geom1="{pair_with}" geom2="g" condim="3" friction="0.3 0.3 0.005 0.0001 0.0001"
        solref="{tc:.6g} {zeta:.6g}" solimp="{sim.IMP[0]} {sim.IMP[1]} {wd:.6g} 0.5 2"/></contact></mujoco>"""
    m = mujoco.MjModel.from_xml_string(xml); dd = mujoco.MjData(m)
    v0 = math.sqrt(max(v_in ** 2 - 2 * G * gap, 0.0))
    dd.qvel[2] = -v0
    vin = None; vup = 0.0; contact_seen = False; t_end = None
    for _ in range(int(40 * tc / dt) + int(2 * gap / v0 / dt) + 1000):
        mujoco.mj_step(m, dd)
        vz = dd.qvel[2]
        if dd.ncon > 0 and not contact_seen:
            contact_seen = True; vin = -vz
        if contact_seen:
            vup = max(vup, vz)
            if dd.ncon == 0 and vz > 0:
                break
    pen = None
    return vup / v_in, v_in


if __name__ == "__main__":
    zetas = [1.0, 0.7, 0.5, 0.4, 0.33, 0.3, 0.27, 0.24, 0.21, 0.18, 0.15]
    out = {}
    for onto in ("floor", "box"):
        for h in (0.005, 0.5, 10.0):
            es = [drop(h, z, onto)[0] for z in zetas]
            out[f"{onto}_{h}"] = es
            print(f"{onto:5s} h={h:6.3f} m: " + "  ".join(f"z{z:.2f}:{e:.3f}" for z, e in zip(zetas, es)), flush=True)
    an = [math.exp(-math.pi * z / math.sqrt(1 - z * z)) if z < 1 else 0.0 for z in zetas]
    print("ideal spring-damper exp(-pi z / sqrt(1-z^2)): " + "  ".join(f"z{z:.2f}:{e:.3f}" for z, e in zip(zetas, an)))
    json.dump(dict(zetas=zetas, e=out, ideal=an), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out/restitution_scan.json"), "w"), indent=1)
