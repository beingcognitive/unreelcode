"""2D overlays (v7, 1080x1920): captions, the instrument readout, the code card and the end card.
The code shown is read from design.py, the readout from the same timeline functions the light is traced with, and
the relief and solve size from cache/lens.npz. Every text block is checked against the Reels safe zone."""
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import timeline as T

ROOT = Path(__file__).parent
SERIF = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"
W, H = 1080, 1920
REPO = "github.com/beingcognitive/unreelcode"
REPO_1, REPO_2 = REPO[:REPO.rindex("/")], REPO[REPO.rindex("/"):]
PAPER = (246, 240, 230)
CREAM = (240, 232, 214)
SCRIM = (10, 8, 6)
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 40, 940, 220, 1540

_lens = np.load(ROOT / "cache" / "lens.npz")
RELIEF_MM = float(_lens["H"].max() * 1e3)
NSOLVE = int(_lens["N"])
SRC = (ROOT / "design.py").read_text().splitlines()


def font(path, size, index=0): return ImageFont.truetype(path, size, index=index)
fcode = font(MONO, 56)                               # cap height measured below (>= 40 px)
flab = font(MONO, 40)
fread = font(MONO, 40)
furl = font(MONO, 40)


def cap_height(f):
    bb = f.getbbox("H"); return bb[3] - bb[1]


def ease(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)


def fade(ft, t0, t1, fi=0.25, fo=0.3):
    if ft < t0 or ft > t1: return 0.0
    a = 1.0 if t0 == 0.0 else ease((ft - t0) / fi)
    return a * (1 - ease((ft - (t1 - fo)) / fo))


def check(box):
    x0, y0, x1, y1 = box
    assert x0 >= SAFE_L and x1 <= SAFE_R and y0 >= SAFE_T and y1 <= SAFE_B, box


HOOK = [("Light through water", 62), ("makes these lines.", 62)]
CAPTIONS = [  # (start, end, lines, y)
    (0.0, 3.7, HOOK, 262),
    (4.3, 6.1, [("What if a glass were", 62), ("shaped on purpose?", 62)], 262),
    (6.3, 7.8, [("…into a face.", 66)], 262),                    # words only: the face is first seen at 18 s
    (8.3, 11.7, [("No picture on this glass.", 60), ("It's just very slightly curved.", 54)], 262),
    (12.3, 20.4, [("Lower the glass:", 60), ("watch the lines fold.", 60)], 262),
]


def block(img, lines, y, a):
    """centred lines on a soft dark scrim; a = opacity"""
    if a <= 0: return img
    base = img.convert("RGBA"); ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    rows, h = [], y
    for s, sz in lines:
        f = font(SERIF, sz); bb = d.textbbox((0, 0), s, font=f)
        rows.append((s, f, h, bb[2] - bb[0], bb[1])); h += (bb[3] - bb[1]) + int(sz * 0.42)
    wmax = max(r[3] for r in rows)
    check(((W - wmax) / 2, y, (W + wmax) / 2, h))
    d.rounded_rectangle(((W - wmax) / 2 - 36, y - 28, (W + wmax) / 2 + 36, h - int(lines[-1][1] * 0.42) + 32),
                        radius=28, fill=SCRIM + (int(170 * a),))
    for s, f, yy, w, top in rows:
        d.text(((W - w) / 2, yy - top), s, font=f, fill=PAPER + (int(255 * a),))
    return Image.alpha_composite(base, ov)


def pill(img, rows, y0, a, col):
    """centred monospace rows on a dark pill"""
    if a <= 0: return img
    base = img.convert("RGBA"); ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    lh = 52; wmax = max(d.textlength(s, font=f) for s, f in rows)
    x = (W - wmax) / 2
    check((x, y0, x + wmax, y0 + lh * len(rows)))
    d.rounded_rectangle((x - 22, y0 - 12, x + wmax + 22, y0 + lh * len(rows) + 2), radius=16, fill=SCRIM + (int(160 * a),))
    for k, (s, f) in enumerate(rows):
        w = d.textlength(s, font=f)
        d.text(((W - w) / 2, y0 + k * lh), s, font=f, fill=col + (int(240 * a),))
    return Image.alpha_composite(base, ov)


def readout(img, ft):
    """the distance the light is traced for; gold at the design distance"""
    a = ease((ft - 12.0) / 0.4) * (1 - ease((ft - 22.4) / 0.25))
    if a <= 0: return img
    d_cm = T.wall_d(ft) * 100
    hot = abs(T.wall_d(ft) - T.D) < 0.0015
    return pill(img, [(f"glass to floor {d_cm:4.1f} cm", fread)], 1468, a,
                (255, 214, 150) if hot else (205, 195, 176))


def diagram(img, ft):
    """the persistent side view (lamp -> glass -> floor), live with the glass's height above the floor"""
    a = ease((ft - 12.1) / 0.4) * (1 - ease((ft - 22.4) / 0.25))
    if a <= 0: return img
    import storyboard as SB
    drawn = np.asarray(SB.diagram(img.convert("RGB"), T.wall_d(ft), T.beam(ft)), np.float32)
    base = np.asarray(img.convert("RGB"), np.float32)
    return Image.fromarray((base + (drawn - base) * a).round().astype(np.uint8))


def setup_labels(img, ft):
    """lamp / glass / floor, pointing at the 3/4 view (same camera as render.setup_params)"""
    a = ease((ft - 4.7) / 0.5) * (1 - ease((ft - 7.5) / 0.4))
    if a <= 0: return img
    import storyboard as SB, render as R
    p = R.setup_params(ft)
    cam = SB.Cam(pos=p["pos"], look=p["look"], fov=p["fov"], ss=1)
    WL = SB.WL; L = 0.065; lz = T.SETUP_D + 0.16
    pts = dict(lamp=cam(np.array([[L, -L, lz]]))[0], glass=cam(np.array([[WL / 2, -WL / 2, T.SETUP_D]]))[0],
               floor=cam(np.array([[0.035, -0.03, 0.0]]))[0])
    base = img.convert("RGBA"); ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    f = font(SERIF, 44)
    for name, (x, y) in pts.items():
        tx, ty = x + 110, min(max(y - 20, 430), 1480)
        w = d.textlength(name, font=f); check((tx, ty, tx + w, ty + 44))
        d.line([(tx - 10, ty + 26), (x, y)], fill=(220, 205, 180, int(200 * a)), width=2)
        d.text((tx, ty), name, font=f, fill=(246, 240, 230, int(255 * a)))
    return Image.alpha_composite(base, ov)


# ---------------------------------------------------------------- the code card (bars 10-12)
def _line(prefix):
    hits = [l for l in SRC if l.strip().startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0].strip()


CODE = [_line("W = 0.10"), _line("D = 0.50")]
CODE_T0 = 22.75
CODE_DT = 0.25                                       # one code line every quarter second


def code_card(img, ft):
    a = ease((ft - 22.6) / 0.25) * (1 - ease((ft - 24.75) / 0.25))
    if a <= 0: return img
    base = img.convert("RGBA")
    sh = np.zeros((H, W, 4), np.uint8)
    grad = np.clip((640 - np.arange(H)) / 110, 0, 1) * 0.90
    sh[..., 3] = (grad[:, None] * 255 * a).astype(np.uint8)
    ov = Image.alpha_composite(Image.new("RGBA", base.size, (0, 0, 0, 0)), Image.fromarray(sh))
    d = ImageDraw.Draw(ov)
    x0, y, lh = 64, 250, 76
    for k, s in enumerate(CODE):
        ak = a * ease((ft - (CODE_T0 + CODE_DT * k)) / 0.2)
        w = d.textlength(s, font=fcode)
        check((x0, y, x0 + w, y + lh))
        col = (255, 214, 150) if s.startswith("D = ") else (238, 228, 208)
        d.text((x0, y), s, font=fcode, fill=col + (int(255 * ak),))
        y += lh
    lab = f"relief {RELIEF_MM:.2f} mm · solved {NSOLVE}×{NSOLVE}"
    ak = a * ease((ft - (CODE_T0 + 0.55)) / 0.25)
    w = d.textlength(lab, font=flab)
    check((x0, y + 10, x0 + w, y + 60))
    d.text((x0, y + 10), lab, font=flab, fill=(170, 164, 150, int(255 * ak)))
    d.text((x0, y + 64), "design.py  ·  cache/lens.npz", font=font(MONO, 30), fill=(120, 116, 108, int(255 * ak)))
    return Image.alpha_composite(base, ov)


# ---------------------------------------------------------------- end card (bars 13-14)
END0 = 25.1
TEXT_OUT = 27.4                                       # the dissolve into frame 0 starts at 27.5


def end_card(img, ft):
    out = 1 - ease((ft - (TEXT_OUT - 0.45)) / 0.45)
    a1 = ease((ft - END0) / 0.6) * out
    a3 = ease((ft - END0 - 0.8) / 0.5) * out
    if a1 <= 0: return img
    img = block(img, [("A self-portrait,", 70), ("in light.", 70)], 250, a1)
    return pill(img, [(REPO_1, furl), (REPO_2, furl)], 1432, a3, CREAM)


def apply(img, ft):
    im = Image.fromarray(img)
    im = setup_labels(im, ft)
    im = diagram(im, ft)
    for t0, t1, lines, y in CAPTIONS:
        a = fade(ft, t0, t1)
        if a > 0: im = block(im, lines, y, a)
    im = readout(im, ft)
    im = code_card(im, ft)
    im = end_card(im, ft)
    return np.array(im.convert("RGB"))


if __name__ == "__main__":
    print("cap heights: code", cap_height(fcode), "readout", cap_height(fread), "url", cap_height(furl))
