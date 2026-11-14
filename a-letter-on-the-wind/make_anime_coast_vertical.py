# Vertical (9:16, for Reels / Shorts) 45-second cut of the seaside-headland anime short, built and rendered entirely by this script in Blender (EEVEE).
#
#   /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python make_anime_coast_vertical.py
#       -> anime-short-coast-vertical.mp4 (spawns worker Blender processes, then ffmpeg)
#   ... --python make_anime_coast_vertical.py -- --stills 2,8,12 outdir [scale]
#       -> outdir/s_XXXX.png test frames
#   ... --python make_anime_coast_vertical.py -- --range f0 f1 outdir     (internal worker mode)
#   ... --python make_anime_coast_vertical.py -- --audio out.wav          (soundtrack only)
#
# No models, textures, images or sound samples are loaded: every mesh, material and camera move is made here.
import bpy, sys, os, math, subprocess, shutil, time
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FPS, DUR, W, H = 24, 45.0, 1080, 1920
NF = int(DUR * FPS)
OUT = os.path.join(HERE, 'anime-short-coast-vertical.mp4')
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
NWORK = 4
SHOW_TITLE = False      # the posted film ends on end credits added afterwards; True draws the old on-screen title from 40.3 s

# ----------------------------------------------------------------------------- orchestrator
def orchestrate():
    tmp = os.path.join(HERE, '.coast-vertical-tmp')
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    t0 = time.time(); procs = []
    for i in range(NWORK):
        a, b = NF * i // NWORK, NF * (i + 1) // NWORK
        log = open(os.path.join(tmp, 'w%d.log' % i), 'w')
        procs.append(subprocess.Popen([bpy.app.binary_path, '-b', '--factory-startup', '--python', os.path.abspath(__file__),
                                       '--', '--range', str(a), str(b), tmp], stdout=log, stderr=subprocess.STDOUT))
    for p in procs: p.wait()        # a worker can exit non-zero on quit after writing every frame, so check the frames instead
    missing = [f for f in range(NF) if not os.path.exists(os.path.join(tmp, 'f%05d.png' % f))]
    if missing: raise SystemExit('%d frames missing (first %d), see logs in %s' % (len(missing), missing[0], tmp))
    audio = os.path.join(tmp, 'audio.wav'); make_audio(audio)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(tmp, 'f%05d.png')]
    cmd += ['-i', audio, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k']
    cmd += ['-c:v', 'libx264', '-crf', '18', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-t', str(DUR), '-movflags', '+faststart', OUT]
    subprocess.check_call(cmd)
    shutil.rmtree(tmp, ignore_errors=True)
    print('wrote %s in %.0f s' % (OUT, time.time() - t0))

def make_audio(path):
    """Synthesised soundtrack: soft pads, a music-box arpeggio, wind and sea. No samples are loaded."""
    import wave
    sr = 44100; n = int(DUR * sr); t = np.arange(n) / sr; r = np.random.default_rng(5); TAU = 2 * math.pi
    def env(a, b, fi, fo): return np.clip((t - a) / fi, 0, 1) * np.clip((b - t) / fo, 0, 1)
    def band(x, lo, hi):
        X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / sr); X *= (f > lo) / (1 + (f / hi) ** 4); y = np.fft.irfft(X, len(x)); return y / np.abs(y).max()
    def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
    chords = [(50, [62, 66, 69]), (47, [62, 66, 71]), (43, [62, 67, 71]), (45, [61, 64, 69])]          # D, Bm, G, A
    L = np.zeros(n); R = np.zeros(n); bar = 4.0; pat = [0, 1, 2, 3, 2, 1, 2, 3]
    for i in range(int(DUR / bar)):
        root, notes = chords[i % 4] if i < int(DUR / bar) - 1 else chords[0]
        a = i * bar; e = env(a - 0.3, a + bar + 0.6, 1.2, 1.5); arp = notes + [notes[0] + 12]
        for j, m in enumerate(arp):
            f = hz(m)
            L += 0.05 * e * np.sin(TAU * f * 1.002 * t + j) + 0.015 * e * np.sin(TAU * f * 2 * t)
            R += 0.05 * e * np.sin(TAU * f * 0.998 * t + 2 * j) + 0.015 * e * np.sin(TAU * f * 2.003 * t)
        b = 0.09 * e * np.sin(TAU * hz(root) * t); L += b; R += b
        for q in range(8):
            ts = a + q * 0.5
            if ts < 2.0 or ts > DUR - 5: continue
            fly = 15.0 <= ts < 40.0
            f = hz(arp[pat[q]] + 12 + (12 if fly and q % 2 else 0)); k0 = int(ts * sr); m_ = min(n - k0, int(1.6 * sr)); tt = np.arange(m_) / sr
            s = (0.07 if fly else 0.042) * np.exp(-tt * 3.2) * (np.sin(TAU * f * tt) + 0.3 * np.sin(TAU * 2 * f * tt) * np.exp(-tt * 6)) * np.minimum(tt / 0.004, 1)
            pan = 0.5 + 0.3 * math.sin(q * 1.7 + i)
            L[k0:k0 + m_] += s * (1 - pan); R[k0:k0 + m_] += s * pan
    wind = band(r.normal(size=n), 150, 900); sea = band(r.normal(size=n), 60, 500)
    wamp = 0.05 + 0.12 * np.clip((t - 14.3) / 2, 0, 1) * np.clip((44.5 - t) / 3, 0, 1) * (0.7 + 0.3 * np.sin(TAU * 0.13 * t)) + 0.35 * np.exp(-((t - 14.45) / 0.28) ** 2)
    samp = 0.06 * (0.55 + 0.45 * np.sin(TAU * t / 7.5)) ** 2 * (1 - 0.6 * np.clip((t - 15.0) / 3, 0, 1) * np.clip((44.5 - t) / 3, 0, 1))
    L += wind * wamp + sea * samp; R += np.roll(wind, sr // 37) * wamp + np.roll(sea, sr // 23) * samp
    out = np.tanh(np.stack([L, R], 1) * (np.clip(t / 1.5, 0, 1) * np.clip((DUR - t) / 2.5, 0, 1))[:, None] * 1.4); out *= 0.7 / np.abs(out).max()
    w = wave.open(path, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((out * 32767).astype('<i2').tobytes()); w.close()

if not ARGS:
    orchestrate(); sys.exit(0)
if ARGS[0] == '--audio':
    make_audio(ARGS[1]); sys.exit(0)

# ----------------------------------------------------------------------------- small maths
rng = np.random.default_rng(11)
PI = math.pi
def nrmz(v): v = np.asarray(v, float); return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)
def lerp(a, b, t): return a + (b - a) * t
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ss(a, b, x):
    t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t)
def V3(*a): return np.array(a, float)
def lin(c): return tuple(float(x) ** 2.2 for x in c)     # colours below are written as they should look on screen

# ----------------------------------------------------------------------------- mesh helpers
def lathe(prof, seg=20, sx=1.0, sy=1.0):
    prof = np.array(prof, float); prof[:, 0] = np.maximum(prof[:, 0], 1e-3); n = len(prof)
    a = np.linspace(0, 2 * PI, seg, endpoint=False)
    V = np.stack([np.outer(prof[:, 0], np.cos(a)) * sx, np.outer(prof[:, 0], np.sin(a)) * sy,
                  np.repeat(prof[:, 1][:, None], seg, 1)], -1).reshape(-1, 3)
    i = np.arange(n - 1)[:, None]; j = np.arange(seg)[None, :]; j2 = (j + 1) % seg
    F = np.stack([i * seg + j, i * seg + j2, (i + 1) * seg + j2, (i + 1) * seg + j], -1).reshape(-1, 4)
    return V, F
def ellipsoid(c, r, seg=18, rings=10):
    ph = np.linspace(0.03, PI - 0.03, rings)
    V, F = lathe(np.stack([np.sin(ph), -np.cos(ph)], 1), seg)
    return V * np.asarray(r, float) + np.asarray(c, float), F
def tube(pts, rad, seg=8):
    pts = np.array(pts, float); n = len(pts); rad = np.broadcast_to(np.asarray(rad, float), (n,))
    T = nrmz(np.gradient(pts, axis=0))
    U = np.cross(T, [0, 0, 1.0]); bad = np.linalg.norm(U, axis=1) < 1e-3; U[bad] = np.cross(T[bad], [1.0, 0, 0]); U = nrmz(U)
    Vv = np.cross(T, U); a = np.linspace(0, 2 * PI, seg, endpoint=False)
    V = pts[:, None, :] + rad[:, None, None] * (np.cos(a)[None, :, None] * U[:, None, :] + np.sin(a)[None, :, None] * Vv[:, None, :])
    i = np.arange(n - 1)[:, None]; j = np.arange(seg)[None, :]; j2 = (j + 1) % seg
    F = np.stack([i * seg + j, i * seg + j2, (i + 1) * seg + j2, (i + 1) * seg + j], -1).reshape(-1, 4)
    return V.reshape(-1, 3), F
def xform(V, M): return V @ np.array(M.to_3x3()).T + np.array(M.translation)

class Geo:
    def __init__(s): s.V = []; s.F = {}; s.n = 0; s.nrm = []; s.var = []
    def add(s, V, F, nrm=None, var=None):
        V = np.asarray(V, float); F = np.asarray(F)
        s.F.setdefault(F.shape[1], []).append(F + s.n); s.V.append(V); s.n += len(V)
        s.nrm.append(nrm if nrm is not None else np.tile([0, 0, 1.0], (len(V), 1)))
        s.var.append(var if var is not None else np.full(len(V), 0.5))
        return s
    def build(s, name, mat, smooth=True, shadow=True):
        me = bpy.data.meshes.new(name); V = np.concatenate(s.V)
        loops = []; starts = []; off = 0
        for k, fl in s.F.items():
            F = np.concatenate(fl); loops.append(F.ravel()); starts.append(off + np.arange(len(F)) * k); off += F.size
        loops = np.concatenate(loops); starts = np.concatenate(starts)
        me.vertices.add(len(V)); me.vertices.foreach_set('co', V.astype(np.float32).ravel())
        me.loops.add(len(loops)); me.loops.foreach_set('vertex_index', loops.astype(np.int32))
        me.polygons.add(len(starts)); me.polygons.foreach_set('loop_start', starts.astype(np.int32))
        me.update(calc_edges=True)
        if smooth: me.polygons.foreach_set('use_smooth', np.ones(len(starts), bool))
        a = me.attributes.new('nrm', 'FLOAT_VECTOR', 'POINT'); a.data.foreach_set('vector', np.concatenate(s.nrm).astype(np.float32).ravel())
        a = me.attributes.new('var', 'FLOAT', 'POINT'); a.data.foreach_set('value', np.concatenate(s.var).astype(np.float32))
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
        ob.visible_shadow = shadow
        return ob

def leaves(centers, radii, n_per, size, up_bias=0.35, flat=0.7, droop=0.0):
    """Brush-dab leaves (hexagons) on the shells of ellipsoid clumps; 'nrm' is the clump normal so a clump shades as one mass."""
    centers = np.asarray(centers, float).reshape(-1, 3); radii = np.broadcast_to(np.asarray(radii, float), centers.shape)
    K = len(centers); N = K * n_per
    c = np.repeat(centers, n_per, 0); r = np.repeat(radii, n_per, 0)
    d = rng.normal(size=(N, 3)); d[:, 2] = d[:, 2] * 0.85 + 0.2; d = nrmz(d)
    p = c + d * r * rng.uniform(0.72, 1.05, (N, 1))
    nrm = nrmz(d + [0, 0, up_bias])
    ln = nrmz(d + rng.normal(size=(N, 3)) * flat)
    u = nrmz(np.cross(ln, [0, 0, 1.0]) + 1e-4); v = np.cross(ln, u)
    ang = np.linspace(0, 2 * PI, 6, endpoint=False)[None, :] + rng.uniform(0, 1, (N, 1))
    rad = size * rng.uniform(0.6, 1.15, (N, 6)) * rng.uniform(0.7, 1.3, (N, 1))
    sv = rng.uniform(0.45, 0.9, (N, 1))
    V = p[:, None, :] + (np.cos(ang) * rad)[..., None] * u[:, None, :] + (np.sin(ang) * rad * sv)[..., None] * v[:, None, :]
    V[:, :, 2] -= droop * rng.uniform(0, 1, (N, 1))
    var = 0.55 * rng.uniform(0, 1, (N, 1)) + 0.45 * np.repeat(rng.uniform(0, 1, (K, 1)), n_per, 0)
    return V.reshape(-1, 3), np.arange(N * 6).reshape(N, 6), np.repeat(nrm, 6, 0), np.repeat(var, 6, 1).ravel()

# ----------------------------------------------------------------------------- material helpers
class NT:
    def __init__(s, tree): s.t = tree; s.N = tree.nodes; s.L = tree.links
    def node(s, typ, **kw):
        n = s.N.new(typ)
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def put(s, inp, v):
        if isinstance(v, bpy.types.NodeSocket): s.L.new(v, inp)
        elif isinstance(v, (tuple, list)) and len(v) == 3 and inp.type == 'RGBA': inp.default_value = (*v, 1)
        else: inp.default_value = v
    def rgb(s, c, raw=False):
        if isinstance(c, bpy.types.NodeSocket): return c
        if not raw and max(c) <= 1.0: c = lin(c)
        n = s.node('ShaderNodeRGB'); n.outputs[0].default_value = (*c, 1); return n.outputs[0]
    def math(s, op, a, b=None, c=None, cl=False):
        n = s.node('ShaderNodeMath', operation=op); n.use_clamp = cl
        for i, v in enumerate((a, b, c)):
            if v is not None: s.put(n.inputs[i], v)
        return n.outputs[0]
    def mix(s, f, a, b, bt='MIX'):
        n = s.node('ShaderNodeMix'); n.data_type = 'RGBA'; n.blend_type = bt
        s.put(n.inputs[0], f); s.put(n.inputs[6], a); s.put(n.inputs[7], b); return n.outputs[2]
    def scale(s, col, k):
        n = s.node('ShaderNodeVectorMath', operation='SCALE'); s.put(n.inputs[0], col); s.put(n.inputs[3], k); return n.outputs[0]
    def sstep(s, x, e0, e1):
        n = s.node('ShaderNodeMapRange'); n.interpolation_type = 'SMOOTHSTEP'
        s.put(n.inputs[0], x); s.put(n.inputs[1], e0); s.put(n.inputs[2], e1); return n.outputs[0]
    def noise(s, vec, scale, detail=3.0, rough=0.55):
        n = s.node('ShaderNodeTexNoise'); s.put(n.inputs['Vector'], vec); n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail; n.inputs['Roughness'].default_value = rough
        return n.outputs[0], n.outputs[1]
    def sepz(s, vec):
        n = s.node('ShaderNodeSeparateXYZ'); s.put(n.inputs[0], vec); return n.outputs

GLOB = None; GV = {}
def make_globals():
    """One shared node group holding the per-frame values every material reads (time of day, fog, ...)."""
    global GLOB
    GLOB = bpy.data.node_groups.new('Globals', 'ShaderNodeTree'); nt = NT(GLOB); out = nt.node('NodeGroupOutput')
    for name, typ in (('L0', 'F'), ('gain', 'F'), ('fogd', 'F'), ('fogc', 'C'), ('titlea', 'F'), ('cloudk', 'F'), ('time', 'F'), ('lamp', 'F'), ('win', 'F'), ('seaA', 'C'), ('seaB', 'C'), ('seaC', 'C'), ('glitc', 'C'), ('foamc', 'C')):
        GLOB.interface.new_socket(name=name, in_out='OUTPUT', socket_type='NodeSocketFloat' if typ == 'F' else 'NodeSocketColor')
        n = nt.node('ShaderNodeValue' if typ == 'F' else 'ShaderNodeRGB'); GV[name] = n.outputs[0]
        nt.L.new(n.outputs[0], out.inputs[name])
def setg(name, v):
    GV[name].default_value = (*v, 1) if isinstance(v, (tuple, list, np.ndarray)) else v

def fogged(nt, g, col, pos):
    dist = nt.node('ShaderNodeCameraData').outputs['View Distance']
    z = nt.sepz(pos)[2]
    hf = nt.math('EXPONENT', nt.math('MULTIPLY', nt.math('MAXIMUM', nt.math('SUBTRACT', z, 7.0), 0.0), -0.045))
    f = nt.math('SUBTRACT', 1.0, nt.math('EXPONENT', nt.math('MULTIPLY', nt.math('MULTIPLY', dist, g.outputs['fogd']), nt.math('MULTIPLY', hf, -1.0))))
    return nt.mix(nt.math('MULTIPLY', f, 0.97), col, g.outputs['fogc'])

def toon(name, sh, mid, li, th=(0.34, 0.64), soft=0.012, namp=0.22, nscale=2.0, nvec=(1, 1, 1), nrm=False, var=0.0,
         edge=0.0, hook=None, chroma=0.8, glow=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = NT(m.node_tree); nt.N.clear()
    g = nt.node('ShaderNodeGroup'); g.node_tree = GLOB
    geo = nt.node('ShaderNodeNewGeometry'); pos = geo.outputs['Position']
    dif = nt.node('ShaderNodeBsdfDiffuse'); dif.inputs['Color'].default_value = (1, 1, 1, 1)
    if nrm:
        at = nt.node('ShaderNodeAttribute'); at.attribute_name = 'nrm'; nt.L.new(at.outputs['Vector'], dif.inputs['Normal'])
    s2r = nt.node('ShaderNodeShaderToRGB'); nt.L.new(dif.outputs[0], s2r.inputs[0])
    bw = nt.node('ShaderNodeRGBToBW'); nt.L.new(s2r.outputs[0], bw.inputs[0]); lum = bw.outputs[0]
    lumN = nt.math('DIVIDE', lum, g.outputs['L0'])
    mp = nt.node('ShaderNodeMapping'); mp.inputs['Scale'].default_value = nvec; nt.L.new(pos, mp.inputs['Vector'])
    nf, _ = nt.noise(mp.outputs[0], nscale)
    x = nt.math('ADD', lumN, nt.math('MULTIPLY', nt.math('SUBTRACT', nf, 0.5), namp * 0.4))
    av = None
    if var:
        a2 = nt.node('ShaderNodeAttribute'); a2.attribute_name = 'var'; av = a2.outputs['Fac']
        x = nt.math('ADD', x, nt.math('MULTIPLY', nt.math('SUBTRACT', av, 0.5), var))
    cs = {'sh': nt.rgb(sh), 'mid': nt.rgb(mid), 'li': nt.rgb(li)}
    if hook: hook(nt, cs, pos, geo)
    col = nt.mix(nt.sstep(x, th[0] - soft, th[0] + soft), cs['sh'], cs['mid'])
    col = nt.mix(nt.sstep(x, th[1] - soft, th[1] + soft), col, cs['li'])
    nf2, _ = nt.noise(pos, nscale * 0.35, detail=2.0)
    col = nt.scale(col, nt.math('ADD', 0.94, nt.math('MULTIPLY', nf2, 0.12)))
    if av is not None:
        col = nt.mix(1.0, col, nt.mix(av, nt.rgb((0.72, 0.84, 0.82), True), nt.rgb((1.18, 1.12, 0.80), True)), 'MULTIPLY')
    if edge:
        lw = nt.node('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.35
        col = nt.mix(nt.math('MULTIPLY', nt.sstep(lw.outputs['Facing'], 0.5, 0.82), edge), col, nt.scale(cs['sh'], 0.42))
    ch = nt.scale(s2r.outputs[0], nt.math('DIVIDE', 1.0, nt.math('MAXIMUM', lum, 1e-3)))
    col = nt.mix(chroma, col, ch, 'MULTIPLY')
    col = nt.scale(col, g.outputs['gain'])
    if glow: col = glow(nt, g, col)
    col = fogged(nt, g, col, pos)
    em = nt.node('ShaderNodeEmission'); nt.L.new(col, em.inputs['Color'])
    out = nt.node('ShaderNodeOutputMaterial'); nt.L.new(em.outputs[0], out.inputs['Surface'])
    return m

def glowmat(name, build):
    """Unlit see-through material (light shafts, mist, title): build(nt, g) returns (colour socket, alpha socket)."""
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = NT(m.node_tree); nt.N.clear()
    g = nt.node('ShaderNodeGroup'); g.node_tree = GLOB
    col, alpha = build(nt, g)
    em = nt.node('ShaderNodeEmission'); nt.put(em.inputs['Color'], col)
    tr = nt.node('ShaderNodeBsdfTransparent'); mx = nt.node('ShaderNodeMixShader')
    nt.put(mx.inputs[0], alpha); nt.L.new(tr.outputs[0], mx.inputs[1]); nt.L.new(em.outputs[0], mx.inputs[2])
    out = nt.node('ShaderNodeOutputMaterial'); nt.L.new(mx.outputs[0], out.inputs['Surface'])
    m.surface_render_method = 'BLENDED'
    return m

# ----------------------------------------------------------------------------- scene set-up
S = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
S.render.engine = 'BLENDER_EEVEE'
S.render.resolution_x, S.render.resolution_y, S.render.fps = W, H, FPS
S.render.image_settings.file_format = 'PNG'; S.render.image_settings.compression = 20
S.view_settings.view_transform = 'Standard'
S.eevee.taa_render_samples = 20
S.eevee.use_shadows = True
S.eevee.shadow_pool_size = '1024'
S.render.film_transparent = False
make_globals()

SUN = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); S.collection.objects.link(SUN)
SUN.data.angle = math.radians(2.5)
try: SUN.data.shadow_cascade_max_distance = 160.0
except Exception: pass
CAM = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); S.collection.objects.link(CAM); S.camera = CAM
CAM.data.clip_start = 0.05; CAM.data.clip_end = 2500

# world: painted sky for the camera, flat ambient colour for lighting
WD = bpy.data.worlds.new('w'); S.world = WD; WD.use_nodes = True; wn = NT(WD.node_tree); wn.N.clear()
WV = {}
def wval(name, col=None):
    n = wn.node('ShaderNodeRGB' if col else 'ShaderNodeValue'); WV[name] = n.outputs[0]; return n.outputs[0]
def setw(name, v): WV[name].default_value = (*v, 1) if isinstance(v, (tuple, list, np.ndarray)) else v
wdir = wn.node('ShaderNodeTexCoord').outputs['Generated']
wz = wn.sepz(wdir)[2]
sky = wn.mix(wn.sstep(wz, -0.03, 0.55), wval('horizon', 1), wval('zenith', 1))
sdn = wn.node('ShaderNodeCombineXYZ'); WSUN = sdn
dp = wn.node('ShaderNodeVectorMath', operation='DOT_PRODUCT'); wn.L.new(wdir, dp.inputs[0]); wn.L.new(sdn.outputs[0], dp.inputs[1])
sd = wn.math('MAXIMUM', dp.outputs['Value'], 0.0)
sky = wn.mix(wn.math('MULTIPLY', wn.math('POWER', sd, 10.0), wval('glowa')), sky, wval('glowc', 1), 'ADD')
cmp_ = wn.node('ShaderNodeMapping'); cmp_.inputs['Scale'].default_value = (2.0, 2.0, 7.0); wn.L.new(wdir, cmp_.inputs['Vector']); WCLOUD = cmp_
cf, _ = wn.noise(cmp_.outputs[0], 1.6, detail=5.0, rough=0.6)
sky = wn.mix(wn.math('MULTIPLY', wn.math('MULTIPLY', wn.sstep(cf, 0.50, 0.66), wn.sstep(wz, 0.0, 0.22)), wval('clouda')), sky, wval('cloudc', 1))
sky = wn.mix(wn.math('MULTIPLY', wn.sstep(sd, 0.9990, 0.9996), wval('disca')), sky, wval('discc', 1), 'ADD')
vs = wn.node('ShaderNodeTexVoronoi'); wn.L.new(wdir, vs.inputs['Vector']); vs.inputs['Scale'].default_value = 70.0
vb = wn.node('ShaderNodeRGBToBW'); wn.L.new(vs.outputs['Color'], vb.inputs[0])
star = wn.math('MULTIPLY', wn.math('SUBTRACT', 1.0, wn.sstep(vs.outputs['Distance'], 0.03, 0.085)), wn.math('MULTIPLY', wn.sstep(vb.outputs[0], 0.35, 0.9), wval('stara')))
sky = wn.mix(wn.math('MULTIPLY', star, wn.sstep(wz, 0.05, 0.3)), sky, wn.rgb((2.2, 2.3, 2.6)), 'ADD')
lp = wn.node('ShaderNodeLightPath')
bg = wn.node('ShaderNodeBackground'); wn.L.new(wn.mix(lp.outputs['Is Camera Ray'], wval('amb', 1), sky), bg.inputs['Color'])
wn.L.new(bg.outputs[0], wn.node('ShaderNodeOutputWorld').inputs['Surface'])

# compositor: painterly filter, bloom, flash and fade
CT = bpy.data.node_groups.new('Comp', 'CompositorNodeTree'); S.compositing_node_group = CT
CT.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
cn = NT(CT)
rl = cn.node('CompositorNodeRLayers')
KSIZE = 2.4          # only a light smoothing now: the look comes from flat cel bands
ku = cn.node('CompositorNodeKuwahara'); cn.L.new(rl.outputs['Image'], ku.inputs['Image'])
for nm, v in (('Type', 'Anisotropic'), ('Size', KSIZE), ('Uniformity', 3), ('Sharpness', 0.6), ('Eccentricity', 1.2)):
    try: ku.inputs[nm].default_value = v
    except Exception as e: print('kuwahara', nm, e)
KUW = ku
glr = cn.node('CompositorNodeGlare'); cn.L.new(ku.outputs['Image'], glr.inputs['Image'])
for nm, v in (('Type', 'Bloom'), ('Threshold', 0.85), ('Strength', 0.55), ('Size', 0.55), ('Saturation', 1.0)):
    try: glr.inputs[nm].default_value = v
    except Exception as e: print('glare', nm, e)
exn = cn.node('CompositorNodeExposure'); cn.L.new(glr.outputs['Image'], exn.inputs['Image']); CEXP = exn.inputs['Exposure']
fd = cn.node('ShaderNodeMix'); fd.data_type = 'RGBA'; cn.L.new(exn.outputs['Image'], fd.inputs[6]); fd.inputs[7].default_value = (0, 0, 0, 1); CFADE = fd.inputs[0]; CFADEC = fd.inputs[7]
cn.L.new(fd.outputs[2], cn.node('NodeGroupOutput').inputs['Image'])

# ----------------------------------------------------------------------------- layout: a headland above the sea
GX, GY = 0.0, 9.5                                   # girl, near the cliff edge
LX, LY = 24.0, 40.0                                 # lighthouse on the tip of the promontory
CX, CY, CROT = -10.0, 4.0, math.radians(25)         # cottage
PA, PB, PR = V3(10.0, 6.0), V3(24.0, 40.0), 7.5     # promontory (a tapering capsule)
STACKS = [(41.0, 54.0, 3.2, 9.0), (47.0, 63.0, 2.2, 6.0), (-34.0, 44.0, 3.8, 11.0), (-41.0, 50.0, 2.0, 5.0),
          (8.0, 128.0, 4.5, 13.0), (16.0, 140.0, 2.5, 7.0), (-34.0, 158.0, 5.0, 16.0), (-26.0, 172.0, 2.2, 6.0), (22.0, 190.0, 3.0, 8.0), (-44.0, 214.0, 3.4, 10.0)]
def coast_d(x, y):
    """Rough distance past the coastline in metres (negative on land)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    d1 = y - (11.0 + 3.0 * np.sin(0.07 * x + 1.0) + 2.0 * np.sin(0.19 * x))
    ab = PB - PA
    u = np.clip(((x - PA[0]) * ab[0] + (y - PA[1]) * ab[1]) / float(ab @ ab), 0, 1)
    d2 = np.hypot(x - (PA[0] + u * ab[0]), y - (PA[1] + u * ab[1])) - (PR - 1.5 * u)
    return np.minimum(d1, d2)
def path_x(y): return 0.6 + 0.8 * np.sin(np.asarray(y, float) * 0.12)
def plateau(x, y):
    h = 9.0 + 0.15 * np.clip(12.0 - y, 0, 80) + 0.22 * np.sin(x * 0.21 + 1.3) * np.cos(y * 0.17) + 0.14 * np.sin(x * 0.07 - y * 0.11)
    h = h + 0.5 * np.exp(-((x - GX) ** 2 + (y - GY) ** 2) / (2 * 2.3 ** 2)) + 2.2 * np.exp(-((x - LX) ** 2 + (y - LY) ** 2) / (2 * 6.0 ** 2))
    k = np.clip((-y - 50.0) / 150.0, 0, 1)
    return h + 22.0 * k * k * (3 - 2 * k) * (0.55 + 0.45 * np.sin(x * 0.017 + 0.6))
def ground(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    d = coast_d(x, y) + 0.7 * np.sin(x * 0.9 + y * 0.45) + 0.5 * np.sin(y * 1.3 - x * 0.6)
    k = np.clip((d + 1.0) / 5.5, 0, 1); k = k * k * (3 - 2 * k)
    return plateau(x, y) * (1 - k) - 4.0 * k
def in_cottage(x, y, grow=0.6):
    dx, dy = x - CX, y - CY; c, s = math.cos(-CROT), math.sin(-CROT)
    return (np.abs(dx * c - dy * s) < 3.4 + grow) & (np.abs(dx * s + dy * c) < 2.4 + grow)
hG = float(ground(GX, GY))
LZ = float(ground(LX, LY)) - 0.3
LAMPPOS = V3(LX, LY, LZ + 17.0)
CAM.data.clip_end = 9000

sn = NT(GLOB); SUNV = sn.node('ShaderNodeCombineXYZ')
GLOB.interface.new_socket(name='sund', in_out='OUTPUT', socket_type='NodeSocketVector')
sn.L.new(SUNV.outputs[0], [n for n in GLOB.nodes if n.type == 'GROUP_OUTPUT'][0].inputs['sund'])

# ----------------------------------------------------------------------------- materials
def ground_hook(nt, cs, pos, geo):
    nz = nt.sepz(geo.outputs['Normal'])[2]; nf, _ = nt.noise(pos, 0.5)
    rock = nt.math('SUBTRACT', 1.0, nt.sstep(nt.math('ADD', nz, nt.math('MULTIPLY', nt.math('SUBTRACT', nf, 0.5), 0.3)), 0.70, 0.84))
    at = nt.node('ShaderNodeAttribute'); at.attribute_name = 'var'
    path = nt.sstep(nt.math('ADD', at.outputs['Fac'], nt.math('MULTIPLY', nt.math('SUBTRACT', nf, 0.5), 0.5)), 0.4, 0.6)
    mp = nt.node('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (0.12, 0.12, 1.6); nt.L.new(pos, mp.inputs['Vector'])
    ns, _ = nt.noise(mp.outputs[0], 1.0); band = nt.sstep(ns, 0.42, 0.58)
    for k, dirt, r1, r2 in (('sh', (0.42, 0.32, 0.26), (0.36, 0.27, 0.33), (0.45, 0.33, 0.30)),
                            ('mid', (0.80, 0.68, 0.48), (0.74, 0.60, 0.50), (0.86, 0.72, 0.52)),
                            ('li', (0.97, 0.90, 0.68), (0.97, 0.88, 0.74), (1.0, 0.95, 0.80))):
        cs[k] = nt.mix(rock, nt.mix(path, cs[k], nt.rgb(dirt)), nt.mix(band, nt.rgb(r1), nt.rgb(r2)))

M = {}
M['ground'] = toon('ground', (0.16, 0.30, 0.20), (0.44, 0.62, 0.25), (0.80, 0.84, 0.38), namp=0.3, nscale=0.9, hook=ground_hook)
M['grass'] = toon('grass', (0.10, 0.24, 0.16), (0.40, 0.60, 0.24), (0.84, 0.88, 0.42), nrm=True, var=0.45, namp=0.25, nscale=0.9)
M['pine'] = toon('pine', (0.05, 0.17, 0.15), (0.14, 0.36, 0.22), (0.42, 0.60, 0.28), nrm=True, var=0.5, namp=0.3, nscale=0.5)
M['bush'] = toon('bush', (0.10, 0.26, 0.14), (0.30, 0.52, 0.20), (0.66, 0.78, 0.32), nrm=True, var=0.5, namp=0.3, nscale=0.6)
M['bark'] = toon('bark', (0.22, 0.12, 0.11), (0.50, 0.30, 0.22), (0.80, 0.56, 0.40), namp=0.5, nscale=5.0, nvec=(1, 1, 0.1), edge=0.6, chroma=0.5)
M['stone'] = toon('stone', (0.36, 0.33, 0.40), (0.66, 0.62, 0.60), (0.94, 0.90, 0.80), namp=0.3, nscale=2.5, edge=0.5)
M['rock'] = toon('rock', (0.36, 0.27, 0.33), (0.78, 0.64, 0.50), (0.98, 0.90, 0.74), namp=0.4, nscale=0.4, edge=0.3)
M['plaster'] = toon('plaster', (0.60, 0.66, 0.86), (0.95, 0.94, 0.90), (1.0, 1.0, 0.96), namp=0.12, nscale=1.5, th=(0.3, 0.6))
M['roof'] = toon('roof', (0.50, 0.20, 0.16), (0.86, 0.42, 0.24), (1.0, 0.66, 0.38), namp=0.35, nscale=3.0, nvec=(0.3, 3, 3))
M['red'] = toon('red', (0.50, 0.12, 0.14), (0.86, 0.22, 0.18), (1.0, 0.45, 0.32), namp=0.12)
M['wood'] = toon('wood', (0.26, 0.21, 0.20), (0.52, 0.44, 0.38), (0.80, 0.72, 0.60), namp=0.3, nscale=6.0, nvec=(1, 1, 0.15))
M['sail'] = toon('sail', (0.70, 0.68, 0.80), (0.98, 0.95, 0.86), (1.0, 1.0, 0.95), namp=0.08, th=(0.25, 0.55))
M['cloud'] = toon('cloud', (0.72, 0.80, 0.96), (0.92, 0.95, 1.0), (1.0, 1.0, 0.98), th=(0.27, 0.52), soft=0.015, namp=0.08, nscale=0.012, chroma=1.0,
                  glow=lambda nt, g, col: nt.scale(col, g.outputs['cloudk']))
M['fl_r'] = toon('fl_r', (0.60, 0.10, 0.10), (0.92, 0.22, 0.16), (1.0, 0.45, 0.30), nrm=True, namp=0.1)
M['fl_w'] = toon('fl_w', (0.72, 0.76, 0.90), (0.98, 0.98, 0.95), (1.0, 1.0, 1.0), nrm=True, namp=0.1)
M['fl_y'] = toon('fl_y', (0.70, 0.50, 0.10), (0.98, 0.80, 0.20), (1.0, 0.95, 0.50), nrm=True, namp=0.1)
M['dark'] = toon('dark', (0.06, 0.05, 0.08), (0.10, 0.08, 0.12), (0.16, 0.13, 0.16), namp=0.1)
M['skin'] = toon('skin', (0.80, 0.55, 0.46), (0.97, 0.78, 0.64), (1.0, 0.90, 0.78), namp=0.05, th=(0.3, 0.7), edge=0.25)
M['dress'] = toon('dress', (0.58, 0.64, 0.82), (0.90, 0.92, 0.96), (1.0, 1.0, 0.97), namp=0.1, th=(0.3, 0.62), edge=0.3)
M['hair'] = toon('hair', (0.09, 0.06, 0.06), (0.21, 0.13, 0.10), (0.44, 0.29, 0.20), namp=0.25, nscale=9.0, nvec=(1, 1, 0.2), edge=0.3)
M['straw'] = toon('straw', (0.55, 0.42, 0.22), (0.86, 0.71, 0.38), (1.0, 0.92, 0.58), namp=0.2, nscale=12.0, edge=0.3)
M['blue'] = toon('blue', (0.10, 0.20, 0.50), (0.18, 0.38, 0.78), (0.35, 0.60, 0.95), namp=0.05)
M['paper'] = toon('paper', (0.72, 0.78, 0.95), (0.97, 0.97, 1.0), (1.0, 1.0, 1.0), namp=0.0, th=(0.2, 0.5), chroma=0.5)
M['window'] = toon('window', (0.08, 0.10, 0.18), (0.16, 0.22, 0.34), (0.40, 0.52, 0.66), namp=0.1,
                   glow=lambda nt, g, col: nt.mix(g.outputs['win'], col, nt.rgb((3.0, 2.0, 0.8))))
M['lamp'] = toon('lamp', (0.30, 0.38, 0.44), (0.55, 0.66, 0.70), (0.86, 0.94, 0.94), namp=0.1,
                 glow=lambda nt, g, col: nt.mix(g.outputs['lamp'], col, nt.rgb((3.6, 3.1, 1.6))))
M['title'] = glowmat('title', lambda nt, g: (nt.rgb((0.05, 0.13, 0.38)), g.outputs['titlea']))
M['titlesh'] = glowmat('titlesh', lambda nt, g: (nt.rgb((1.0, 1.0, 0.97)), g.outputs['titlea']))

def sea_mat():
    """Flat painted sea: drifting colour bands, brush dabs, sun/moon glitter and foam along the rocks."""
    m = bpy.data.materials.new('sea'); m.use_nodes = True; nt = NT(m.node_tree); nt.N.clear()
    g = nt.node('ShaderNodeGroup'); g.node_tree = GLOB
    geo = nt.node('ShaderNodeNewGeometry'); pos = geo.outputs['Position']
    at = nt.node('ShaderNodeAttribute'); at.attribute_name = 'var'; shore = at.outputs['Fac']
    tm = g.outputs['time']
    def moving(scale, vel):
        mu = nt.node('ShaderNodeVectorMath', operation='MULTIPLY'); nt.L.new(pos, mu.inputs[0]); mu.inputs[1].default_value = scale
        c = nt.node('ShaderNodeCombineXYZ')
        for i, v in enumerate(vel): nt.put(c.inputs[i], nt.math('MULTIPLY', tm, v))
        ad = nt.node('ShaderNodeVectorMath', operation='ADD'); nt.L.new(mu.outputs[0], ad.inputs[0]); nt.L.new(c.outputs[0], ad.inputs[1])
        return ad.outputs[0]
    n1, _ = nt.noise(moving((0.035, 0.14, 1.0), (0.02, 0.05, 0.03)), 1.0, detail=3.0)
    col = nt.mix(nt.sstep(n1, 0.44, 0.56), g.outputs['seaA'], g.outputs['seaB'])
    n2, _ = nt.noise(moving((0.25, 0.9, 1.0), (0.05, 0.25, 0.12)), 1.0, detail=2.0)
    col = nt.mix(nt.math('MULTIPLY', nt.sstep(n2, 0.66, 0.72), 0.55), col, nt.scale(g.outputs['seaB'], 1.35))
    col = nt.mix(nt.math('MULTIPLY', nt.sstep(shore, 0.02, 0.5), 0.85), col, g.outputs['seaC'])
    _, nc = nt.noise(moving((0.9, 0.9, 1.0), (0.1, 0.3, 0.35)), 1.0, detail=2.0)
    def vm(op, a, b):
        n = nt.node('ShaderNodeVectorMath', operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, bpy.types.NodeSocket): nt.L.new(v, n.inputs[i])
            elif v is not None: n.inputs[i].default_value = v
        return n
    nrm = vm('NORMALIZE', vm('ADD', vm('MULTIPLY', vm('SUBTRACT', nc, (0.5, 0.5, 0.5)).outputs[0], (0.5, 1.6, 0.0)).outputs[0], (0, 0, 1.0)).outputs[0], None).outputs[0]
    rf = vm('REFLECT', nt.scale(geo.outputs['Incoming'], -1.0), nrm).outputs[0]
    dp = vm('DOT_PRODUCT', rf, g.outputs['sund']).outputs['Value']
    col = nt.mix(nt.sstep(dp, 0.955, 0.992), col, g.outputs['glitc'], 'ADD')
    wob = nt.math('MULTIPLY', nt.math('SINE', nt.math('MULTIPLY', tm, 1.3)), 0.06)
    foam = nt.sstep(nt.math('ADD', shore, nt.math('ADD', nt.math('MULTIPLY', nt.math('SUBTRACT', n2, 0.5), 0.6), wob)), 0.62, 0.70)
    col = nt.mix(foam, col, g.outputs['foamc'])
    col = fogged(nt, g, col, pos)
    em = nt.node('ShaderNodeEmission'); nt.L.new(col, em.inputs['Color'])
    nt.L.new(em.outputs[0], nt.node('ShaderNodeOutputMaterial').inputs['Surface'])
    return m
M['sea'] = sea_mat()

# ----------------------------------------------------------------------------- world geometry
def grid(xs, ys):
    X, Y = np.meshgrid(xs, ys); ny, nx = X.shape
    i = np.arange(ny - 1)[:, None]; j = np.arange(nx - 1)[None, :]
    F = np.stack([i * nx + j, i * nx + j + 1, (i + 1) * nx + j + 1, (i + 1) * nx + j], -1).reshape(-1, 4)
    return X, Y, F
def box(c, h):
    s = np.array([(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], float)
    F = np.array([(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    return np.asarray(c, float) + s * np.asarray(h, float), F
def core(g, c, rad):
    V, F = ellipsoid((0, 0, 0), (1, 1, 1), 10, 7)
    g.add(V * rad + c, F, nrmz(V + [0, 0, 0.35]), np.full(len(V), 0.25))
class Kit:
    """Collects pieces per material; build() makes one object per material."""
    def __init__(s, T=None): s.g = {}; s.T = T
    def add(s, mat, VF, smooth=True):
        V = np.asarray(VF[0], float); V = xform(V, s.T) if s.T is not None else V
        s.g.setdefault((mat, smooth), Geo()).add(V, np.asarray(VF[1])); return s
    def build(s, name, shadow=True):
        return [g.build('%s_%s' % (name, k[0]), M[k[0]], smooth=k[1], shadow=shadow) for k, g in s.g.items()]

def build_land():
    xs = np.concatenate([-np.geomspace(3000, 76, 40), np.arange(-70, 80, 0.5), np.geomspace(86, 3000, 40)])
    ys = np.concatenate([-np.geomspace(3000, 51, 40), np.arange(-45, 62, 0.5)])
    X, Y, F = grid(xs, ys)
    pm = np.exp(-((X - path_x(Y)) / 0.75) ** 2) * (Y < GY - 0.6) * (Y > -120)
    Geo().add(np.stack([X, Y, ground(X, Y)], -1).reshape(-1, 3), F, None, pm.ravel()).build('land', M['ground'])

def build_sea():
    xs = np.concatenate([-np.geomspace(7000, 95, 36), np.arange(-90, 95, 0.75), np.geomspace(100, 7000, 36)])
    ys = np.concatenate([np.arange(0, 80, 0.75), np.arange(80, 260, 1.5), np.geomspace(262, 7000, 30)])
    X, Y, F = grid(xs, ys)
    d = coast_d(X, Y) - 2.5
    for (x, y, r, h) in STACKS: d = np.minimum(d, np.hypot(X - x, Y - y) - r * 1.15)
    Geo().add(np.stack([X, Y, np.zeros_like(X)], -1).reshape(-1, 3), F, None, np.exp(-np.maximum(d, 0) / 3.0).ravel()).build('sea', M['sea'], shadow=False)

def dabs(P, size):
    """Small upward-facing hexagon brush dabs at points P."""
    N = len(P); ln = nrmz(np.stack([rng.normal(0, 0.35, N), rng.normal(0, 0.35, N), np.ones(N)], 1))
    u = nrmz(np.cross(ln, [1.0, 0, 0])); v = np.cross(ln, u)
    ang = np.linspace(0, 2 * PI, 6, endpoint=False)[None, :] + rng.uniform(0, 1, (N, 1))
    rad = size * rng.uniform(0.7, 1.2, (N, 1))
    V = P[:, None, :] + (np.cos(ang) * rad)[..., None] * u[:, None, :] + (np.sin(ang) * rad)[..., None] * v[:, None, :]
    return V.reshape(-1, 3), np.arange(N * 6).reshape(N, 6)

def build_meadow():
    def blades(xs, ys, hmin, hmax):
        ok = (coast_d(xs, ys) < -2.0) & (np.abs(xs - path_x(ys)) > 0.85 - 0.4 * rng.uniform(0, 1, len(xs))) & ~in_cottage(xs, ys, 0.1)
        xs, ys = xs[ok], ys[ok]; n = len(xs)
        base = np.stack([xs, ys, ground(xs, ys)], 1)
        ang = rng.uniform(0, 2 * PI, n); w = rng.uniform(0.022, 0.05, n); h = rng.uniform(hmin, hmax, n)
        side = np.stack([np.cos(ang), np.sin(ang), np.zeros(n)], 1) * w[:, None]
        lean = np.stack([rng.normal(0, 0.16, n), rng.normal(-0.12, 0.16, n), np.ones(n)], 1) * h[:, None]
        V = np.stack([base - side, base + side, base + lean], 1).reshape(-1, 3)
        var = np.repeat(rng.uniform(0, 1, n), 3); var[2::3] = np.clip(var[2::3] + 0.35, 0, 1.3)
        return V, np.arange(n * 3).reshape(n, 3), None, var
    g = Geo()
    n = 190000; g.add(*blades(rng.uniform(-14, 15, n), rng.uniform(-36, 15.5, n), 0.18, 0.5))
    n = 120000; g.add(*blades(rng.uniform(-42, 42, n), rng.uniform(-48, 16, n), 0.25, 0.6))
    n = 60000; u = rng.uniform(0, 1, n); ab = PB - PA
    g.add(*blades(PA[0] + u * ab[0] + rng.uniform(-8, 8, n), PA[1] + u * ab[1] + rng.uniform(-8, 8, n), 0.2, 0.5))
    n = 26000; g.add(*blades(rng.uniform(-5, 6.5, n), rng.uniform(-36, -18, n), 0.5, 1.0))        # tall foreground blades
    g.build('grass', M['grass'], smooth=False, shadow=False)
    # wildflowers in drifts
    fl = {'fl_r': [], 'fl_w': [], 'fl_y': []}; keys = list(fl)
    for _ in range(260):
        cx, cy = rng.uniform(-17, 17), rng.uniform(-36, 14); n = int(rng.integers(25, 70)); k = keys[int(rng.integers(0, 3))]
        xs = cx + rng.normal(0, 1.3, n); ys = cy + rng.normal(0, 1.3, n)
        ok = (coast_d(xs, ys) < -2.0) & (np.abs(xs - path_x(ys)) > 0.7) & ~in_cottage(xs, ys, 0.2)
        xs, ys = xs[ok], ys[ok]
        fl[k].append(np.stack([xs, ys, ground(xs, ys) + rng.uniform(0.22, 0.5, len(xs))], 1))
    for k, pl in fl.items():
        P = np.concatenate(pl); Geo().add(*dabs(P, 0.062)).build(k, M[k], smooth=False, shadow=False)

def build_wall_and_fence():
    key = np.array([(4.6, -40.0), (4.0, -22.0), (4.7, -9.0), (5.2, 1.5), (8.5, 5.5), (12.5, 9.5)])
    seg = np.linalg.norm(np.diff(key, axis=0), axis=1); cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.arange(0, cum[-1], 0.36); px = np.interp(s, cum, key[:, 0]); py = np.interp(s, cum, key[:, 1])
    tg = nrmz(np.stack([np.gradient(px), np.gradient(py)], 1)); nr = np.stack([-tg[:, 1], tg[:, 0]], 1)
    g = Geo()
    for i in range(len(s)):
        z = float(ground(px[i], py[i]))
        for (o, dz) in ((-0.15, 0.1), (0.15, 0.1), (0.0, 0.36), (rng.uniform(-0.1, 0.1), 0.58)):
            if dz > 0.5 and rng.uniform() < 0.45: continue
            c = (px[i] + nr[i, 0] * o + rng.normal(0, 0.03), py[i] + nr[i, 1] * o + rng.normal(0, 0.03), z + dz + rng.normal(0, 0.02))
            g.add(*ellipsoid(c, (rng.uniform(0.17, 0.26), rng.uniform(0.17, 0.26), rng.uniform(0.11, 0.17)), 8, 6))
    g.build('wall', M['stone'])
    f = Geo(); xs = np.arange(-46.0, -2.5, 2.3)
    ys = 11.0 + 3.0 * np.sin(0.07 * xs + 1.0) + 2.0 * np.sin(0.19 * xs) - 2.4
    zs = ground(xs, ys); tops = []
    for x, y, z in zip(xs, ys, zs):
        t = (x + rng.normal(0, 0.05), y + rng.normal(0, 0.05), z + 1.05); f.add(*tube([(x, y, z - 0.2), t], [0.07, 0.055], 6)); tops.append(t)
    tops = np.array(tops)
    for hh in (0.12, 0.52):
        pts = []
        for a, b in zip(tops[:-1], tops[1:]): pts += [a - [0, 0, hh], (a + b) / 2 - [0, 0, hh + 0.1]]
        pts.append(tops[-1] - [0, 0, hh]); f.add(*tube(pts, 0.018, 5))
    f.build('fence', M['wood'])

def build_cottage():
    k = Kit(Matrix.Translation((CX, CY, float(ground(CX, CY)) - 0.25)) @ Matrix.Rotation(CROT, 4, 'Z'))
    k.add('stone', box((0, 0, -0.3), (3.4, 2.4, 0.6)), False).add('plaster', box((0, 0, 1.55), (3.2, 2.2, 1.3)), False)
    e, w, z0, z1 = 3.55, 2.65, 2.7, 4.5
    RV = [(-e, -w, z0), (e, -w, z0), (e, w, z0), (-e, w, z0), (-e, 0, z1), (e, 0, z1)]
    k.add('roof', (RV, [(0, 1, 5, 4), (2, 3, 4, 5), (0, 3, 2, 1)]), False)
    for sx in (-3.2, 3.2): k.add('plaster', ([(sx, -2.2, 2.84), (sx, 2.2, 2.84), (sx, 0, 4.33)], [(0, 1, 2)]), False)
    k.add('plaster', box((1.9, 0.5, 4.4), (0.32, 0.32, 0.7)), False).add('roof', box((1.9, 0.5, 5.15), (0.4, 0.4, 0.08)), False)
    k.add('blue', box((0.9, -2.22, 1.25), (0.45, 0.05, 1.0)), False)
    for c, h in (((-1.5, -2.22, 1.75), (0.5, 0.05, 0.5)), ((3.22, 0.2, 1.75), (0.05, 0.55, 0.5)), ((-3.22, 0.0, 1.75), (0.05, 0.55, 0.5)), ((-0.6, 2.22, 1.75), (0.5, 0.05, 0.5))):
        k.add('window', box(c, h), False)
    for x in (-2.16, -0.84): k.add('blue', box((x, -2.24, 1.75), (0.15, 0.04, 0.54)), False)
    k.build('cottage')

def build_lighthouse():
    k = Kit(Matrix.Translation((LX, LY, LZ)))
    prof = np.array([(2.6, 0.0), (2.5, 0.6), (2.25, 4.0), (1.95, 9.0), (1.7, 14.0), (1.6, 15.5)])
    k.add('plaster', lathe(prof, 28))
    for za, zb in ((5.0, 7.6), (10.8, 13.2)):
        zz = np.linspace(za, zb, 4); k.add('red', lathe(np.stack([np.interp(zz, prof[:, 1], prof[:, 0]) + 0.03, zz], 1), 28))
    k.add('dark', lathe([(1.6, 15.4), (2.45, 15.55), (2.45, 15.85), (1.3, 15.9)], 28))
    a = np.linspace(0, 2 * PI, 25)
    k.add('dark', tube(np.stack([2.38 * np.cos(a), 2.38 * np.sin(a), np.full(25, 16.85)], 1), 0.035, 5))
    for aa in a[:-1:2]: k.add('dark', tube([(2.38 * math.cos(aa), 2.38 * math.sin(aa), 15.85), (2.38 * math.cos(aa), 2.38 * math.sin(aa), 16.85)], 0.03, 5))
    k.add('lamp', lathe([(1.25, 15.9), (1.25, 18.05)], 24))
    for aa in a[:-1:3]: k.add('dark', tube([(1.28 * math.cos(aa), 1.28 * math.sin(aa), 15.9), (1.28 * math.cos(aa), 1.28 * math.sin(aa), 18.05)], 0.04, 5))
    k.add('red', lathe([(1.6, 18.0), (1.05, 18.8), (0.16, 19.7), (0.01, 19.75)], 24)).add('red', ellipsoid((0, 0, 19.95), (0.22, 0.22, 0.22), 10, 6))
    k.add('dark', box((0.0, -2.52, 1.1), (0.5, 0.12, 1.1)), False)
    k.add('plaster', box((-4.2, 0.6, 1.2), (2.0, 1.6, 1.5)), False)                               # keeper's store
    RV = [(-6.45, -1.2, 2.6), (-1.95, -1.2, 2.6), (-1.95, 2.4, 2.6), (-6.45, 2.4, 2.6), (-6.45, 0.6, 3.8), (-1.95, 0.6, 3.8)]
    k.add('roof', (RV, [(0, 1, 5, 4), (2, 3, 4, 5), (0, 3, 2, 1)]), False)
    for sx in (-6.2, -2.2): k.add('plaster', ([(sx, -1.0, 2.68), (sx, 2.2, 2.68), (sx, 0.6, 3.72)], [(0, 1, 2)]), False)
    k.add('window', box((-4.2, -1.02, 1.5), (0.45, 0.05, 0.45)), False)
    k.build('lighthouse')

def build_trees():
    trunk = Geo(); lf = Geo(); bush = Geo()
    def pine(x, y, Ht, r0, npr=150, sz=0.34):
        z0 = float(ground(x, y)) - 0.3; lean = V3(rng.uniform(-0.4, 0.2), -1.0, 0) * Ht * 0.22      # bent inland by the sea wind
        zs = np.array([0, 0.25, 0.55, 0.8, 1.0]) * Ht
        P = V3(x, y, z0) + np.outer((zs / Ht) ** 2, lean) + np.outer(zs, [0, 0, 1.0])
        trunk.add(*tube(P, r0 * np.array([1.5, 1.05, 0.85, 0.6, 0.3]), 9))
        for _ in range(int(rng.integers(5, 8))):
            aa = rng.uniform(0, 2 * PI); rr = rng.uniform(0.4, 0.33 * Ht)
            c = V3(P[-1][0] + rr * math.cos(aa), P[-1][1] + rr * math.sin(aa) - 0.06 * Ht, z0 + Ht * rng.uniform(0.84, 1.05))
            rad = V3(rng.uniform(1.8, 3.0), rng.uniform(1.8, 3.0), rng.uniform(0.7, 1.1)) * Ht / 9
            trunk.add(*tube([P[3], (P[3] + c) / 2 - [0, 0, 0.3], c], [r0 * 0.35, r0 * 0.22, 0.05], 6))
            lf.add(*leaves(c, rad, npr, sz)); core(lf, c, rad * 0.7)
    pine(-16.5, 3.5, 9.5, 0.36); pine(-19.5, -3.5, 8.0, 0.30); pine(-15.0, -8.5, 7.5, 0.30); pine(-24.0, 4.0, 8.5, 0.32)
    for _ in range(70):
        x, y = rng.uniform(-230, 230), rng.uniform(-210, -50)
        if abs(x) < 7: continue
        pine(x, y, rng.uniform(7, 11.5), 0.33, 60, 0.6)
    for _ in range(110):
        x, y = rng.uniform(-48, 48), rng.uniform(-50, 13)
        if coast_d(x, y) > -2.8 or abs(x - float(path_x(y))) < 2.6 or in_cottage(x, y, 1.2) or math.hypot(x - GX, y - GY) < 3: continue
        r = rng.uniform(0.5, 1.15); c = V3(x, y, float(ground(x, y)) + r * 0.35); rad = V3(r, r, r * 0.65)
        bush.add(*leaves(c, rad, 70, 0.17)); core(bush, c, rad * 0.7)
    for (x, y, r, h) in STACKS:
        V, F = lathe([(r * 1.35, -3.0), (r * 1.1, 0.5), (r * 0.9, h * 0.4), (r * 0.78, h * 0.75), (r * 0.45, h * 0.95), (0.01, h)], 12, rng.uniform(0.8, 1.2), rng.uniform(0.8, 1.2))
        V = V + [x, y, 0] + rng.normal(0, 0.12 * r, V.shape) * [1, 1, 0.3]; trunk_r = Geo().add(V, F); trunk_r.build('stack', M['rock'])
        c = V3(x, y, h * 0.93); bush.add(*leaves(c, (r * 0.5, r * 0.5, 0.4), 60, 0.2))
    trunk.build('trunks', M['bark']); lf.build('pines', M['pine'], smooth=False); bush.build('bushes', M['bush'], smooth=False)

def build_clouds():
    g = Geo()
    def heap(az, dist, base, Wd, Hh):
        c0 = V3(math.sin(az) * dist, math.cos(az) * dist, base); tx = V3(math.cos(az), -math.sin(az), 0); rd = V3(math.sin(az), math.cos(az), 0)
        for _ in range(int(rng.integers(16, 26))):
            u = rng.uniform(-1, 1); top = (1 - u * u) * rng.uniform(0.2, 1.0)
            r = rng.uniform(0.16, 0.30) * Wd * (0.6 + 0.5 * (1 - abs(u)))
            c = c0 + tx * u * Wd + rd * rng.uniform(-0.15, 0.15) * Wd + V3(0, 0, top * Hh + r * 0.35)
            g.add(*ellipsoid(c, (r, r, r * rng.uniform(0.6, 0.85)), 20, 12))
    for i in range(18):                          # big summer cumulus, leaving the sky straight out to sea open
        az = rng.uniform(0.5, 2.0) * (1 if i % 2 else -1) if i < 13 else rng.uniform(2.2, 4.1)
        dist = rng.uniform(1100, 2600); f = dist / 1500
        heap(az, dist, rng.uniform(150, 300) * f, rng.uniform(260, 620) * f, rng.uniform(180, 480) * f)
    for i in range(22):                          # a low far band along the horizon
        heap(rng.uniform(-PI, PI), rng.uniform(4500, 6000), rng.uniform(120, 220), rng.uniform(350, 700), rng.uniform(120, 300))
    for (x, y, b, wd, hh) in ((-170, 430, 95, 45, 35), (70, 520, 120, 60, 45), (-120, 610, 150, 70, 50), (20, 720, 170, 80, 60), (-210, 300, 110, 50, 40), (150, 330, 130, 55, 40)):
        heap(math.atan2(x, y), math.hypot(x, y), b, wd, hh)          # small ones beside the last leg of the flight
    return g.build('clouds', M['cloud'], shadow=False)

BOATS = []
def build_boats():
    for i, (x, y, hd, sp, hull) in enumerate([(-8.5, 43.3, 0.2, 1.0, 'red'), (-52.0, 96.0, 2.9, 0.8, 'plaster'), (75.0, 150.0, 0.5, 1.1, 'blue'),
                                             (-130.0, 270.0, -0.3, 0.9, 'plaster'), (30.0, 340.0, 3.3, 0.9, 'red'), (-55.3, 184.1, 0.3, 0.9, 'plaster')]):
        root = bpy.data.objects.new('boat%d' % i, None); S.collection.objects.link(root)
        k = Kit(); k.add(hull, ellipsoid((0, 0, 0.25), (0.9, 3.0, 0.7), 14, 8)).add('wood', tube([(0, 0.3, 0.6), (0, 0.3, 7.5)], 0.06, 6))
        k.add('sail', ([(0, 0.2, 7.3), (0, 0.2, 1.3), (0.25, -2.9, 1.3), (0, 0.45, 6.5), (0, 0.45, 1.2), (0.2, 2.9, 1.0)], [(0, 1, 2), (3, 4, 5)]), False)
        for ob in k.build('boat%d' % i, shadow=False): ob.parent = root
        BOATS.append((root, V3(x, y, 0), hd, sp, rng.uniform(0, 6.28)))

LA = V3(-7.5, -3.0, float(ground(-7.5, -3.0)) + 2.05); LB = V3(-3.6, -1.8, float(ground(-3.6, -1.8)) + 2.05)
LN = nrmz(V3((LB - LA)[1], -(LB - LA)[0], 0.0))                                                  # downwind (the wind comes off the sea)
SHEETS = []
def build_laundry():
    w = Geo()
    for p in (LA, LB): w.add(*tube([(p[0], p[1], p[2] - 2.3), p + [0, 0, 0.1]], 0.05, 6))
    u = np.linspace(0, 1, 14); rope = LA + np.outer(u, LB - LA); rope[:, 2] -= 0.15 * 4 * u * (1 - u)
    w.add(*tube(rope, 0.012, 5)); w.build('laundry_poles', M['wood'])
    for (u0, u1, h, mat) in ((0.06, 0.34, 1.25, 'dress'), (0.38, 0.56, 0.8, 'red'), (0.60, 0.86, 1.15, 'dress'), (0.88, 0.97, 0.6, 'blue')):
        U, Vv = np.meshgrid(np.linspace(u0, u1, 9), np.linspace(0, 1, 9)); nx = 9
        i = np.arange(8)[:, None]; j = np.arange(8)[None, :]
        F = np.stack([i * nx + j, i * nx + j + 1, (i + 1) * nx + j + 1, (i + 1) * nx + j], -1).reshape(-1, 4)
        top = LA + U.reshape(-1, 1) * (LB - LA); top[:, 2] -= 0.15 * 4 * U.ravel() * (1 - U.ravel())
        ob = Geo().add(np.zeros((81, 3)), F).build('sheet', M[mat])
        SHEETS.append((ob, top, U.ravel(), Vv.ravel(), h, rng.uniform(0, 6.28)))
def anim_laundry(t):
    for ob, top, U, Vv, h, ph in SHEETS:
        sw = 0.55 + 0.35 * math.sin(1.3 * t + ph) + 0.15 * math.sin(2.9 * t + 2 * ph)
        th = sw * Vv ** 1.3 * 0.9 + 0.12 * Vv * np.sin(14 * U * 4 + 6 * t + ph)
        P = top + h * Vv[:, None] * (np.sin(th)[:, None] * LN + np.cos(th)[:, None] * V3(0, 0, -1.0))
        ob.data.vertices.foreach_set('co', P.astype(np.float32).ravel()); ob.data.update()

NG = 16
GUL = dict(c=np.array([(4, 22), (8, 26), (24, 40), (26, 44), (20, 36), (-14, 24), (-18, 28), (2, 30), (30, 52), (-4, 18), (14, 20), (2, 118), (-16, 168), (-34, 232), (40, 20), (-10, -20)], float),
           R=rng.uniform(6, 16, NG), w=rng.uniform(0.25, 0.5, NG) * np.where(rng.uniform(0, 1, NG) < 0.5, -1, 1), ph=rng.uniform(0, 6.28, NG), z=rng.uniform(15, 30, NG))
def build_gulls():
    F = (np.array([(0, 1, 2), (0, 3, 1)])[None] + (np.arange(NG) * 4)[:, None, None]).reshape(-1, 3)
    return Geo().add(np.zeros((NG * 4, 3)), F).build('gulls', M['paper'], smooth=False, shadow=False)
def anim_gulls(t):
    a = GUL['w'] * t + GUL['ph']; sg = np.sign(GUL['w'])
    c = np.stack([GUL['c'][:, 0] + GUL['R'] * np.cos(a), GUL['c'][:, 1] + GUL['R'] * np.sin(a), GUL['z'] + 0.8 * np.sin(0.7 * t + GUL['ph'])], 1)
    fw = np.stack([-np.sin(a) * sg, np.cos(a) * sg, np.zeros(NG)], 1); side = np.stack([np.cos(a), np.sin(a), np.zeros(NG)], 1)
    flap = (0.38 * np.sin(7 * t + GUL['ph'] * 3) + 0.12)[:, None] * V3(0, 0, 1.0)
    V = np.stack([c + 0.32 * fw, c - 0.3 * fw, c + 0.95 * side + flap, c - 0.95 * side + flap], 1)
    GULLS.data.vertices.foreach_set('co', V.astype(np.float32).ravel()); GULLS.data.update()

def build_title():
    obs = []
    for txt, size, y in (('KAZE NO TEGAMI', 0.62, 0.0), ('A LETTER ON THE WIND', 0.2, -0.52)):
        cu = bpy.data.curves.new('title', 'FONT'); cu.body = txt; cu.align_x = 'CENTER'; cu.size = size; cu.space_character = 1.25
        for mat, off in (('titlesh', 0.009), ('title', 0.0)):
            c2 = cu.copy(); c2.materials.append(M[mat]); ob = bpy.data.objects.new('title', c2); S.collection.objects.link(ob); ob.visible_shadow = False
            obs.append((ob, y, off))
    return obs

# flight path of the paper plane (Catmull-Rom through key points, arc-length parametrised):
# off the cliff, down along the promontory, round the tip, up past the lamp, back over the meadow and the pine hill,
# out past the lighthouse again, down to skim the sea and up into the open sky
KP = np.array([(GX + 0.13, GY + 0.45, hG + 1.32), (0.4, 13.0, hG + 2.6), (1.5, 18.0, 12.0), (4.0, 25.0, 8.0), (9.0, 37.5, 3.2), (20.0, 51.5, 3.6),
               (32.0, 50.0, 8.0), (35.0, 39.0, 15.0), (28.0, 31.5, 23.0), (19.0, 38.0, 29.0),
               (10.0, 36.0, 31.0), (-2.0, 24.0, 28.0), (-9.0, 8.0, 23.0), (-9.0, -10.0, 22.0), (-2.0, -32.0, 27.0), (14.0, -52.0, 36.0), (36.0, -52.0, 41.0),
               (52.0, -30.0, 42.0), (50.0, 0.0, 40.0), (36.0, 36.0, 37.0), (18.0, 80.0, 33.0), (0.0, 125.0, 18.0), (-18.0, 170.0, 6.0), (-28.0, 205.0, 5.5),
               (-36.0, 250.0, 16.0), (-41.0, 320.0, 40.0), (-44.0, 400.0, 66.0), (-46.0, 480.0, 90.0), (-48.0, 560.0, 125.0), (-50.0, 640.0, 165.0)])
def _cr():
    P = np.concatenate([[2 * KP[0] - KP[1]], KP, [2 * KP[-1] - KP[-2]]]); out = []
    for i in range(len(KP) - 1):
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        for u in np.linspace(0, 1, 60, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    return np.array(out)
PATH = _cr(); PLEN = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(PATH, axis=0), axis=1))]); PTOT = PLEN[-1]
def pathP(s):
    s = clamp(s, 0, PTOT - 0.01); return np.array([np.interp(s, PLEN, PATH[:, k]) for k in range(3)])

def build_girl():
    root = bpy.data.objects.new('girl', None); S.collection.objects.link(root)
    root.location = (GX, GY, float(ground(GX, GY)) - 0.02)
    def part(name, pieces, parent, loc=(0, 0, 0)):
        obs = []
        for i, (mat, VF) in enumerate(pieces):
            ob = Geo().add(VF[0] - np.array(loc), VF[1]).build('%s%d' % (name, i), M[mat]); ob.parent = parent; ob.location = loc; obs.append(ob)
        return obs
    body = bpy.data.objects.new('gbody', None); S.collection.objects.link(body); body.parent = root
    pcs = [('dress', lathe([(0.01, 0.40), (0.31, 0.42), (0.27, 0.56), (0.175, 0.85), (0.118, 1.02), (0.105, 1.12), (0.125, 1.19), (0.06, 1.245), (0.01, 1.25)], 20, 1.0, 0.82)),
           ('blue', lathe([(0.121, 0.985), (0.128, 1.0), (0.126, 1.04), (0.112, 1.055)], 20, 1.0, 0.82)),
           ('skin', tube([(0, 0, 1.22), (0, 0.005, 1.31)], 0.036, 8))]
    for sgn in (-1, 1):
        pcs.append(('skin', tube([(sgn * 0.065, 0, 0.05), (sgn * 0.065, 0, 0.5)], [0.03, 0.04], 8)))
        pcs.append(('hair', ellipsoid((sgn * 0.065, 0.03, 0.035), (0.04, 0.075, 0.035), 10, 6)))
    part('gb', pcs, body)
    head = bpy.data.objects.new('ghead', None); S.collection.objects.link(head); head.parent = body; head.location = (0, 0, 1.28)
    hp = [('skin', ellipsoid((0, 0.012, 0.095), (0.104, 0.11, 0.118), 18, 12)),
          ('hair', ellipsoid((0, -0.03, 0.112), (0.124, 0.122, 0.128), 18, 12)),
          ('hair', ellipsoid((0, -0.075, 0.02), (0.122, 0.08, 0.135), 14, 10)),
          ('straw', lathe([(0.01, 0.245), (0.13, 0.225), (0.31, 0.175), (0.31, 0.165), (0.01, 0.19)], 28)),
          ('straw', ellipsoid((0, 0, 0.215), (0.127, 0.127, 0.09), 20, 10)),
          ('blue', lathe([(0.129, 0.2), (0.131, 0.215), (0.127, 0.245)], 24))]
    for sgn in (-1, 1): hp.append(('dark', ellipsoid((sgn * 0.043, 0.112, 0.085), (0.016, 0.008, 0.023), 8, 6)))
    for ob in part('gh', hp, head): pass
    arms = {}
    for nm, sgn in (('R', 1), ('L', -1)):
        sh = bpy.data.objects.new('sh' + nm, None); S.collection.objects.link(sh); sh.parent = body; sh.location = (sgn * 0.128, 0, 1.17)
        part('ua' + nm, [('dress', tube([(0, 0, 0.02), (0, 0, -0.1)], [0.045, 0.04], 8)), ('skin', tube([(0, 0, -0.08), (0, 0, -0.22)], [0.03, 0.027], 8))], sh)
        el = bpy.data.objects.new('el' + nm, None); S.collection.objects.link(el); el.parent = sh; el.location = (0, 0, -0.21)
        part('fa' + nm, [('skin', tube([(0, 0, 0.0), (0, 0, -0.2)], [0.028, 0.022], 8)), ('skin', ellipsoid((0, 0, -0.225), (0.028, 0.02, 0.036), 8, 6))], el)
        hd = bpy.data.objects.new('hand' + nm, None); S.collection.objects.link(hd); hd.parent = el; hd.location = (0, 0.02, -0.26)
        arms[nm] = (sh, el, hd)
    return root, body, head, arms

def build_plane():
    V = np.array([(0, 0.24, 0.0), (-0.14, -0.17, 0.035), (0.14, -0.17, 0.035), (0, -0.17, -0.065), (0, -0.17, 0.0)]) * 1.5
    F = np.array([(0, 1, 4), (0, 4, 2), (0, 4, 3)])
    return Geo().add(V, F).build('plane', M['paper'], smooth=False)

build_land(); build_sea(); build_meadow(); build_wall_and_fence(); build_cottage(); build_trees()
build_lighthouse(); CLOUDS = build_clouds(); build_boats(); build_laundry(); GULLS = build_gulls()
GROOT, GBODY, GHEAD, GARMS = build_girl(); PLANE = build_plane(); TITLE = build_title()

# ----------------------------------------------------------------------------- per-frame animation
def look_at(ob, pos, target, roll=0.0):
    pos = np.asarray(pos, float); z = nrmz(pos - np.asarray(target, float)); x = nrmz(np.cross([0, 0, 1.0], z)); y = np.cross(z, x)
    c, s = math.cos(roll), math.sin(roll); x, y = x * c + y * s, y * c - x * s
    m = Matrix.Identity(4)
    for i in range(3): m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], pos[i]
    ob.matrix_world = m
def orient(ob, pos, fwd, up=(0, 0, 1.0), scale=1.0):
    y = nrmz(fwd); x = nrmz(np.cross(y, up)); z = np.cross(x, y)
    m = Matrix.Identity(4)
    for i in range(3): m[i][0], m[i][1], m[i][2], m[i][3] = x[i] * scale, y[i] * scale, z[i] * scale, pos[i]
    ob.matrix_world = m

HOLD, RAISE, WIND, THROW, REST = V3(25, 85, -5), V3(98, 22, -45), V3(165, 95, -5), V3(80, 5, -10), V3(30, 12, -5)
def girl_pose(t):
    """Right-arm (shoulder, elbow) angles in degrees, head tilt, body lean."""
    lean = 0.0; head = 18.0
    if t < 9.8: r = HOLD
    elif t < 12.4: k = ss(9.8, 12.2, t); r = lerp(HOLD, RAISE, k); head = 18 - 6 * k
    elif t < 13.9: k = ss(12.4, 13.8, t); r = lerp(RAISE, WIND, k); lean = -7 * k; head = 12
    elif t < 14.35: k = ss(13.9, 14.3, t); r = lerp(WIND, THROW, k); lean = lerp(-7, 11, k); head = 12 + 8 * k
    else: k = ss(14.5, 16.5, t); r = lerp(THROW, REST, k); lean = lerp(11, 0, k); head = 22
    return r, head, lean

DAY = dict(sd=nrmz(V3(0.45, 0.35, 0.82)), sc=V3(1.0, 0.96, 0.84), X=1.7, amb=V3(0.70, 0.82, 1.0) * 0.6, gain=1.0, fogc=V3(0.80, 0.90, 0.97), fogd=0.0016,
           hor=V3(0.80, 0.91, 0.98), zen=V3(0.20, 0.48, 0.86), cc=V3(1.0, 1.0, 1.0), ca=0.3, star=0.0, glowc=V3(1.0, 0.97, 0.85), glowa=0.2, disc=0.0, discc=V3(3.0, 2.6, 1.6),
           seaA=V3(0.05, 0.30, 0.62), seaB=V3(0.16, 0.50, 0.78), seaC=V3(0.30, 0.78, 0.80), glitc=V3(1.0, 1.0, 0.92), glita=1.0, foamc=V3(1.0, 1.0, 1.0))
def path_s(t):
    if t < 14.3: return 0.0
    if t < 15.0: return lerp(0.0, 9.0, ((t - 14.3) / 0.7) ** 1.3)
    return 9.0 + (PTOT - 60.0 - 9.0) * ((t - 15.0) / 45.0) ** 1.03      # same pace as the 60 s film; this cut stops at 45 s

def apply(t):
    P = DAY
    # light, sky and the shared material values
    SUN.data.color = tuple(P['sc']); SUN.data.energy = PI * P['X']
    look_at(SUN, P['sd'] * 100, (0, 0, 0))
    setg('L0', float(np.dot(P['amb'], (0.2126, 0.7152, 0.0722)) + P['X'])); setg('gain', P['gain'])
    setg('fogc', lin(P['fogc'])); setg('fogd', P['fogd']); setg('time', t); setg('cloudk', 1.0); setg('lamp', 0.0); setg('win', 0.0)
    for k in ('seaA', 'seaB', 'seaC', 'foamc'): setg(k, lin(P[k]))
    setg('glitc', np.array(lin(P['glitc'])) * P['glita'])
    for i in range(3): SUNV.inputs[i].default_value = float(P['sd'][i]); WSUN.inputs[i].default_value = float(P['sd'][i])
    for k, v in (('horizon', lin(P['hor'])), ('zenith', lin(P['zen'])), ('amb', P['amb']), ('cloudc', lin(P['cc'])), ('clouda', P['ca']), ('stara', P['star']),
                 ('glowc', P['glowc']), ('glowa', P['glowa']), ('disca', P['disc']), ('discc', P['discc'])): setw(k, v)
    WCLOUD.inputs['Location'].default_value = (t * 0.01, 0.0, 0.0)
    CLOUDS.location = (2.0 * t, 0.0, 0.0)

    # girl
    r, head, lean = girl_pose(t)
    br = 0.006 * math.sin(t * 2.2)
    GBODY.rotation_euler = (math.radians(lean), 0, 0); GBODY.location = (0, 0, br)
    GHEAD.rotation_euler = (math.radians(head - lean * 0.5), 0, math.radians(4 * math.sin(t * 0.5)))
    shR, elR, hdR = GARMS['R']; shL, elL, hdL = GARMS['L']
    shR.rotation_euler = (math.radians(r[0]), 0, math.radians(r[2])); elR.rotation_euler = (math.radians(r[1]), 0, 0)
    shL.rotation_euler = (math.radians(8 + 3 * math.sin(t * 1.1)), math.radians(8), 0); elL.rotation_euler = (math.radians(14), 0, 0)
    bpy.context.view_layer.update()
    hand = np.array(hdR.matrix_world.translation)

    # paper plane
    s = path_s(t); pp = pathP(s); tg = nrmz(pathP(s + 0.6) - pathP(max(s - 0.6, 0)))
    if t < 14.3:
        fw = V3(0.0, 1.0, 0.25) if t < 12.4 else nrmz(V3(0.0, 1.0, lerp(0.25, 0.5, ss(12.4, 13.8, t))))
        orient(PLANE, hand + V3(0, 0.02, 0.05), fw, V3(0, -0.25, 1.0))
    else:
        k = ss(14.3, 14.5, t); pos = lerp(hand, pp, k) if k < 1 else pp
        a2 = nrmz(pathP(s + 3.0) - pathP(s + 0.5)); bank = float(np.cross(tg, a2)[2]) * 4.0
        side = nrmz(np.cross(tg, [0, 0, 1.0])); up = nrmz(V3(0, 0, 1.0) - side * bank)
        orient(PLANE, pos + V3(0, 0, 0.06 * math.sin(t * 5.0)), tg, up, scale=1.0 + 0.35 * ss(15.0, 17.0, t))

    # camera per shot
    exposure = 0.0; fade = 0.0; lens = 32.0; titlea = 0.0
    if t < 9.6:                                   # up the meadow path toward the cliff edge
        k = ss(0, 9.6, t) * 0.6 + 0.4 * (t / 9.6)
        pos = lerp(V3(1.3, -26.0, 1.5), V3(0.5, -14.0, 1.4), k); pos[2] += float(ground(pos[0], pos[1]))
        look_at(CAM, pos, lerp(V3(10.0, 20.0, 17.0), V3(8.0, 20.0, 16.0), k)); lens = 24.0
        fade = 1.0 - ss(0.0, 1.6, t)
    elif t < 15.0:                                # behind her: the throw, and the plane leaving over the edge
        k = (t - 9.6) / 5.4
        pos = V3(GX, GY, hG) + lerp(V3(1.0, -3.9, 1.2), V3(0.9, -3.5, 1.35), k)
        look_at(CAM, pos, pos + V3(math.sin(0.175) * 20, math.cos(0.175) * 20, 3.4)); lens = 16.0
    else:                                         # chase, all the way up into the open sky
        e = ss(37.0, 45.0, t)                     # at the end the plane pulls away and the camera lets it go
        cs_ = max(s - lerp(4.2, 26.0, e ** 1.5), 0.0); cp = pathP(cs_); ct = nrmz(pathP(cs_ + 1.0) - pathP(max(cs_ - 1.0, 0)))
        side = nrmz(np.cross(ct, [0, 0, 1.0]))
        pos = cp + V3(0, 0, 0.5) + side * 0.35
        pos[2] = max(pos[2], max(float(ground(pos[0], pos[1])), 0.0) + 1.0)
        a2 = nrmz(pathP(s + 3.0) - pathP(s + 0.5)); bank = float(np.cross(tg, a2)[2])
        look_at(CAM, pos, pathP(s + 1.5) + V3(0, 0, 6.0 * e), roll=-bank * 1.2 * (1 - e)); lens = 21.0
        titlea = ss(40.3, 41.5, t) if SHOW_TITLE else 0.0; fade = ss(44.0, 44.9, t)
    CAM.data.lens = lens
    CEXP.default_value = exposure; CFADE.default_value = fade; CFADEC.default_value = (0, 0, 0, 1) if t < 30 else (1, 1, 1, 1); setg('titlea', titlea)
    bpy.context.view_layer.update()
    cm = CAM.matrix_world.copy()
    for ob, y, off in TITLE:
        ob.hide_render = titlea <= 0.0
        ob.matrix_world = cm @ Matrix.Translation((off * 0.7, (0.25 + y) * 0.16 - off * 0.7, -1.4 - off)) @ Matrix.Scale(0.16, 4)

    # wind and sea life
    anim_laundry(t); anim_gulls(t)
    for root, p0, hd, sp, ph in BOATS:
        root.location = (p0[0] + math.cos(hd) * sp * t, p0[1] + math.sin(hd) * sp * t, 0.06 * math.sin(1.1 * t + ph))
        root.rotation_euler = (math.radians(3) * math.sin(0.9 * t + ph), math.radians(7 + 2 * math.sin(0.6 * t + ph)), hd - PI / 2)

def render(t, path):
    apply(t); S.render.filepath = path; bpy.ops.render.render(write_still=True)

if ARGS[0] == '--stills':
    out = ARGS[2]; os.makedirs(out, exist_ok=True)
    if len(ARGS) > 3: S.render.resolution_percentage = int(float(ARGS[3]) * 100); KUW.inputs['Size'].default_value = KSIZE * float(ARGS[3])
    for ts in ARGS[1].split(','):
        t0 = time.time(); render(float(ts), os.path.join(out, 's_%06.2f.png' % float(ts))); print('still', ts, '%.1fs' % (time.time() - t0), flush=True)
elif ARGS[0] == '--range':
    for f in range(int(ARGS[1]), int(ARGS[2])):
        render(f / FPS, os.path.join(ARGS[3], 'f%05d.png' % f)); print('frame', f, flush=True)
