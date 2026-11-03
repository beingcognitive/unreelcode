"""preview.py SHOT t1 t2 ... -- simulate a shot and save full-resolution frames at given shot times."""
import sys, time
import numpy as np
from PIL import Image
import shots
from ink import Ink, Look

name = sys.argv[1]
times = [float(x) for x in sys.argv[2:]]
S = shots.SHOTS[name]
f = Ink(*S.get("grid", (960, 402)), consts=S["consts"])
L = Look(f.ctx)
rng = np.random.default_rng(S.get("seed", 1))
S["init"](f, rng)
dt = 1.0 / (shots.FPS * S["substeps"])
t = -S["preroll"]
t0 = time.time()
import os; out = os.path.dirname(os.path.abspath(__file__)) + "/cache/preview"
import os; os.makedirs(out, exist_ok=True)
for T in sorted(times):
    while t < T - 1e-9:
        S["drive"](f, t, dt, rng)
        f.step(dt, **S.get("step", {}))
        t += dt
    look = S["look"](T) if callable(S["look"]) else S["look"]
    img = L.render(f.dye[0], int(T * 100), **look)
    Image.fromarray(img).save(f"{out}/{name}_{T:05.2f}.png")
    print(f"{name} t={T:.2f} max={f.get_dye().max(axis=(0,1)).round(2)} {time.time()-t0:.1f}s")
