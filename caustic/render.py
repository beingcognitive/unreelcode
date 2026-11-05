"""Render the picture (v3): every frame of every beat -> cache/frames/####.png, per-frame inputs and the measured
sharpness in cache/stats.json. Resumable; frames whose inputs repeat an earlier frame exactly reuse its image.

  hook    light through a wavy water surface (a sum of 5 travelling sine waves), traced with the same tracer
  setup   3/4 view of the rig (storyboard.setup_still): real rays, the real traced light on the floor
  floor   top-down views of the floor, traced for each frame's distance, tilt and framing (+ side diagram, overlay)
  proof   the glass alone (clear, over the floor grid) and a real cut through its surface (drawn, display only)

    python render.py [first] [last]
"""
import sys, json, shutil, numpy as np, torch
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter, zoom as nzoom
import timeline as T
from trace import Glass, PX, FW, FH, DEV

ROOT = Path(__file__).parent
OUT = ROOT / "cache" / f"frames{T.SUFFIX}"; OUT.mkdir(parents=True, exist_ok=True)
STATS = ROOT / "cache" / f"stats{T.SUFFIX}.json"
LAMP = np.array([1.0, 0.74, 0.44])
EXPO, CONTRAST = 0.16, 1.35                 # one exposure for the whole film: light is never rescaled per frame

_rng = np.random.default_rng(11)
_plaster = gaussian_filter(_rng.normal(0, 1, (FH, FW)), 1.2)
_plaster = 1 + 0.035 * _plaster / _plaster.std() + 0.02 * gaussian_filter(_rng.normal(0, 1, (FH, FW)), 9) * 9
yy, xx = np.mgrid[0:FH, 0:FW]
_vig = 1 - 0.55 * (((xx - FW / 2) / FW) ** 2 + ((yy - FH / 2) / (0.8 * FH)) ** 2)
TARGET = np.asarray(Image.open(ROOT / "cache" / "target.png"), np.float64) / 255


def look(E):
    """Display only: develop traced irradiance E (1.0 = bare beam) into sRGB: film curve, a little bloom, faint
    floor texture and room light. None of it moves light."""
    e = gaussian_filter(E, 0.8)
    bloom = gaussian_filter(e, 14) * 0.10 + gaussian_filter(e, 60) * 0.06
    lum = (e + bloom) * _plaster + 0.010 * _vig
    rgb = 1 - np.exp(-EXPO * (lum[..., None] * LAMP[None, None]) ** CONTRAST)
    rgb = np.clip(rgb, 0, 1) ** (1 / 2.2)
    return (rgb * 255 + _rng.uniform(-0.5, 0.5, rgb.shape)).clip(0, 255).astype(np.uint8)


def corr_square(E_sq):
    """how much a glass-sized square of light looks like the face (the music's input)"""
    sq = nzoom(E_sq, TARGET.shape[0] / E_sq.shape[0], order=1)[:TARGET.shape[0], :TARGET.shape[1]]
    return float(np.corrcoef(gaussian_filter(sq, 1.0).ravel(), TARGET.ravel())[0, 1])


# ---------------------------------------------------------------- hook: light through water
class Water(Glass):
    """The same tracer, with the surface a sum of 5 travelling sine waves (heights and slopes analytic).
    Not a fluid simulation. n = 1.33, floor 30 cm below."""
    WAVES = [(17, 0.034, 0.3, 0.050), (71, 0.027, 1.9, 0.045), (133, 0.041, 4.1, 0.060), (205, 0.030, 2.2, 0.050),
             (262, 0.023, 5.0, 0.040)]   # (direction deg, wavelength m, phase, speed m/s)

    def __init__(self, R=5632, seed=3, Ww=0.50, d=0.30):
        self.W, self.D, self.n, self.R = Ww, d, 1.33, R
        g = torch.Generator().manual_seed(seed)
        k = torch.arange(R * R)
        jit = torch.rand((R * R, 2), generator=g)
        st = Ww / R
        self.py = (((k // R).float() + jit[:, 0]) * st).to(DEV)
        self.px = (((k % R).float() + jit[:, 1]) * st).to(DEV)
        self.ray_flux = (Ww / R) ** 2 / PX ** 2
        self._dirs = {}

    def at(self, t):
        h = torch.zeros_like(self.px); hx = torch.zeros_like(self.px); hy = torch.zeros_like(self.px)
        for ang, lam, ph, c in self.WAVES:
            kk = 2 * np.pi / lam; a = np.radians(ang)
            A = 0.55 / ((1.33 - 1) * self.D * kk * kk)
            arg = kk * (np.cos(a) * self.px + np.sin(a) * self.py) + ph - kk * c * t
            h += A * torch.sin(arg); co = A * kk * torch.cos(arg)
            hx += co * np.cos(a); hy += co * np.sin(a)
        self.h, self.hx, self.hy = h - h.min(), hx, hy
        self._dirs = {}


WPX = 0.26 / FW                               # the pool floor frame is 26 cm wide


# ---------------------------------------------------------------- the glass alone (proof), display only
def proof_frame(u):
    import storyboard as SB
    from overlay import check
    HL, WL = SB.HL, SB.WL
    img = Image.new("RGB", (FW, FH), (7, 6, 5)); d = ImageDraw.Draw(img)
    sc = 1.0 + 0.03 * T.ease(u)                                       # a slow push in (display)
    cx, cy = 500, 860
    s = 600 * sc; x0, y0 = cx - s / 2, cy - s / 2
    step = 60 * sc                                                     # the floor: a 1 cm grid, seen through the glass
    for k in range(-20, 21):
        x = cx + k * step; y = cy + k * step
        d.line((x, 0, x, FH), fill=(34, 30, 26), width=2); d.line((0, y, FW, y), fill=(34, 30, 26), width=2)
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); o = ImageDraw.Draw(ov)
    o.rectangle((x0, y0, x0 + s, y0 + s), fill=(200, 222, 230, 22))                    # faint tint of clear acrylic
    sheen = Image.new("L", (int(s), int(s)), 0)
    sv = np.clip(1 - np.abs(np.add.outer(np.arange(int(s)), np.arange(int(s))) / s - 0.62 - 0.08 * u) / 0.10, 0, 1)
    sheen = Image.fromarray((sv * 34).astype(np.uint8))
    ov.paste(Image.new("RGBA", sheen.size, (255, 245, 230, 255)), (int(x0), int(y0)), sheen)   # a soft reflection
    o.rectangle((x0, y0, x0 + s, y0 + s), outline=(255, 240, 215, 235), width=4)       # polished rim
    o.line((x0 + s + 5, y0 + 8, x0 + s + 5, y0 + s + 5), fill=(255, 240, 215, 120), width=4)  # its edge
    o.line((x0 + 8, y0 + s + 5, x0 + s + 5, y0 + s + 5), fill=(255, 240, 215, 120), width=4)
    col = 250                                                          # the cut: down the middle of the glass
    cxl = x0 + (col + 0.5) / HL.shape[0] * s
    for yy_ in np.arange(y0 + 6, y0 + s - 6, 22):
        o.line((cxl, yy_, cxl, min(yy_ + 11, y0 + s)), fill=(255, 214, 150, 110), width=2)
    prof = HL[::-1, col] - HL[:, col].min()
    pw, ph, px0, py0 = 560, 150, cx - 280, 1250
    n = len(prof); m = max(2, int(n * T.ease(min(1.0, u * 2.2))))           # the profile draws on
    xs = px0 + np.arange(n) / (n - 1) * pw; ys = py0 + ph - prof / prof.max() * ph
    o.line(list(zip(xs[:m], ys[:m])), fill=(255, 220, 160, 255), width=4)
    o.line((px0, py0 + ph + 4, px0 + pw, py0 + ph + 4), fill=(120, 110, 96, 255), width=2)
    mag = (ph / prof.max()) / (pw / WL)
    f = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 30)
    lab = f"side view, curve magnified {mag:.0f}×"
    check((px0, py0 + ph + 14, px0 + o.textlength(lab, font=f), py0 + ph + 50))
    o.text((px0, py0 + ph + 14), lab, font=f, fill=(180, 170, 152, int(255 * min(1, u * 3))))
    return np.asarray(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"))


# ---------------------------------------------------------------- framing of the floor shots (display, re-traced)
def floor_frame(t):
    """(px, centre offset x, centre offset y) for the top-down floor shots"""
    if t < 22.6: return PX * 1.05, 0.012, 0.0                                       # the sweep and the hold
    if t < 25.0:                                                                    # code card: centred, 2 cm lower
        return PX * 1.0, 0.0, 0.02 * T.ease((t - 22.6) / 0.4) * (1 - T.ease((t - 24.7) / 0.3))
    return PX * 1.0, 0.0, 0.0


def setup_params(t):
    """the 3/4 view: the glass 50 cm above the floor; rays travel from the lamp and the light lands. The camera stays
    focused on the glass all through the shot, so the floor light stays a soft glow (depth of field, display only):
    the face is first seen at the end of the sweep."""
    u = (t - 4.0) / 4.0
    e = T.ease(u)
    pos = (0.60 - 0.06 * e, -0.74 + 0.08 * e, 1.10 - 0.06 * e)
    ray_f = float(np.clip((t - 4.2) / 1.4, 0, 1))
    light = float(np.clip((ray_f - 0.75) / 0.25, 0, 1))
    return dict(pos=pos, look=(0.0, 0.0, 0.42), fov=60, ray_f=ray_f, blur=SETUP_BLUR, light=light, gz=T.SETUP_D)


SETUP_BLUR = 55.0                              # texture pixels (0.20 m over 1000 px): 11 mm, enough to hide the face


def main(a, b):
    import storyboard as SB
    stats = json.loads(STATS.read_text()) if STATS.exists() else {}
    seen = {v["key"]: int(k) for k, v in stats.items() if "key" in v and (OUT / f"{int(k):04d}.png").exists()}
    g = water = None
    last_sharp = 0.0
    for i in range(a, b):
        t = i / T.FPS; name = T.shot_at(t)[0]
        f = OUT / f"{i:04d}.png"
        if str(i) in stats and f.exists():
            last_sharp = stats[str(i)]["sharp"]; continue
        rec = dict(t=t, shot=name)
        if name == "hook":
            if water is None: water = Water()
            water.at(t)
            E = water.wall(water.D, px=WPX)
            img = look(E)
            side = int(round(0.10 / WPX)); r0, c0 = FH // 2 - side // 2, FW // 2 - side // 2
            sh = corr_square(E[r0:r0 + side, c0:c0 + side]); key = None
        elif name == "setup":
            p = setup_params(t)
            img = np.asarray(SB.setup_still(**p)[0])
            Es = SB.floor_light(0.20, 1000, T.SETUP_D)
            Eb = gaussian_filter(Es, p["blur"]) * p["light"]
            n = Es.shape[0]; side = int(round(0.10 / 0.20 * n)); r0 = n // 2 - side // 2
            sh = corr_square(Eb[r0:r0 + side, r0:r0 + side]) if p["light"] > 0 else 0.0
            rec.update(blur=p["blur"], ray_f=p["ray_f"]); key = None
        elif name == "proof":
            img = proof_frame((t - 8.0) / 4.0); sh = 0.0; key = None           # no light on screen: nothing like the face
        else:
            if g is None: g = Glass()
            d, bm = T.wall_d(t), T.beam(t)
            px, ox, oy = floor_frame(t)
            key = f"{d:.6f}|{bm[0]:.4f}|{bm[1]:.4f}|{px:.9f}|{ox:.5f}|{oy:.5f}"
            if key in seen:
                shutil.copyfile(OUT / f"{seen[key]:04d}.png", f)
                stats[str(i)] = dict(stats[str(seen[key])], t=t, shot=name, reused=seen[key])
                last_sharp = stats[str(i)]["sharp"]; continue
            E = g.wall(d, bm, px=px, centre=(g.W / 2 - ox, g.W / 2 + oy))
            img = look(E)
            sh = g.sharpness(g.wall(d, bm), TARGET)
            rec.update(d=d, beam=list(bm), px=px, key=key)
        Image.fromarray(img).save(f)
        rec["sharp"] = sh; stats[str(i)] = rec; last_sharp = sh
        if key: seen[key] = i
        if i % 30 == 0:
            STATS.write_text(json.dumps(stats))
            print(f"{i:4d} t={t:5.2f} {name:6s} sharp={sh:.3f}", flush=True)
    STATS.write_text(json.dumps(stats))


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    b = int(sys.argv[2]) if len(sys.argv) > 2 else T.NF
    main(a, b)
