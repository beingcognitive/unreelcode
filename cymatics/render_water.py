"""Renders the Faraday dish (water.py) with torch: per-pixel camera rays, surface normals from the height
field, reflection of a warm ring light + faint softbox, Fresnel, caustics on the dish floor (forward-splatted
refracted light), meniscus at the rim, filmic tonemap, grain. v3: native vertical 1080x1920, no letterbox.  Output piped to ffmpeg."""
import sys, math, time, subprocess, numpy as np, torch
import torch.nn.functional as Fn
import water as Wt, timeline as T, overlay
DEV = Wt.DEV
W, H, SS = 1080, 1920, 1.5
RW, RH = int(W * SS), int(H * SS)
import shutil
FF = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
R0 = Wt.DISH / 2

def look(eye, tgt, fov, shift=(0, 0)):
    eye = torch.tensor(eye, dtype=torch.float32, device=DEV); tgt = torch.tensor(tgt, dtype=torch.float32, device=DEV)
    f = tgt - eye; f = f / f.norm()
    up = torch.tensor([0, 1.0, 0], device=DEV) if abs(float(f[2])) > 0.99 else torch.tensor([0, 0, 1.0], device=DEV)
    s = torch.linalg.cross(f, up); s = s / s.norm(); u = torch.linalg.cross(s, f)
    th = math.tan(math.radians(fov) / 2)
    ys = (torch.arange(RH, device=DEV) + 0.5) / RH * 2 - 1; xs = (torch.arange(RW, device=DEV) + 0.5) / RW * 2 - 1
    yy, xx = torch.meshgrid(-ys, xs, indexing='ij')
    d = f + s * (xx * th * RW / RH)[..., None] + u * (yy * th)[..., None]
    return eye, d / d.norm(dim=-1, keepdim=True)

def rot(eye, tgt, ang):
    a = math.radians(ang); c, s = math.cos(a), math.sin(a)
    r = lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])
    return r(eye), r(tgt)

def caustics(hx, hy):
    """bottom illumination: rays from overhead, refracted by the surface, travel DEPTH to the floor."""
    n = hx.shape[0]; dx = Wt.LBOX / n
    off = -(1 - 1 / 1.333) * Wt.DEPTH          # paraxial refraction displacement per unit slope
    ix = torch.arange(n, device=DEV, dtype=torch.float32)
    yy, xx = torch.meshgrid(ix, ix, indexing='ij')
    tx = (xx + off * hx / dx).round().long().clamp(0, n - 1); ty = (yy + off * hy / dx).round().long().clamp(0, n - 1)
    I = torch.zeros(n * n, device=DEV).index_add_(0, (ty * n + tx).view(-1), torch.ones(n * n, device=DEV))
    I = I.view(1, 1, n, n)
    k = torch.tensor([1, 4, 6, 4, 1.], device=DEV); k = (k[:, None] * k[None]) / 256
    I = Fn.conv2d(I, k[None, None], padding=2)
    return I[0, 0]

def env(r):
    """environment seen in reflection: warm ring light around the zenith + faint cool softbox."""
    th = torch.acos(r[..., 2].clamp(-1, 1))
    ring = torch.exp(-((th - math.radians(33)) / math.radians(4.5)) ** 2)
    ring2 = torch.exp(-((th - math.radians(52)) / math.radians(10)) ** 2)
    soft = torch.exp(-(th / math.radians(9)) ** 2)
    warm = torch.tensor([1.0, 0.72, 0.38], device=DEV); cool = torch.tensor([0.55, 0.7, 1.0], device=DEV)
    return ring[..., None] * warm * 30 + ring2[..., None] * cool * 2.0 + soft[..., None] * cool * 0.6

def aces(x): return ((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)).clamp(0, 1)

def render(u, cam, fi, amp_mm=0.22, breathe=1.0):
    eye, tgt, fov, ang, expo = cam
    eye, tgt = rot(eye, tgt, ang)
    o, d = look(eye, tgt, fov)
    h = u * amp_mm * 1e-3 * breathe
    dx = Wt.LBOX / u.shape[0]
    hy, hx = torch.gradient(h, spacing=dx)
    C = caustics(hx, hy)
    # ray / plane z=0
    t = -o[2] / d[..., 2]
    p = o[:2] + d[..., :2] * t[..., None]
    g = (p / (Wt.LBOX / 2))[None]                                  # grid_sample coords, x then y
    samp = lambda F: Fn.grid_sample(F[None, None], g, align_corners=False, padding_mode='border')[0, 0]
    sx, sy, sC = samp(hx), samp(hy), samp(C)
    N = torch.stack([-sx, -sy, torch.ones_like(sx)], -1); N = N / N.norm(dim=-1, keepdim=True)
    cosv = (-(d * N).sum(-1)).clamp(0, 1)
    rdir = d + 2 * cosv[..., None] * N
    fres = 0.02 + 0.98 * (1 - cosv) ** 5
    refl = env(rdir) * fres[..., None]
    floor = torch.tensor([0.010, 0.0085, 0.007], device=DEV) * (0.4 + 0.9 * sC)[..., None]
    floor = floor + torch.tensor([0.05, 0.032, 0.014], device=DEV) * (sC - 1).clamp(min=0)[..., None] ** 1.5 * 0.5
    col = refl + floor * (1 - fres[..., None])
    r = p.norm(dim=-1)
    inside = torch.sigmoid((R0 - r) / 0.00012)
    # meniscus: thin bright ring catching the ring light; outside: black glass table w/ dim rim reflection
    men = torch.exp(-((r - R0 + 0.0003) / 0.00035) ** 2)
    rim = torch.exp(-((r - R0 - 0.0016) / 0.0006) ** 2)
    out = torch.tensor([0.0015, 0.0014, 0.0013], device=DEV) * torch.exp(-(r - R0).clamp(min=0) / 0.02)[..., None]
    col = col * inside[..., None] + out * (1 - inside[..., None])
    col = col + men[..., None] * torch.tensor([1.0, 0.75, 0.45], device=DEV) * 0.8 + \
        rim[..., None] * torch.tensor([0.5, 0.42, 0.33], device=DEV) * 0.12
    col = col.permute(2, 0, 1)[None]
    col = Fn.avg_pool2d(Fn.interpolate(col, size=(H * 2, W * 2), mode='bilinear', align_corners=False), 2)[0]
    c = aces(col * expo)
    yy = (torch.arange(H, device=DEV) / H - 0.5)[:, None]; xx = (torch.arange(W, device=DEV) / W - 0.5)[None]
    c = c * (1 - 0.35 * (torch.sqrt((xx * 0.75) ** 2 + yy ** 2) * 1.35) ** 2.5)
    c = c ** (1 / 2.2)
    gseed = torch.Generator(device='cpu').manual_seed(fi)
    n = (torch.rand(H, W, generator=gseed) + torch.rand(H, W, generator=gseed) - 1).to(DEV)
    lum = (0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2])
    c = c + n * 0.035 * (0.35 + lum * (1 - lum) * 2)
    # v3.1: TPDF dither of one 8-bit step against banding in the smooth specular falloff
    d2 = (torch.rand(H, W, generator=gseed) + torch.rand(H, W, generator=gseed) - 1).to(DEV)
    c = c + d2 / 255.0
    return (c.clamp(0, 1) * 255).round().byte().permute(1, 2, 0).cpu().numpy()

def ease(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
M = 1.0  # metres
def cam_at(t):
    # v3: re-framed for a vertical frame (fov is vertical); the dish nearly fills the width
    if t < 28.0:      # W1: top-down, slow push-in + rotation
        u = (t - 23) / 5; z = 0.172 - 0.034 * ease(u)
        return ((0, -1e-5, z), (0, 0, 0), 38, -8 + 14 * u, 1.0)
    if t < 30.5:      # W2: oblique glide over the surface
        u = (t - 28) / 2.5
        return ((0.002 + 0.01 * u, -0.066, 0.058), (0.0, 0.002, 0), 54, 20 * u, 1.0)
    u = (t - 30.5) / 5  # W3: mandala, top-down, push to the centre
    z = 0.166 - 0.05 * ease(u)
    return ((0, -1e-5, z), (0, 0, 0), 38, 25 * u - 10, 1.0)

def breathe(t): return 0.81 + 0.19 * math.cos(2 * math.pi * 0.21 * (t - 23))

if __name__ == '__main__':
    ts = [float(a) for a in sys.argv[2:]] if sys.argv[1] == 'still' else None
    d = Wt.Dish(); d.t = 20.5
    if ts:
        from PIL import Image
        for tt in ts:
            d.run(tt); Image.fromarray(overlay.apply(render(d.u, cam_at(tt), int(tt * 30), breathe=breathe(tt)), tt, 'water')).save(f'dev/water_{tt:.2f}.png')
        sys.exit()
    ff = subprocess.Popen([FF, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                           '-r', '30', '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', '12',
                           '-pix_fmt', 'yuv420p', 'cache/seg_water.mp4'], stdin=subprocess.PIPE)
    # v3.1: bar 10 (sim 23.0-25.5, the still-flat dish) is cut, so the shot opens at 25.5 with cells forming.
    # The dish is still simulated through bar 10 off-screen, so its state at 25.5 is the real one.
    d.run(25.5); T0 = time.time()
    for i in range(300):
        t = 25.5 + i / 30
        d.run(t)
        ff.stdin.write(overlay.apply(render(d.u, cam_at(t), int(t * 30), breathe=breathe(t)), t, 'water').tobytes())
        if i % 30 == 0: print('water', i, round(time.time() - T0, 1), flush=True)
    ff.stdin.close(); ff.wait()
