"""Per-pair damping ratios from the speed law e(v) = e0 (v/v0)^(-1/4) above the anchor speed (e0 below it), using
the impact speeds measured in a previous run of the chain; pairs that did not exist there are extrapolated as
sqrt(h) from the largest measured one (impact speeds scale as sqrt(g h) in this geometrically similar chain).
usage: python render/speed_zeta.py MEASURED_CHAIN NDOM OUT.json"""
import json, math, sys
import numpy as np
src, ndom, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
J = json.load(open(src + ".json")); Z = np.load(src + ".npz"); T, Q = Z["t"], Z["qpos"]
scan = json.load(open("out/restitution_scan.json")); zs = np.array(scan["zetas"]); es = np.array(scan["e"]["floor_0.5"])
o = np.argsort(es)
zeta_for = lambda e: float(np.interp(e, es[o], zs[o]))
E0_DD, V0_DD = 0.45, math.sqrt(2 * 9.81 * 0.0906)
E0_FL, V0_FL = 0.35, 7.7 * math.sin(math.radians(57.5))
law = lambda e0, v0, v: e0 if (v is None or v <= v0) else e0 * (v / v0) ** -0.25
hs = [0.005 * 1.5 ** i for i in range(ndom)]
first = {}
for e in J["events"]:
    k = tuple(sorted((e["a"], e["b"])))
    first.setdefault(k, e)
n_src = len(J["dom"])
vdd = []
for i in range(ndom - 1):
    k = tuple(sorted((f"d{i+1}", f"d{i+2}")))
    if i < n_src - 1 and k in first:
        vdd.append(first[k]["vn"])
    else:
        vdd.append(vdd[-1] * math.sqrt(hs[i] / hs[i - 1]))
def R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
# floor landings: the far end's downward speed at the first floor impact, for dominoes that land flat on the floor
vfl = [None] * ndom
for i, D in enumerate(J["dom"]):
    t85 = J["t_85"][i]
    if t85 is None or i >= ndom: continue
    j = np.searchsorted(T, t85)
    zz = [(Q[k][7*i:7*i+3] + R(Q[k][7*i+3:7*i+7]) @ np.array([0, 0, D["h"] / 2]))[2] for k in range(j - 20, min(j + 60, len(T)))]
    vfl[i] = float(-(np.diff(zz) * 1000.0).min())
if ndom > n_src or vfl[ndom - 1] is None:
    # the new last domino lands freely: scale the previous last domino's landing speed by sqrt(h)
    vfl[ndom - 1] = vfl[n_src - 1] * math.sqrt(hs[ndom - 1] / hs[n_src - 1])
    if n_src - 1 != ndom - 1:
        vfl[n_src - 1] = None        # no longer the last one: it comes to rest on its successor, not on the floor
edd = [law(E0_DD, V0_DD, v) for v in vdd]; efl = [law(E0_FL, V0_FL, v) for v in vfl]
z = dict(dd=[zeta_for(e) for e in edd], fl=[zeta_for(e) for e in efl])
json.dump(z, open(out, "w"))
json.dump(dict(src=src, vdd=vdd, vfl=vfl, edd=edd, efl=efl, zeta=z), open(out.replace(".json", "_law.json"), "w"), indent=1)
print("dd e:", [round(x, 3) for x in edd]); print("floor e:", [round(x, 3) for x in efl])
print("v d(n-1)->dn %.2f m/s, last landing %.1f m/s" % (vdd[-1], vfl[-1]))
