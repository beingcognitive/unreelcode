"""v3 storyboard: one full-size still per beat -> out/storyboard/.  python storyboard.py

The rig stands vertically to fit the 9:16 frame: the lamp above, the glass below it, the light landing on the floor.
All light on the floor is traced (trace.py). The rays drawn in the setup and the diagrams are real rays through the
solved surface (same Snell refraction as trace.py, sampled at a few points). The 3/4 view is drawn with a simple
pinhole projection; the camera's depth of field (soft floor in the setup) is display only.
Simplifications: the lamp is parallel light, the glass has no thickness for the optics, Fresnel losses are ignored.
"""
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.interpolate import RectBivariateSpline
from scipy.ndimage import gaussian_filter
import overlay as O
from trace import Glass, PX, FW, FH

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "storyboard"; OUT.mkdir(parents=True, exist_ok=True)
LAMP = np.array([1.0, 0.74, 0.44])
MONO, SERIF = O.MONO, O.SERIF


def develop(E, expo=0.16, contrast=1.35, bloom=True):
    """same film curve as render.look(), for any image size (display only)"""
    e = gaussian_filter(E, 0.8)
    if bloom: e = e + gaussian_filter(e, 14) * 0.10 + gaussian_filter(e, 60) * 0.06
    rgb = 1 - np.exp(-expo * (e[..., None] * LAMP[None, None]) ** contrast)
    return (np.clip(rgb, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


# ---------------------------------------------------------------- real rays through the solved glass
z = np.load(ROOT / "cache" / "lens.npz")
HL, WL, DL, NG = z["H"], float(z["W"]), float(z["D"]), float(z["n"])
cc = (np.arange(HL.shape[0]) + 0.5) * WL / HL.shape[0]
SPL = RectBivariateSpline(cc, cc, HL, kx=3, ky=3)               # H[iy, ix]: first axis y


def rays(px, py, d, beam=(0.0, 0.0)):
    """exit point and wall/floor hit for light entering the glass at (px, py) (m, glass coords)"""
    h = SPL.ev(py, px); hx = SPL.ev(py, px, dy=1); hy = SPL.ev(py, px, dx=1)
    ax, ay = np.sin(np.radians(beam[0])) / NG, np.sin(np.radians(beam[1])) / NG
    k = np.array([ax, ay, np.sqrt(1 - ax * ax - ay * ay)])
    n = np.stack([-hx, -hy, np.ones_like(hx)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    c1 = n @ k; k2 = 1 - NG * NG * (1 - c1 * c1)
    t = NG * k[None] + (np.sqrt(k2) - NG * c1)[:, None] * n
    s = (d - h) / t[:, 2]
    return px + s * t[:, 0], py + s * t[:, 1], t


# ---------------------------------------------------------------- beat 1: light through water (the everyday anchor)
def water_still():
    """A wavy water surface = a sum of 5 sine waves (not a fluid simulation), traced with the same tracer."""
    n, Ww, d = 512, 0.45, 0.30
    x = (np.arange(n) + 0.5) * Ww / n
    Y, X = np.meshgrid(x, x, indexing="ij")
    Hs = np.zeros((n, n))
    rng = np.random.default_rng(4)
    for ang, lam, ph in ((17, 0.034, 0.3), (71, 0.027, 1.9), (133, 0.041, 4.1), (205, 0.030, 2.2), (262, 0.023, 5.0)):
        k = 2 * np.pi / lam; a = np.radians(ang)
        A = 0.55 / ((1.33 - 1) * d * k * k)                       # each wave alone would focus a little past the floor
        Hs += A * np.sin(k * (np.cos(a) * X + np.sin(a) * Y) + ph)
    Hs -= Hs.min()
    np.savez(ROOT / "cache" / "water.npz", H=Hs, W=Ww, D=d, n=1.33, N=n)
    g = Glass(lens=ROOT / "cache" / "water.npz", R=5120)
    E = g.wall(d, px=0.26 / FW)
    img = develop(E)
    del g
    return img, dict(waves=5, depth_m=d, amplitude_mm=float(Hs.max() * 1e3))


# ---------------------------------------------------------------- pinhole camera + drawing helpers (display)
class Cam:
    def __init__(self, pos, look, up=(0, 0, 1), fov=40, size=(FW, FH), ss=2):
        self.p = np.array(pos, float); f = np.array(look, float) - self.p; f /= np.linalg.norm(f)
        r = np.cross(f, up); r /= np.linalg.norm(r); u = np.cross(r, f)
        self.R = np.stack([r, u, f]); self.ss = ss
        self.W, self.H = size[0] * ss, size[1] * ss
        self.f = 0.5 * self.H / np.tan(np.radians(fov) / 2)

    def __call__(self, P):
        q = (np.atleast_2d(P) - self.p) @ self.R.T
        return np.stack([self.W / 2 + self.f * q[:, 0] / q[:, 2], self.H / 2 - self.f * q[:, 1] / q[:, 2]], -1)


def persp_coeffs(src, dst):
    """PIL PERSPECTIVE coefficients mapping output (dst) pixels to input (src) pixels"""
    A, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]; b += [u, v]
    return np.linalg.solve(np.array(A, float), np.array(b, float))


_FLOOR = {}


def floor_light(side=0.20, res=1000, d=None):
    """the light on the floor with the glass d above it (default D), traced once per (d, side) and cached"""
    d = DL if d is None else d
    k = (round(d, 6), side, res)
    if k not in _FLOOR:
        g = Glass(R=4096); _FLOOR[k] = g.wall(d, size=(res, res), px=side / res); del g
    return _FLOOR[k]


def setup_still(pos=(0.50, -0.62, 0.98), look=(0.0, 0.0, 0.40), fov=52, ray_f=1.0, blur=42.0, light=1.0, ss=2, gz=None):
    """3/4 view of the whole rig: lamp above, the one glass, the floor below; real rays; real light on the floor.
    ray_f: how far the rays have travelled (0..1, display); blur: the camera's depth-of-field blur on the floor
    (texture pixels, display only); light: how much of the floor light has arrived."""
    cam = Cam(pos=pos, look=look, fov=fov, ss=ss)
    S = cam.ss
    img = Image.new("RGB", (cam.W, cam.H), (6, 5, 4))
    gz = DL if gz is None else gz                                     # the glass's height above the floor
    side, res = (0.20, 1000) if gz <= 0.6 else (0.32, 1280)
    E = floor_light(side, res, gz)
    floor_tex = develop(gaussian_filter(E, blur) * light if blur > 0.3 else E * light)
    tex = Image.fromarray(floor_tex)
    corners = np.array([[-side / 2, side / 2, 0], [side / 2, side / 2, 0], [side / 2, -side / 2, 0], [-side / 2, -side / 2, 0]])
    dst = cam(corners)
    src = [(0, 0), (res, 0), (res, res), (0, res)]
    warped = tex.transform((cam.W, cam.H), Image.PERSPECTIVE, persp_coeffs(src, dst), Image.BICUBIC)
    mask = Image.new("L", (cam.W, cam.H), 0); ImageDraw.Draw(mask).polygon([tuple(p) for p in dst], fill=255)
    wl = np.asarray(warped, np.int32) * (np.asarray(mask)[..., None] > 0)
    img = Image.fromarray(np.clip(np.asarray(img, np.int32) + wl, 0, 255).astype(np.uint8))   # light adds to the floor
    # a big dim floor around it, so the floor reads as a surface
    big = np.array([[-0.45, 0.45, 0], [0.45, 0.45, 0], [0.45, -0.45, 0], [-0.45, -0.45, 0]])
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    d.polygon([tuple(p) for p in cam(big)], outline=(70, 60, 50, 160), width=2 * S)
    for gx in np.linspace(-0.45, 0.45, 10):
        d.line([tuple(p) for p in cam(np.array([[gx, -0.45, 0], [gx, 0.45, 0]]))], fill=(40, 34, 28, 120), width=S)
        d.line([tuple(p) for p in cam(np.array([[-0.45, gx, 0], [0.45, gx, 0]]))], fill=(40, 34, 28, 120), width=S)
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    # rays: from the lamp straight down to the glass, then bent toward the floor (real refraction)
    lz = gz + 0.16                                                    # lamp height (display: parallel light)
    rng = np.random.default_rng(2)
    gi = (np.arange(8) + 0.5) / 8 * WL
    px, py = [a.ravel() for a in np.meshgrid(gi, gi)]
    px = np.clip(px + rng.uniform(-0.004, 0.004, px.size), 0.002, WL - 0.002)
    py = np.clip(py + rng.uniform(-0.004, 0.004, py.size), 0.002, WL - 0.002)
    X, Y, _ = rays(px, py, gz)
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    w2 = lambda x, y, zz: np.array([[x - WL / 2, y - WL / 2, zz]])
    L1 = lz - gz; L2 = np.sqrt((X - px) ** 2 + (Y - py) ** 2 + gz ** 2)
    for a, b, Xh, Yh, l2 in zip(px, py, X, Y, L2):
        p0, p1, p2 = cam(w2(a, b, lz))[0], cam(w2(a, b, gz))[0], cam(w2(Xh, Yh, 0.0))[0]
        r = ray_f * (L1 + l2)                                         # distance travelled along this ray
        if r <= 0: continue
        u1 = min(r / L1, 1.0)
        d.line([tuple(p0), tuple(p0 + (p1 - p0) * u1)], fill=(255, 214, 150, 70), width=2 * S)
        if r > L1:
            u2 = min((r - L1) / l2, 1.0)
            d.line([tuple(p1), tuple(p1 + (p2 - p1) * u2)], fill=(255, 220, 160, 95), width=2 * S)
    img = Image.alpha_composite(img, ov)
    # the glass: one thin clear square, rim highlight
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    top = np.array([[-WL / 2, -WL / 2, gz], [WL / 2, -WL / 2, gz], [WL / 2, WL / 2, gz], [-WL / 2, WL / 2, gz]])
    bot = top - [0, 0, 0.008]
    d.polygon([tuple(p) for p in cam(top)], fill=(190, 215, 225, 38))
    for e0, e1 in ((0, 1), (1, 2)):                                   # the visible side faces
        d.polygon([tuple(p) for p in cam(np.array([top[e0], top[e1], bot[e1], bot[e0]]))], fill=(210, 230, 235, 70))
    ct, cb = cam(top), cam(bot)
    d.line([tuple(p) for p in np.vstack([ct, ct[:1]])], fill=(255, 240, 215, 235), width=3 * S)
    d.line([tuple(cb[0]), tuple(cb[1]), tuple(cb[2])], fill=(255, 240, 215, 150), width=2 * S)
    for i in (0, 1, 2): d.line([tuple(ct[i]), tuple(cb[i])], fill=(255, 240, 215, 200), width=2 * S)
    img = Image.alpha_composite(img, ov)
    # the lamp: a simple box with a glowing underside, parallel light
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    L = 0.065; lb, lt = lz, lz + 0.05
    box = lambda zz: np.array([[-L, -L, zz], [L, -L, zz], [L, L, zz], [-L, L, zz]])
    B, T = cam(box(lb)), cam(box(lt))
    d.polygon([tuple(p) for p in B], fill=(255, 226, 180, 255))
    for e0, e1 in ((0, 1), (1, 2)):
        d.polygon([tuple(B[e0]), tuple(B[e1]), tuple(T[e1]), tuple(T[e0])], fill=(70, 63, 56, 255), outline=(170, 155, 135, 255))
    d.polygon([tuple(p) for p in T], fill=(96, 88, 78, 255), outline=(190, 175, 150, 255))
    img = Image.alpha_composite(img, ov)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0)); ImageDraw.Draw(glow).polygon([tuple(p) for p in B], fill=(255, 210, 150, 160))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(30 * S)))
    img = img.resize((FW, FH), Image.LANCZOS).convert("RGB") if S > 1 else img.convert("RGB")
    anchors = dict(lamp=cam(np.array([[L, -L, lb]]))[0] / S, glass=cam(np.array([[WL / 2, -WL / 2, gz]]))[0] / S,
                   floor=cam(np.array([[0.035, -0.03, 0.0]]))[0] / S)
    return img, anchors


def label(img, text, xy, to, size=40):
    """a label with a thin leader line to the thing it names (inside the safe zone)"""
    base = img.convert("RGBA"); ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    f = ImageFont.truetype(SERIF, size); w = d.textlength(text, font=f)
    O.check((xy[0], xy[1], xy[0] + w, xy[1] + size))
    d.line([(xy[0] - 10, xy[1] + size * 0.55), tuple(to)], fill=(220, 205, 180, 200), width=2)
    d.text(xy, text, font=f, fill=(246, 240, 230, 255))
    return Image.alpha_composite(base, ov).convert("RGB")


# ---------------------------------------------------------------- the persistent side-view diagram (display)
def diagram(img, d, beam=(0.0, 0.0), x0=46, y0=560, scale=440.0):
    """lamp -> glass -> floor, seen from the side, to scale; the rays are real rays along the glass's middle row"""
    base = img.convert("RGBA"); ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); g = ImageDraw.Draw(ov)
    wpx = WL * scale * 1.0                                          # the glass, 10 cm
    fy = y0 + 720; gy = fy - d * scale                               # the floor stays put; the glass moves (to scale, 440 px/m)
    cx = x0 + 70
    O.check((x0, y0 - 40, x0 + 160, fy + 64))
    g.rounded_rectangle((x0 - 14, y0 - 46, x0 + 168, fy + 70), radius=18, fill=(10, 8, 6, 175))
    tilt = np.radians(beam[1])
    lx, ly = cx, y0 + 6                                              # lamp
    ca, sa = np.cos(tilt), np.sin(tilt)
    pts = [(-40, -12), (40, -12), (40, 10), (-40, 10)]
    g.polygon([(lx + x * ca - y * sa, ly + x * sa + y * ca) for x, y in pts], fill=(60, 54, 48, 255))
    g.line([(lx - 40 * ca - 10 * sa, ly - 40 * sa + 10 * ca), (lx + 40 * ca - 10 * sa, ly + 40 * sa + 10 * ca)], fill=(255, 220, 170, 255), width=5)
    xs = np.linspace(0.006, WL - 0.006, 9)
    _, X, _ = rays(np.full_like(xs, WL / 2), xs, d, beam)              # side view: across = the glass's y axis
    for xg, xf in zip(xs, X):
        gxp = cx + (xg - WL / 2) * scale
        g.line([(gxp - (gy - ly) * np.tan(tilt), ly + 10), (gxp, gy)], fill=(255, 214, 150, 120), width=2)
        g.line([(gxp, gy), (cx + (xf - WL / 2) * scale, fy)], fill=(255, 220, 160, 170), width=2)
    g.line([(cx - wpx / 2, gy), (cx + wpx / 2, gy)], fill=(210, 235, 240, 255), width=5)      # glass
    g.line([(x0 - 4, fy), (x0 + 150, fy)], fill=(150, 136, 118, 255), width=4)               # floor
    f = ImageFont.truetype(MONO, 30)
    g.text((x0 + 4, y0 - 40), "lamp", font=f, fill=(220, 210, 190, 255))
    g.text((x0 + 4, gy - 38), "glass", font=f, fill=(220, 230, 235, 255))
    g.text((x0 + 4, fy + 8), "floor", font=f, fill=(200, 190, 172, 255))
    g.text((x0 + 4, fy + 34), f"{d * 100:.0f} cm", font=f, fill=(255, 214, 150, 255) if abs(d - DL) < 1e-3 else (200, 190, 172, 255))
    return Image.alpha_composite(base, ov).convert("RGB")


def floor_view(d, beam=(0.0, 0.0), shift_x=0.0):
    """top-down view of the floor (traced), the glass centre moved right by shift_x metres to leave room for the diagram"""
    g = Glass(R=6144)
    px = PX * 1.12
    E = g.wall(d, beam, centre=(g.W / 2 - shift_x, g.W / 2), px=px)
    del g
    from render import look
    return Image.fromarray(look(E))


def proof_still():
    """the glass alone, face-on: clear and blank; and a magnified cross-section of its real surface"""
    img = Image.new("RGB", (FW, FH), (6, 5, 4)); ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    s = 600; x0 = (FW - s) // 2 - 40; y0 = 520
    d.rectangle((x0, y0, x0 + s, y0 + s), fill=(190, 215, 225, 18), outline=(255, 240, 215, 230), width=4)
    d.line((x0 + 6, y0 + s + 6, x0 + s + 6, y0 + s + 6), fill=(255, 240, 215, 90), width=3)
    d.line((x0 + s + 6, y0 + 6, x0 + s + 6, y0 + s + 6), fill=(255, 240, 215, 90), width=3)
    col = 250                                                       # a cut down the middle of the glass (top to bottom)
    prof = HL[::-1, col] - HL[:, col].min()                         # top of the glass first
    py0, ph = 1270, 150                                              # plot: 10 cm wide, its height magnified
    pw = s
    mag = (ph / prof.max()) / (pw / WL)
    xs = x0 + np.arange(len(prof)) / (len(prof) - 1) * pw
    ys = py0 + ph - prof / prof.max() * ph
    d.line(list(zip(xs, ys)), fill=(255, 220, 160, 255), width=4)
    d.line((x0, py0 + ph + 4, x0 + pw, py0 + ph + 4), fill=(120, 110, 96, 255), width=2)
    sx = x0 + (col + 0.5) / HL.shape[0] * s                         # where the cut is, on the glass above
    d.line((sx, y0, sx, y0 + s), fill=(255, 220, 160, 140), width=2)
    f = ImageFont.truetype(MONO, 30)
    hmax = prof.max() * 1e3
    d.text((x0, py0 + ph + 14), f"cut through the glass · height ×{mag:.0f}", font=f, fill=(180, 170, 152, 255))
    d.text((x0 + pw + 14, py0 - 6), f"{hmax:.1f} mm", font=f, fill=(255, 214, 150, 255))
    O.check((x0 + pw + 14, py0 - 6, x0 + pw + 14 + d.textlength(f'{hmax:.1f} mm', font=f), py0 + 30))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    return img, mag, hmax


def main():
    shots = []
    # 1 hook
    im, info = water_still()
    im = O.block(Image.fromarray(im), [("Light through water", 62), ("makes these lines.", 62)], 262, 1.0)
    im.convert("RGB").save(OUT / "1_hook_water.png"); shots.append(("1_hook_water", info))
    # 2 setup
    im, an = setup_still()
    im = O.block(im, [("What if a glass were", 62), ("shaped on purpose?", 62)], 262, 1.0)
    print("anchors", {k: v.round() for k, v in an.items()})
    im = label(im, "lamp", (an["lamp"][0] + 110, max(an["lamp"][1] - 20, 430)), an["lamp"])
    im = label(im, "glass", (an["glass"][0] + 90, an["glass"][1] - 10), an["glass"])
    im = label(im, "floor", (an["floor"][0] + 110, min(an["floor"][1] + 20, 1480)), an["floor"])
    im.convert("RGB").save(OUT / "2_setup.png"); shots.append(("2_setup", an))
    # 3 reveal
    im = floor_view(DL, shift_x=0.012)
    im = O.block(im, [("…into a face.", 66)], 262, 1.0)
    im = diagram(im, DL)
    im.convert("RGB").save(OUT / "3_reveal.png"); shots.append(("3_reveal", None))
    # 4 proof: the glass is blank
    im, mag, hmax = proof_still()
    im = O.block(im, [("Nothing is printed on it.", 60), ("Only its shape:", 60), (f"bumps {O.RELIEF_MM:.1f} mm tall.", 60)], 262, 1.0)
    im.save(OUT / "4_blank_glass.png"); shots.append(("4_blank_glass", dict(mag=mag, row_relief_mm=hmax)))
    # 5 melt, with the diagram
    im = floor_view(0.35, shift_x=0.012)
    im = O.block(im, [("Lower the glass:", 58), ("the face softens away.", 58)], 262, 1.0)
    im = diagram(im, 0.35)
    im.convert("RGB").save(OUT / "5_melt.png"); shots.append(("5_melt", None))
    # 6 tilt, with the diagram
    im = floor_view(DL, (0.0, 6.0), shift_x=0.012)
    im = O.block(im, [("Tilt the lamp:", 58), ("the face moves with it.", 58)], 1240, 1.0)
    im = diagram(im, DL, (0.0, 6.0))
    im.convert("RGB").save(OUT / "6_tilt.png"); shots.append(("6_tilt", None))
    for s in shots: print(s)


if __name__ == "__main__":
    main()
