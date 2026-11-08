"""Scan every rendered frame for glitches: single-frame flicker (a frame unlike both neighbours while they agree),
sudden dark regions (e.g. a black roof), fireflies (isolated very bright pixels), and missing frames.
usage: python render/qa.py RAW_DIR N_FRAMES  -> prints a report and writes RAW_DIR/qa.json"""
import json, os, sys
import numpy as np
from PIL import Image, ImageFilter

d, n = sys.argv[1], int(sys.argv[2])
small, dark, fire = [], [], []
missing = [f for f in range(n) if not os.path.exists(os.path.join(d, f"{f:05d}.png"))]
for f in range(n):
    p = os.path.join(d, f"{f:05d}.png")
    if not os.path.exists(p):
        small.append(None); dark.append(np.nan); fire.append(0); continue
    im = Image.open(p).convert("L")
    s = np.asarray(im.resize((180, 320), Image.BILINEAR), float) / 255
    small.append(s)
    dark.append(float((s < 0.03).mean()))
    g = np.asarray(im, float) / 255
    med = np.asarray(im.filter(ImageFilter.MedianFilter(5)), float) / 255
    fire.append(int(((g > 0.97) & (med < 0.55)).sum()))
flags = []
for f in range(1, n - 1):
    a, b, c = small[f - 1], small[f], small[f + 1]
    if a is None or b is None or c is None: continue
    dab, dbc, dac = np.abs(a - b).mean(), np.abs(b - c).mean(), np.abs(a - c).mean()
    if dab > 0.02 and dbc > 0.02 and dac < 0.5 * min(dab, dbc):
        flags.append(dict(frame=f, kind="flicker", d_prev=round(dab, 4), d_next=round(dbc, 4), d_skip=round(dac, 4)))
    jump = dark[f] - 0.5 * (dark[f - 1] + dark[f + 1])
    if abs(jump) > 0.01:
        flags.append(dict(frame=f, kind="dark-region jump", value=round(jump, 4)))
for f in range(n):
    if fire[f] > 40:
        flags.append(dict(frame=f, kind="fireflies", pixels=fire[f]))
# sustained dark-region changes that are not caused by the camera cut (report the biggest steps)
dk = np.array(dark)
steps = np.abs(np.diff(dk))
top = [int(i) for i in np.argsort(np.nan_to_num(steps))[-5:][::-1]]
rep = dict(n=n, missing=missing, flags=flags, largest_dark_steps=[(i, round(float(steps[i]), 4)) for i in top],
           max_fireflies=int(max(fire)))
json.dump(rep, open(os.path.join(d, "qa.json"), "w"), indent=1)
print(f"{n} frames, missing {len(missing)}, flags {len(flags)}, max fireflies {max(fire)}")
for fl in flags[:30]:
    print(" ", fl)
print("largest dark-area steps (frame, change):", rep["largest_dark_steps"])
