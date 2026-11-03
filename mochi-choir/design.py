"""The Mochi Choir: 25 mochi sit along a rainbow arch, one per pitch of Bach's Prelude in C (bars 1-19). A conductor on
a cloud tosses one candy per note; it lands on that singer's head exactly when the note sounds, bounces off and falls
away. Real gravity at a stated scale (a 5 cm mochi is 60 px, so 1 m = 1200 px).

Physics (lib/phys.py, exact ballistics): each head is a rigid circle (the squish in the film is animation only);
restitution 0.45 (soft). For each note a flight time and a contact angle are searched until the candy
  - first touches its own singer, on time (< 2 ms),
  - touches nothing else before (no other head, never the rainbow), and
  - after the bounce leaves the frame without touching any head or the rainbow.

  python design.py   -> cache/choir.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "lib"))
import phys   # noqa: E402
import score  # noqa: E402

PX_PER_M = 1200.0
phys.set_scale(PX_PER_M)
phys.E = 0.45
T0, BAR = 0.75, 2.7
R_CANDY = 15.0
ARC_C, ARC_A, ARC_B = np.array([540.0, 1500.0]), 455.0, 560.0      # rainbow: outer edge ellipse
TH0, TH1 = 166.0, 14.0
SOURCE = np.array([540.0, 520.0])                                   # the conductor's hand


def singers():
    P = score.pitches()
    n = len(P)
    out = []
    for k, p in enumerate(P):
        th = math.radians(TH0 + (TH1 - TH0) * k / (n - 1))
        seat = ARC_C + np.array([ARC_A * math.cos(th), -ARC_B * math.sin(th)])
        ry = 42.0 - 15.0 * k / (n - 1)                                  # low notes are big
        if k == 0:
            ry = 50.0                                                     # grandpa (G2)
        rx = 1.08 * ry
        head = seat + np.array([0.0, -ry])
        out.append(dict(pitch=p, seat=seat, rx=rx, ry=ry, head=head, rad=ry, th=th))
    return out


def in_rainbow(P, pad):
    """inside the rainbow's outer ellipse (grown by pad), above its feet"""
    q = (P - ARC_C) / np.array([ARC_A + pad, ARC_B + pad])
    return ((q ** 2).sum(-1) < 1) & (P[..., 1] < ARC_C[1] + 200)


def fly_clear(p0, v, t_max, heads, rads, skip):
    """first head contact in (0, t_max] and whether the rainbow is touched before it"""
    th, j = phys.first_hit(p0, v, heads, heads, rads, t_max, skip=skip)
    tt = np.arange(0.0, (th if th is not None else t_max), 0.001)
    bad_rb = bool(in_rainbow(phys.pos(p0, v, tt), R_CANDY - 2).any()) if len(tt) else False
    return th, j, bad_rb


def main():
    S = singers()
    heads = np.array([s["head"] for s in S])
    rads = np.array([s["rad"] + R_CANDY for s in S])
    idx = {s["pitch"]: i for i, s in enumerate(S)}
    out, fails = [], 0
    for (t, p, bar) in score.notes(T0, BAR):
        j = idx[p]
        s = S[j]
        side = np.sign(s["head"][0] - 540.0) or 1.0
        best = None
        for FL in (0.62, 0.56, 0.68, 0.5, 0.74, 0.44, 0.8, 0.9, 1.0):
            for tilt in (0.35, 0.5, 0.2, 0.65, 0.05, 0.8, 1.0, 1.3, 1.7, 2.3):
                n = np.array([side * tilt, -1.0]); n /= np.linalg.norm(n)
                target = s["head"] + n * (s["rad"] + R_CANDY)
                v0 = (target - SOURCE - 0.5 * phys.G * FL ** 2) / FL
                th, hj, bad = fly_clear(SOURCE, v0, FL + 0.03, heads, rads, [])
                if bad or hj != j or abs(th - FL) > 0.002:
                    continue
                ph = phys.pos(SOURCE, v0, th)
                vin = phys.vel(v0, th)
                nrm = (ph - s["head"]) / np.linalg.norm(ph - s["head"])
                vout = phys.reflect(vin, nrm)
                # after the bounce: leave the frame without touching a head or the rainbow
                tt = np.arange(0.0, 3.0, 0.001)
                path = phys.pos(ph, vout, tt)
                gone = np.where((path[:, 1] > 2000) | (path[:, 0] < -40) | (path[:, 0] > 1120))[0]
                if not len(gone):
                    continue
                t_out = tt[gone[0]]
                th2, hj2, bad2 = fly_clear(ph, vout, t_out, heads, rads, [j])
                if hj2 is not None or bad2:
                    continue
                best = dict(t_note=t, pitch=p, singer=j, bar=bar, flight=FL, tilt=tilt, t_launch=t - FL,
                            v0=v0.tolist(), t_hit=t - FL + th, p_hit=ph.tolist(), v_in=vin.tolist(),
                            v_out=vout.tolist(), t_exit=t - FL + th + t_out, impact=float(-np.dot(vin, nrm)),
                            err_ms=1000 * (th - FL))
                break
            if best:
                break
        if best is None:
            fails += 1
            print("no clean toss for note", t, p)
            continue
        out.append(best)
    errs = np.array([b["err_ms"] for b in out])
    print(f"{len(out)} candies, {fails} unsolved; hit-time error max {np.abs(errs).max():.4f} ms; "
          f"in flight at once: max {max(sum(1 for c in out if c['t_launch'] <= t <= c['t_exit']) for t in np.arange(0, 60, 0.02))}")
    json.dump(dict(singers=[dict(pitch=s["pitch"], seat=s["seat"].tolist(), rx=s["rx"], ry=s["ry"],
                                 head=s["head"].tolist(), rad=s["rad"], th=s["th"]) for s in S],
                   candies=out, source=SOURCE.tolist(), r_candy=R_CANDY, g=float(phys.G[1]), E=phys.E,
                   arc=[*ARC_C.tolist(), ARC_A, ARC_B], T0=T0, BAR=BAR), open(ROOT / "cache/choir.json", "w"))


if __name__ == "__main__":
    main()
