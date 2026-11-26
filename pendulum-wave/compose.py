"""Compose: rendered frames + captions + the clock, then the end card and the loop dissolve; encode with the audio.
  python compose.py RAW_DIR OUT_MP4 [--scale 0.5]
"""
import json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import timeline as T

J = T.J
FPS, W, H = T.FPS, T.W, T.H
FONT = "/System/Library/Fonts/Avenir Next.ttc"
F_CAP = ImageFont.truetype(FONT, 62, index=2)
F_URL = ImageFont.truetype(FONT, 40, index=5)
F_RO = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 34)
INK = (28, 28, 30); PANEL = (247, 245, 239); CARD_BG = (245, 242, 235); URL_INK = (60, 60, 66); RO_INK = (40, 40, 44)
SAFE = (40, 220, 940, 1540)
TG = T.T_PRE + T.GAMMA
NS = J["swings"]
# every number below comes from out/sim.json (the integration), not typed in
SIMT = lambda x: T.T_PRE + x
CAPTIONS = [
    (0.15, 3.00, [f"{J['n']} pendulums.", "1 push."]),
    (3.15, 7.00, ["Each ball plays a note", "as it crosses", "the glowing line."]),
]
SHOW_CHAPTER_LABELS = False                # no text after the opening: the payoff reads from picture and sound
F_CH = ImageFont.truetype(FONT, 100, index=2)
F_CHT = ImageFont.truetype(FONT, 50, index=5)
CH_CAND = [(60, 700), (60, 1060), (60, 480)]
CH_XY = CH_CAND[0]


def fade(t, a, b, r=0.25):
    if t < a or t > b: return 0.0
    return min(1.0, (t - a) / r, (b - t) / r)


def text_block(dr, xy, lines, font, alpha, fill=INK, spacing=10, panel=None):
    x, y = xy; lay = []
    for ln in lines:
        bb = dr.textbbox((x, y), ln, font=font); lay.append((ln, (x, y), bb)); y = bb[3] + spacing
    boxes = [bb for _, _, bb in lay]
    if panel is not None:
        pd, col = panel
        pd.rounded_rectangle((min(b[0] for b in boxes) - 18, min(b[1] for b in boxes) - 14,
                              max(b[2] for b in boxes) + 18, max(b[3] for b in boxes) + 16),
                             radius=18, fill=col[:3] + (int(col[3] * alpha),))
    for ln, p, bb in lay:
        dr.text(p, ln, font=font, fill=fill + (int(255 * alpha),))
    return boxes, y


def centred_block(dr, y, lines, font, alpha, panel=None, spacing=10):
    """each line centred horizontally on the frame; one panel around the block"""
    lay = []; yy = y
    for ln in lines:
        w = dr.textlength(ln, font=font); x = (W - w) / 2
        bb = dr.textbbox((x, yy), ln, font=font); lay.append((ln, (x, yy), bb)); yy = bb[3] + spacing
    boxes = [bb for _, _, bb in lay]
    if panel is not None:
        pd, col = panel
        pd.rounded_rectangle((min(b[0] for b in boxes) - 18, min(b[1] for b in boxes) - 14,
                              max(b[2] for b in boxes) + 18, max(b[3] for b in boxes) + 16), radius=18,
                             fill=col[:3] + (int(col[3] * alpha),))
    for ln, p, bb in lay:
        dr.text(p, ln, font=font, fill=INK + (int(255 * alpha),))
    return boxes, yy


def overlay(img, f):
    t = f / FPS
    base = img.convert("RGBA")
    pan = Image.new("RGBA", base.size, (0, 0, 0, 0)); pdr = ImageDraw.Draw(pan)
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
    boxes = []; overlay.chbox = None
    for i, (a, b, lines) in enumerate(CAPTIONS):
        al = fade(t, a, b)
        if al > 0:
            bx, y2 = centred_block(dr, CAP_XY.get(i, CAND[0])[1], lines, F_CAP, al, panel=(pdr, PANEL + (205,)))
            boxes += bx
    # chapter readout, only while the camera holds still on a chapter: "4 lines · t = 15.0 s" (t live, from the frame)
    s = T.sim_time(t)
    for tc, n in (T.CHAPTERS if SHOW_CHAPTER_LABELS else []):
        al = fade(s, tc + 0.1, tc + 1.5, 0.2) if n > 1 else fade(s, tc - 0.1, tc + 0.7, 0.15)   # while the lines are distinct
        if al > 0:
            bx, y2 = text_block(dr, CH_XY, [f"{n} line{'s' if n > 1 else ''}"], F_CH, al, fill=INK, panel=None)
            bx2, _ = text_block(dr, (CH_XY[0] + 4, y2 + 6), [f"t = {s:4.1f} s"], F_CHT, al, fill=RO_INK, panel=None)
            x0 = min(b[0] for b in bx + bx2) - 18; y0 = min(b[1] for b in bx + bx2) - 14
            x1 = max(b[2] for b in bx + bx2) + 18; y1 = max(b[3] for b in bx + bx2) + 16
            pdr.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=PANEL + (int(215 * al),))
            boxes += [(x0 + 18, y0 + 14, x1 - 18, y1 - 16)]
            overlay.chbox = (x0, y0, x1, y1)
    for bb in boxes:
        assert SAFE[0] <= bb[0] - 18 and bb[2] + 18 <= SAFE[2] and SAFE[1] <= bb[1] - 14 and bb[3] + 16 <= SAFE[3], (bb, f)
    overlay.boxes = boxes
    overlay.chboxes = [bb for bb in boxes if overlay.chbox and bb == (overlay.chbox[0] + 18, overlay.chbox[1] + 14, overlay.chbox[2] - 18, overlay.chbox[3] - 16)]
    return Image.alpha_composite(Image.alpha_composite(base, pan), lay).convert("RGB")


CAND = [(70, 250), (70, 1250), (70, 340), (70, 1150), (380, 250), (380, 1250)]
CAP_T = {}   # caption positions, in order of preference
CAP_XY = {}
if os.path.exists("cache/cap_place.json"):
    _cp = json.load(open("cache/cap_place.json"))
    if len(_cp["t"]) == len(CAPTIONS):
        CAP_XY = {int(k): tuple(v) for k, v in _cp["xy"].items()}
        CAPTIONS = [(a, b, c[2]) for (a, b), c in zip(_cp["t"], CAPTIONS)]


def place_captions():
    """for each caption, the first candidate position that covers no bob on any frame it is visible;
    if none is clear, try the window shifted by up to +-1.6 s"""
    global CAP_XY, CAPTIONS
    for i in range(len(CAPTIONS)):
        a0, b0, lines = CAPTIONS[i]; done = False
        for dt in (0,):                                   # the two captions keep their times
            if a0 + dt < 0.1: continue
            CAPTIONS[i] = (a0 + dt, b0 + dt, lines)
            frames = range(int((a0 + dt) * FPS), min(int((b0 + dt) * FPS) + 1, T.N_3D))
            for xy in CAND:
                CAP_XY = {**CAP_XY, i: xy}
                try:
                    if not any(covered_bobs(f, only=i) for f in frames): done = True
                except AssertionError:
                    pass
                if done: break
            if done:
                if dt: print(f"caption {i} shifted by {dt:+.1f} s")
                break
        if not done:
            CAPTIONS[i] = (a0, b0, lines); CAP_XY[i] = CAND[0]; print("no clear position for caption", i)
    json.dump(dict(xy={str(k): v for k, v in CAP_XY.items()}, t=[[c[0], c[1]] for c in CAPTIONS]), open("cache/cap_place.json", "w"))


def covered_bobs(f, R=0.019, only=None):
    """bobs (in front of the camera, inside the frame) that a caption or clock panel covers on frame f"""
    global CAPTIONS
    if only is not None:
        keep = CAPTIONS; CAPTIONS = [c if j == only else (0, -1, c[2]) for j, c in enumerate(keep)]
        try: overlay(Image.new("RGB", (W, H)), f)
        finally: CAPTIONS = keep
        boxes = [bb for bb in overlay.boxes if bb not in overlay.chboxes]   # the caption only, not the chapter label
    else:
        overlay(Image.new("RGB", (W, H)), f); boxes = overlay.boxes
    cam = T.camera(f); u, v, sc = T.project(cam, T.bob_positions(f))
    p = np.array(cam["pos"]); fwd = np.array(cam["target"]) - p
    z = (T.bob_positions(f) - p) @ (fwd / np.linalg.norm(fwd)); r = R * sc
    hits = []
    for bb in boxes:
        x0, y0, x1, y1 = bb[0] - 18, bb[1] - 14, bb[2] + 18, bb[3] + 16
        for k in range(T.NP):
            if z[k] > 0.05 and -r[k] < u[k] < W + r[k] and -r[k] < v[k] < H + r[k]:
                if x0 - r[k] < u[k] < x1 + r[k] and y0 - r[k] < v[k] < y1 + r[k]: hits.append(k)
    return sorted(set(hits))


def end_card(last_img, frame0_img, f):
    t = f / FPS - T.T_CARD
    bg = Image.new("RGB", (W, H), CARD_BG)
    k = min(1.0, t / 0.5); k = k * k * (3 - 2 * k)
    img = Image.blend(last_img, bg, k)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
    al = fade(t, 0.35, T.T_TOTAL - T.T_CARD - T.LOOP_DISSOLVE, 0.3)
    # a small drawing: a bar and 12 pendulums, each a little shorter, caught mid-wave
    x0, top = 80, 470
    dr.rounded_rectangle((x0 - 10, top - 10, x0 + 11 * 34 + 10, top), radius=4, fill=(18, 18, 20, int(255 * al)))
    import colorsys
    for i in range(12):
        Lp = 190 * (20 / (20 + i * 19 / 11)) ** 2
        ph = math.sin(2 * math.pi * (i / 11) * 1.0)
        ang = math.radians(16) * ph
        px = x0 + i * 34; bx, by = px + Lp * math.sin(ang), top + Lp * math.cos(ang)
        dr.line((px, top, bx, by), fill=(40, 40, 44, int(255 * al)), width=2)
        r, g, b = colorsys.hsv_to_rgb(0.02 + 0.62 * i / 11, 0.75, 0.85)
        dr.ellipse((bx - 11, by - 11, bx + 11, by + 11), fill=(int(r * 255), int(g * 255), int(b * 255), int(255 * al)))
    bx, y = text_block(dr, (70, 760), ["Made by code.", "Every swing is simulated."], F_CAP, al)
    bx2, _ = text_block(dr, (70, y + 40), ["github.com/beingcognitive/unreelcode"], F_URL, al, fill=URL_INK)
    for bb in bx + bx2:
        assert SAFE[0] <= bb[0] and bb[2] <= SAFE[2] and SAFE[1] <= bb[1] and bb[3] <= SAFE[3], bb
    img = Image.alpha_composite(img.convert("RGBA"), lay).convert("RGB")
    td = T.T_TOTAL - T.LOOP_DISSOLVE
    f_td = int(round(td * FPS))
    if f >= f_td:
        q = min(1.0, (f - f_td) / (T.N_TOTAL - 1 - f_td)); q = q * q * (3 - 2 * q)       # exactly frame 0 on the last frame
        img = Image.blend(img, frame0_img, q)
    return img


if __name__ == "__main__":
    raw_dir, out_mp4 = sys.argv[1], sys.argv[2]
    scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1.0
    fr_dir = raw_dir.rstrip("/") + "_frames"; os.makedirs(fr_dir, exist_ok=True)
    full = lambda f: (lambda im: im.resize((W, H), Image.LANCZOS) if im.size != (W, H) else im)(
        Image.open(os.path.join(raw_dir, f"{f:05d}.png")).convert("RGB"))
    frame0 = overlay(full(0), 0); last = full(T.N_3D - 1)
    w, h = int(W * scale), int(H * scale)
    for f in range(T.N_TOTAL):
        img = overlay(full(f), f) if f < T.N_3D else end_card(last, frame0, f)
        if scale != 1.0: img = img.resize((w, h), Image.LANCZOS)
        img.save(os.path.join(fr_dir, f"{f:05d}.png"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(fr_dir, "%05d.png"),
                    "-i", "cache/audio.wav", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    print("wrote", out_mp4, T.N_TOTAL, "frames")
