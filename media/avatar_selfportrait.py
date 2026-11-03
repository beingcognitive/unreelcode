"""The @unreelcode avatar, ( ^ ‿ ^ ), drawn in wet ink by the Ink film's solver.

  python media/avatar_selfportrait.py out/face   -> out/face_08.png is the avatar
"""
import sys, numpy as np
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "ink"))
from PIL import Image, ImageDraw, ImageFilter
from ink import Ink, Look
import shots
OUT = sys.argv[1]
f = Ink(540, 960, consts={"CURL": "0.8", "SINK": "10.0"})
L = Look(f.ctx)
W, H = f.DW, f.DH
cx, cy = W // 2, H // 2
layers = [Image.new("L", (W, H), 0) for _ in range(4)]
d = [ImageDraw.Draw(l) for l in layers]
# 1: crimson brackets  ( ... )
for sgn in (-1, 1):
    x = cx + sgn * 300
    box = (x - 170, cy - 330, x + 170, cy + 330) if True else None
    if sgn < 0:
        d[1].arc((x - 60, cy - 330, x + 300, cy + 330), 125, 235, fill=255, width=78)
    else:
        d[1].arc((x - 300, cy - 330, x + 60, cy + 330), -55, 55, fill=255, width=78)
# 0: happy closed eyes  ^ ^
for ex in (cx - 120, cx + 120):
    d[0].arc((ex - 62, cy - 150, ex + 62, cy - 30), 200, 340, fill=255, width=34)
# 2: big open smile (a filled half-moon), close under the eyes
d[2].chord((cx - 135, cy - 40, cx + 135, cy + 180), 0, 180, fill=255)
# 3 -> blush: light crimson cheeks (uses the crimson pigment at low density, layer 1 below)
blush = Image.new("L", (W, H), 0)
for bx in (cx - 215, cx + 215):
    ImageDraw.Draw(blush).ellipse((bx - 55, cy + 5, bx + 55, cy + 60), fill=255)
dens = (2.4, 2.4, 2.4, 0)
arr = np.zeros((H, W, 4), np.float32)
for k in range(4):
    a = np.asarray(layers[k].filter(ImageFilter.GaussianBlur(2.0)), np.float32) / 255
    arr[..., k] = a * dens[k]
arr[..., 1] += np.asarray(blush.filter(ImageFilter.GaussianBlur(10)), np.float32) / 255 * 0.35
f.set_dye(arr[::-1].copy())
rng = np.random.default_rng(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
shots.noise_vel(f, rng, 10.0, smooth=25)
look = dict(shots.TEXT_LOOK)
dt = 1 / 48
snap = {0, 8, 16, 24}
for i in range(25):
    if i in snap:
        img = L.render(f.dye[0], 7, **look)
        im = Image.fromarray(img).crop((0, cy - W // 2, W, cy + W // 2))
        im.save(f"{OUT}_{i:02d}.png")
    f.step(dt)
