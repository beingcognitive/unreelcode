"""render.py SHOT [--small] -- simulate a shot, write frames to cache/SHOT/%04d.png + stats.json"""
import sys, os, json, time
import numpy as np
from PIL import Image
import shots
from ink import Ink, Look

name = sys.argv[1]
small = "--small" in sys.argv
S = shots.SHOTS[name]
f = Ink(*S.get("grid", (960, 402)), consts=S["consts"])
L = Look(f.ctx)
rng = np.random.default_rng(S.get("seed", 1))
S["init"](f, rng)
sub = S["substeps"]
dt = 1.0 / (shots.FPS * sub)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", name + ("_small" if small else ""))
os.makedirs(out, exist_ok=True)
t = -S["preroll"]
t0 = time.time()
while t < -1e-9:
    S["drive"](f, t, dt, rng); f.step(dt, **S.get("step", {})); t += dt
stats = []
for i in range(S["frames"]):
    T = i / shots.FPS
    if "hook_frame" in S:
        S["hook_frame"](f, T, rng)
    if "look_f" in S and "look" not in S:
        S["look"] = S["look_f"](f)
    look = S["look"](T) if callable(S["look"]) else S["look"]
    img = L.render(f.dye[0], i + 1000 * hash(name) % 100000, **look)
    if small:
        img = np.asarray(Image.fromarray(img).resize((960, 540), Image.BILINEAR))
    Image.fromarray(img).save(f"{out}/{i:04d}.png", compress_level=1)
    v = f.get_vel()
    stats.append(dict(t=T, ke=float((v ** 2).mean()), steps=f.steps))
    if S.get("paused", lambda T: False)(T):
        continue
    for _ in range(sub):
        S["drive"](f, t, dt, rng); f.step(dt, **S.get("step", {})); t += dt
if name == "codeB":
    assert shots.EDITED_SOURCE is not None
    open(f"{out}/edited_source.glsl", "w").write(shots.EDITED_SOURCE)
json.dump(dict(stats=stats, steps=f.steps, seconds=time.time() - t0,
               grid=[f.VW, f.VH, f.DW, f.DH]), open(f"{out}/stats.json", "w"))
print(name, "steps", f.steps, "time %.1fs" % (time.time() - t0))
