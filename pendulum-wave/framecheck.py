"""Project every bob (centre +- radius) through the timeline camera on every 3D frame; report extents per segment."""
import numpy as np
import timeline as T
R = 0.019
segs = {}
for f in range(T.N_3D):
    cam = T.camera(f); u, v, s = T.project(cam, T.bob_positions(f)); r = R * s
    t = f / T.FPS; key = next(i for i, m in enumerate(T.MOVES) if t <= m[1] + 1e-9) if t <= T.MOVES[-1][1] else len(T.MOVES)
    e = segs.setdefault(key, [1e9, -1e9, 1e9, -1e9])
    e[0] = min(e[0], (u - r).min()); e[1] = max(e[1], (u + r).max()); e[2] = min(e[2], (v - r).min()); e[3] = max(e[3], (v + r).max())
for k, e in sorted(segs.items()):
    m = T.MOVES[k] if k < len(T.MOVES) else None
    print(f"move {k} ({m[0]:.1f}-{m[1]:.1f}s)" if m else "after", "x %.0f..%.0f  y %.0f..%.0f" % tuple(e))
