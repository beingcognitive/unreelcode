"""Render the 3D frames of the film from out/timeline.json. Resumable: frames already on disk are skipped.
  Blender -b --factory-startup --python render/render_frames.py -- --a 0 --b 40 --res 0.5 --samples 16 --dir out/raw_preview
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import scene as S  # noqa: E402  (scene.py's __main__ block does not run on import)

ROOT = S.ROOT
TL = json.load(open(os.path.join(ROOT, S.arg("--tl", "out/timeline.json"))))
a = S.arg("--a", 0, int); b = S.arg("--b", len(TL["frames"]), int)
outdir = os.path.join(ROOT, S.arg("--dir", "out/raw"))
os.makedirs(outdir, exist_ok=True)
if "--list" in S.ARGS:
    a_list = [int(v) for v in S.arg("--list").split(",")]
else:
    a_list = list(range(a, min(b, len(TL["frames"]))))
todo = [f for f in a_list if not os.path.exists(os.path.join(outdir, f"{f:05d}.png"))]
print(f"{len(todo)} frames to render in {outdir}", flush=True)
if todo:
    t0 = time.time()
    parts = S.build("all")
    S.render_settings(S.arg("--samples", 16, int), S.arg("--res", 0.5, float))
    print(f"build {time.time()-t0:.1f} s", flush=True)
    for n, f in enumerate(todo):
        fr = TL["frames"][f]
        S.pose(parts, fr["s"], fr.get("pencil_back", 0.0))
        S.camera(tuple(fr["pos"]), tuple(fr["target"]), fr["fov"],
                 fstop=(fr["fstop"] if fr["fstop"] > 0 else None), focus=fr["focus"])
        path = os.path.join(outdir, f"{f:05d}.png")
        S.bpy.context.scene.render.filepath = path + ".tmp.png"
        t1 = time.time()
        S.bpy.ops.render.render(write_still=True)
        os.replace(path + ".tmp.png", path)          # atomic: a killed run never leaves a half-written frame
        if n % 10 == 0 or n == len(todo) - 1:
            print(f"frame {f}: {time.time()-t1:.1f} s ({n+1}/{len(todo)}, {(time.time()-t0)/(n+1):.1f} s avg)", flush=True)
