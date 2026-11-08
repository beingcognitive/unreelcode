"""The scene for Blender 5.1 Cycles: everything procedural (geometry, materials, sky). Run:
  Blender -b --factory-startup --python render/scene.py -- --still hook --samples 64 --out out/look/hook.png
Domino poses come from the MuJoCo simulation (out/film_chain.npz); props are static and never touch the chain."""
import sys, os, math, json, time
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector, Euler, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bl_util as U  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


CHAIN = arg("--chain", os.path.join(ROOT, "out/film_chain"))
if not os.path.exists(CHAIN + ".json"):
    CHAIN = os.path.join(ROOT, "out/film_chain")
J = json.load(open(CHAIN + ".json"))
Z = np.load(CHAIN + ".npz")
ZT, ZQ, ZN = Z["t"], Z["qpos"], Z["needle_x"]
DOM = J["dom"]; N = len(DOM)
NEEDLE = J["needle"]
TIP_R = NEEDLE["tip_r"]

SUN_DIR = Vector((-0.42, -0.50, 0.76)).normalized()     # toward the sun (as in v2)

# props (true sizes, metres)
RULER = dict(x0=-0.250, x1=0.050, y0=-0.0068, y1=-0.0318)
RICE = [(0.0035, -0.0042, 15), (0.0085, -0.0046, -25), (0.0042, 0.0050, 95), (-0.0062, -0.0036, 40),
        (0.0095, 0.0060, 60)]
COIN = (0.0140, 0.0175)
MUG = (0.160, 0.100)
CHAIR = (0.98, 0.62)
FENCE_Y = 3.2
BIKE = (6.95, 2.78)
LAMP = (17.5, 4.6)
CAR = (36.2, -5.2)
HOUSE = (29.0, 12.6)
TREES = [(34.5, 21.5, 9.5), (40.5, 9.5, 11.0), (45.5, 15.5, 10.0)]
KERB_Y = 8.4
DECK_X = 3.2


# ================================================================================================ materials
def mat_lacquer():
    """deep black lacquer with a clear coat: mirror-like reflections"""
    m = U.principled("lacquer", base=(0.002, 0.002, 0.002), rough=0.18, coat=1.0, coat_rough=0.012, spec=0.35)
    m.node_tree.nodes["Principled BSDF"].inputs["Coat IOR"].default_value = 1.38
    return m


def mat_ivory():
    return U.principled("pip_paint", base=(0.86, 0.83, 0.74), rough=0.38)


def mat_brass(name="brass", base=(0.86, 0.66, 0.36), rough=0.22):
    return U.principled(name, base=base, rough=rough, metal=1.0)


def mat_wood_deck():
    """pale ash boards, 10 cm x 1.8 m, 1.6 mm seams; grain, pores, faint scratches; varnished (clear coat)"""
    m, nt, p = U.new_mat("deck")
    tc = U.node(nt, "ShaderNodeTexCoord", (-1600, 0))
    sep = U.node(nt, "ShaderNodeSeparateXYZ", (-1400, 0)); U.link(nt, tc.outputs["Object"], sep.inputs[0])
    # boards (brick texture: row height = board width)
    br = U.node(nt, "ShaderNodeTexBrick", (-1100, 300))
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.0016
    br.inputs["Brick Width"].default_value = 1.8
    br.inputs["Row Height"].default_value = 0.10
    br.inputs["Color1"].default_value = (0.78, 0.66, 0.50, 1)
    br.inputs["Color2"].default_value = (0.70, 0.58, 0.43, 1)
    br.inputs["Mortar"].default_value = (0.20, 0.15, 0.11, 1)
    br.offset = 0.37; br.offset_frequency = 1
    U.link(nt, tc.outputs["Object"], br.inputs["Vector"])
    # grain: sin((y + warp) * 2 pi / 1.4 mm), warp from stretched noise
    mp = U.node(nt, "ShaderNodeMapping", (-1300, -200)); mp.inputs["Scale"].default_value = (8.0, 120.0, 1.0)
    U.link(nt, tc.outputs["Object"], mp.inputs["Vector"])
    nz = U.node(nt, "ShaderNodeTexNoise", (-1100, -200)); nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    U.link(nt, mp.outputs[0], nz.inputs["Vector"])
    warp = U.math_node(nt, "MULTIPLY", nz.outputs["Fac"], vb=0.006)
    yy = U.math_node(nt, "ADD", sep.outputs["Y"], warp)
    ph = U.math_node(nt, "MULTIPLY", yy, vb=2 * math.pi / 0.0014)
    s = U.math_node(nt, "SINE", ph)
    g = nt.nodes.new("ShaderNodeMath"); g.operation = "MULTIPLY_ADD"
    U.link(nt, s, g.inputs[0]); g.inputs[1].default_value = 0.5; g.inputs[2].default_value = 0.5
    # pores: fine stretched noise thresholded
    mp2 = U.node(nt, "ShaderNodeMapping", (-1300, -500)); mp2.inputs["Scale"].default_value = (300.0, 2500.0, 1.0)
    U.link(nt, tc.outputs["Object"], mp2.inputs["Vector"])
    pn = U.node(nt, "ShaderNodeTexNoise", (-1100, -500)); pn.inputs["Scale"].default_value = 1.0
    pn.inputs["Detail"].default_value = 1.0
    U.link(nt, mp2.outputs[0], pn.inputs["Vector"])
    pores = U.math_node(nt, "GREATER_THAN", pn.outputs["Fac"], vb=0.66)
    # scratches: very stretched noise in a diagonal frame, thin threshold band
    mp3 = U.node(nt, "ShaderNodeMapping", (-1300, -800)); mp3.inputs["Scale"].default_value = (12.0, 1800.0, 1.0)
    mp3.inputs["Rotation"].default_value = (0, 0, 0.6)
    U.link(nt, tc.outputs["Object"], mp3.inputs["Vector"])
    sn = U.node(nt, "ShaderNodeTexNoise", (-1100, -800)); sn.inputs["Scale"].default_value = 1.0
    sn.inputs["Detail"].default_value = 0.0
    U.link(nt, mp3.outputs[0], sn.inputs["Vector"])
    sd = U.math_node(nt, "SUBTRACT", sn.outputs["Fac"], vb=0.5)
    sa = U.math_node(nt, "ABSOLUTE", sd)
    scr = U.math_node(nt, "LESS_THAN", sa, vb=0.004)
    # colour = brick colour * (0.86 + 0.14 grain) * (1 - 0.35 pores)
    gm_n = nt.nodes.new("ShaderNodeMath"); gm_n.operation = "MULTIPLY_ADD"
    U.link(nt, g.outputs[0], gm_n.inputs[0]); gm_n.inputs[1].default_value = 0.16; gm_n.inputs[2].default_value = 0.84
    pm = nt.nodes.new("ShaderNodeMath"); pm.operation = "MULTIPLY_ADD"
    U.link(nt, pores, pm.inputs[0]); pm.inputs[1].default_value = -0.35; pm.inputs[2].default_value = 1.0
    f = U.math_node(nt, "MULTIPLY", gm_n.outputs[0], pm.outputs[0])
    cm = U.node(nt, "ShaderNodeMix", (-300, 200)); cm.data_type = "RGBA"; cm.blend_type = "MULTIPLY"
    cm.inputs["Factor"].default_value = 1.0
    U.link(nt, br.outputs["Color"], cm.inputs[6])
    comb = U.node(nt, "ShaderNodeCombineXYZ", (-500, 100))
    for k in range(3): U.link(nt, f, comb.inputs[k])
    U.link(nt, comb.outputs[0], cm.inputs[7])
    U.link(nt, cm.outputs[2], p.inputs["Base Color"])
    # bump: seams (brick fac), grain, pores, scratches
    hb = U.math_node(nt, "MULTIPLY", g.outputs[0], vb=0.25)
    hp = U.math_node(nt, "MULTIPLY", pores, vb=-0.6)
    hs = U.math_node(nt, "MULTIPLY", scr, vb=-0.4)
    hm = U.math_node(nt, "MULTIPLY", br.outputs["Fac"], vb=-3.0)
    h1 = U.math_node(nt, "ADD", hb, hp); h2 = U.math_node(nt, "ADD", h1, hs); h3 = U.math_node(nt, "ADD", h2, hm)
    bump = U.node(nt, "ShaderNodeBump", (-200, -300)); bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.00008
    U.link(nt, h3, bump.inputs["Height"])
    U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.5
    p.inputs["Coat Weight"].default_value = 0.55
    sr = nt.nodes.new("ShaderNodeMath"); sr.operation = "MULTIPLY_ADD"
    U.link(nt, scr, sr.inputs[0]); sr.inputs[1].default_value = 0.25; sr.inputs[2].default_value = 0.05
    U.link(nt, sr.outputs[0], p.inputs["Coat Roughness"])
    return m


def mat_paving():
    m, nt, p = U.new_mat("paving")
    tc = U.node(nt, "ShaderNodeTexCoord", (-1200, 0))
    br = U.node(nt, "ShaderNodeTexBrick", (-900, 200))
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.006
    br.inputs["Mortar Smooth"].default_value = 0.4
    br.inputs["Brick Width"].default_value = 0.20
    br.inputs["Row Height"].default_value = 0.10
    br.inputs["Color1"].default_value = (0.74, 0.70, 0.64, 1)
    br.inputs["Color2"].default_value = (0.62, 0.59, 0.55, 1)
    br.inputs["Mortar"].default_value = (0.42, 0.40, 0.37, 1)
    U.link(nt, tc.outputs["Object"], br.inputs["Vector"])
    nz = U.node(nt, "ShaderNodeTexNoise", (-900, -200)); nz.inputs["Scale"].default_value = 180.0
    nz.inputs["Detail"].default_value = 6.0
    U.link(nt, tc.outputs["Object"], nz.inputs["Vector"])
    cm = U.node(nt, "ShaderNodeMix", (-500, 100)); cm.data_type = "RGBA"; cm.blend_type = "MULTIPLY"
    cm.inputs["Factor"].default_value = 0.35
    U.link(nt, br.outputs["Color"], cm.inputs[6]); U.link(nt, nz.outputs["Color"], cm.inputs[7])
    U.link(nt, cm.outputs[2], p.inputs["Base Color"])
    h = U.math_node(nt, "SUBTRACT", nz.outputs["Fac"], br.outputs["Fac"])
    bump = U.node(nt, "ShaderNodeBump", (-200, -300)); bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.004
    U.link(nt, h, bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.85
    return m


def mat_soil():
    return U.principled("soil", base=(0.22, 0.24, 0.13), rough=0.95)


def build_floor():
    """the floor z = 0 as three regions: wooden deck (x < 3.2 m), paving (x >= 3.2 m), both within |y| < 8.4 m;
    lawn soil beyond (grass is added separately)"""
    deck, pav, soil = mat_wood_deck(), mat_paving(), mat_soil()
    bm = bmesh.new()
    def quad(x0, x1, y0, y1, mi):
        vs = [bm.verts.new((x0, y0, 0)), bm.verts.new((x1, y0, 0)), bm.verts.new((x1, y1, 0)), bm.verts.new((x0, y1, 0))]
        f = bm.faces.new(vs); f.material_index = mi
    E = 2000.0           # far enough that no camera ever sees the edge of the world
    quad(-E, DECK_X, -KERB_Y, KERB_Y, 0)
    quad(DECK_X, E, -KERB_Y, KERB_Y, 1)
    quad(-E, E, KERB_Y, E, 2)
    quad(-E, E, -E, -KERB_Y, 2)
    return U.obj_from_bm("floor", bm, mats=[deck, pav, soil])


# ================================================================================================ dominoes
# pip layouts on a square half-face, coordinates in units of the face width (u across, v along the height)
_a, _r = 0.25, 0.0
GRID3 = {0: [], 1: [(0, 0)], 2: [(-_a, -_a), (_a, _a)], 3: [(-_a, -_a), (0, 0), (_a, _a)],
         4: [(-_a, -_a), (-_a, _a), (_a, -_a), (_a, _a)], 5: [(-_a, -_a), (-_a, _a), (_a, -_a), (_a, _a), (0, 0)],
         6: [(-_a, -_a), (-_a, 0), (-_a, _a), (_a, -_a), (_a, 0), (_a, _a)],
         7: [(-_a, -_a), (-_a, 0), (-_a, _a), (_a, -_a), (_a, 0), (_a, _a), (0, 0)],
         8: [(-_a, -_a), (-_a, 0), (-_a, _a), (_a, -_a), (_a, 0), (_a, _a), (0, -_a), (0, _a)],
         9: [(u, v) for u in (-_a, 0, _a) for v in (-_a, 0, _a)],
         10: [(u, v) for u in (-_a, _a) for v in (-0.285, -0.095, 0.095, 0.285)] + [(0, -0.095), (0, 0.095)],
         11: [(u, v) for u in (-_a, _a) for v in (-0.285, -0.095, 0.095, 0.285)] + [(0, -0.19), (0, 0.0), (0, 0.19)],
         12: [(u, v) for u in (-_a, 0, _a) for v in (-0.285, -0.095, 0.095, 0.285)]}
PIP_R = 0.066      # pip radius / face width
PIP_D = 0.020      # pip depth / thickness... (fraction of h)


def pips_for(k):
    """domino k (1-based) shows k pips: floor(k/2) on top, ceil(k/2) below"""
    return k // 2, k - k // 2


def build_domino(k, lac, ivory, brass):
    """a unit domino (h = 1): thickness 0.15, width 0.5; local x = thickness (pips on the -x face)"""
    h, w, d = 1.0, 0.5, 0.15
    bm = bmesh.new()
    U.box(bm, (0, 0, 0), (d, w, h))
    U.bevel_all(bm, 0.022, segs=4, profile=0.5)
    ob = U.obj_from_bm(f"dom{k}", bm, mats=[lac, ivory])
    # cutter: pips (drilled), divider groove
    cb = bmesh.new()
    top, bot = pips_for(k)
    face_x = -d / 2
    depth = 0.018
    for half, n in ((+1, top), (-1, bot)):
        for (u, v) in GRID3[n]:
            cy = u * w; cz = half * h / 4 + v * w
            U.cyl(cb, (face_x, cy, cz), PIP_R * w, PIP_R * w, 2 * depth, segs=24,
                  rot=Euler((0, math.pi / 2, 0)).to_matrix())
    U.box(cb, (face_x, 0, 0), (2 * 0.010, w * 0.78, 0.010))      # engraved divider
    cut = U.obj_from_bm(f"cut{k}", cb, mats=[ivory])
    U.boolean(ob, cut, "DIFFERENCE", transfer=True)
    U.remove(cut)
    # make sure only the recessed faces are ivory; everything on the outer skin is lacquer
    me = ob.data
    lac_i = list(me.materials).index(lac) if lac in list(me.materials) else 0
    for poly in me.polygons:
        c = poly.center
        recessed = c.x > face_x + 0.0005 and abs(c.x - face_x) < depth + 0.001 and abs(c.y) < w / 2 - 0.03
        name = me.materials[poly.material_index].name if poly.material_index < len(me.materials) else ""
        if name.startswith("pip_paint") and not recessed:
            poly.material_index = lac_i
    me.shade_smooth()
    wn = ob.modifiers.new("wn", "WEIGHTED_NORMAL"); wn.keep_sharp = True; wn.mode = "FACE_AREA"
    # spinner pin: a small brass dome at the centre of the face
    sb = bmesh.new()
    U.sphere(sb, (face_x - 0.002, 0, 0), (0.010, 0.030, 0.030), segs=(24, 12))
    sp = U.obj_from_bm(f"spin{k}", sb, mats=[brass], smooth=True)
    sp.parent = ob
    return ob


# ================================================================================================ build
def build(level="all"):
    """level: 'macro' skips the big outdoor props (fast look-dev of the opening); 'all' builds everything"""
    import props as P, props2 as P2
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    lac, ivory, brass = mat_lacquer(), mat_ivory(), mat_brass()
    doms = [build_domino(k + 1, lac, ivory, brass) for k in range(N)]
    for i, ob in enumerate(doms):
        ob.scale = (DOM[i]["h"],) * 3
    build_floor()
    parts = dict(doms=doms)
    parts["pencil"] = P.build_pencil()
    P.build_ruler(RULER)
    rm = P.mat_rice()
    for i, (x, y, yaw) in enumerate(RICE):
        ob, c = P.build_rice(f"rice{i}", rm, seed=i + 3)
        ob.location = (x, y, c * 0.97); ob.rotation_euler = (0, 0, math.radians(yaw))
    P.build_coin(*COIN)
    P.build_mug(*MUG)
    P.build_dust((-0.03, 0.07, -0.0065, 0.035), n=70)
    P.build_chair(*CHAIR)
    if level == "all":
        # door-height scale cues between the chair and the lamp post: a garden fence with a gate, and a bicycle
        P.build_fence(FENCE_Y, 1.0, 11.0, gate=(5.0, 6.0))
        P.build_bicycle(*BIKE, lean_deg=10.0)
        P.build_lamp(*LAMP)
        P.build_kerb(KERB_Y, x1=90)
        P2.build_car(*CAR)
        P2.build_house(*HOUSE)
        for k, (x, y, hgt) in enumerate(TREES):
            P2.build_tree(f"tree{k}", x, y, hgt, seed=21 + k)
        if "--nograss" not in ARGS:
            P2.build_grass([(-20, 80, KERB_Y + 0.15, 60), (-20, 80, -60, -KERB_Y - 0.15)], cam_xy=(8.0, -15.0))
    world_and_light(sc)
    return parts


def world_and_light(sc):
    w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky"); sky.sky_type = "MULTIPLE_SCATTERING"
    el = math.asin(SUN_DIR.z); az = math.atan2(SUN_DIR.y, SUN_DIR.x)
    sky.sun_disc = False
    sky.sun_elevation = el
    sky.sun_rotation = az - math.pi / 2 if False else (math.pi / 2 - az)
    sky.altitude = 100.0
    sky.air_density = 0.45; sky.aerosol_density = 10.0
    bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = float(arg("--sky", 0.10, float))
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0]); nt.links.new(bg.outputs[0], out.inputs[0])
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = float(arg("--sun", 3.4, float))
    sun.angle = math.radians(0.8); sun.color = (1.0, 0.96, 0.90)
    so = bpy.data.objects.new("sun", sun); U.collection().objects.link(so)
    so.rotation_euler = (-SUN_DIR).to_track_quat("-Z", "Y").to_euler()


def pose(parts, s, pencil_back=0.0):
    import props as P
    j = min(int(round(s * 1000.0)), len(ZT) - 1)
    q = ZQ[j]
    for i, ob in enumerate(parts["doms"]):
        ob.location = q[7 * i: 7 * i + 3]
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = Quaternion(q[7 * i + 3: 7 * i + 7])
    xn = float(ZN[j])
    # the pencil's graphite point is the simulated tip sphere (radius TIP_R): apex = centre + TIP_R along +x
    tip = Vector((xn + TIP_R, 0.0, NEEDLE["z"]))
    # display only: after its contact has ended (0.66 s) the pencil withdraws back along its own axis and out of
    # frame (0.9 -> 2.1 s of sim time), so a long pencil never lies across the wider shots
    k = min(max((s - 0.9) / 1.2, 0.0), 1.0); k = k * k * (3 - 2 * k)
    t, y = math.radians(14), math.radians(25)
    back = Vector((-math.cos(t) * math.cos(y), -math.cos(t) * math.sin(y), math.sin(t)))
    P.place_pencil(parts["pencil"], tip + back * (0.30 * k + pencil_back))
    return xn


def camera(pos, target, fov_deg, fstop=None, focus=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("cam") or bpy.data.cameras.new("cam")
    co = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", cd)
    if co.name not in U.collection().objects:
        U.collection().objects.link(co)
    sc.camera = co
    co.location = pos
    co.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    cd.sensor_fit = "VERTICAL"; cd.angle_y = math.radians(fov_deg)
    cd.clip_start = max(1e-5, 0.002 * (Vector(target) - Vector(pos)).length)
    cd.clip_end = 2000.0
    cd.dof.use_dof = fstop is not None
    if fstop is not None:
        cd.dof.aperture_fstop = fstop
        cd.dof.focus_distance = focus if focus else (Vector(target) - Vector(pos)).length


def render_settings(samples, res_scale=1.0):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"; prefs.get_devices()
    for dv in prefs.devices:
        dv.use = dv.type == "METAL"
    sc.cycles.device = "GPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6; sc.cycles.glossy_bounces = 3; sc.cycles.transmission_bounces = 4
    sc.cycles.diffuse_bounces = 2; sc.cycles.transparent_max_bounces = 4
    sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = float(arg("--noise", 0.03, float))
    sc.cycles.adaptive_min_samples = 8
    sc.render.use_persistent_data = True
    sc.cycles.sample_clamp_indirect = 8.0
    sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
    sc.render.resolution_x = int(1080 * res_scale); sc.render.resolution_y = int(1920 * res_scale)
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Base Contrast" if False else "None"
    sc.view_settings.exposure = float(arg("--exposure", 0.0, float))
    sc.render.image_settings.file_format = "PNG"


def dvec(x, y, z):
    v = Vector((x, y, z)); return v / v.length


STILLS = {
    "hook":    dict(s=0.0, level="macro", target=(-0.0035, 0.0, 0.0030), dist=0.085, dirn=(-0.12, -1.0, 0.30), fov=30, fstop=16.0),
    "pips":    dict(s=0.0, level="macro", target=(0.0160, 0.0, 0.0055), dist=0.115, dirn=(-0.75, -1.0, 0.42), fov=30, fstop=16.0),
    "ladder":  dict(s=4.2, level="all", target=(0.62, 0.15, 0.22), dist=3.0, dirn=(-1.0, -0.45, 0.65), fov=40, fstop=None),
    "door":    dict(s=8.9, level="all", target=(4.6, 1.6, 1.1), dist=9.5, dirn=(-1.0, -0.55, 0.55), fov=40, fstop=None),
    "reflect": dict(s=6.70, level="all", pos=(2.30, -0.80, 0.48), target=(2.80, 0.05, 0.70), fov=64, fstop=None),
    "giant":   dict(s=21.3, level="all", pos=(8.0, -15.0, 1.7), target=(27.0, 3.0, 5.2), fov=58, fstop=None),
    "overview": dict(s=26.0, level="all", target=(23.0, 0.0, 1.0), dist=78.0, dirn=(-0.45, -1.0, 0.95), fov=40, fstop=None),
    "coin":    dict(s=0.0, level="macro", target=(0.0140, 0.0175, 0.0012), dist=0.050, dirn=(-0.05, -0.30, 1.2), fov=30, fstop=22.0),
}


def still_camera(S):
    if "--cam" in ARGS:
        S = dict(S); S["pos"] = tuple(float(v) for v in arg("--cam").split(","))
        S["target"] = tuple(float(v) for v in arg("--tgt").split(",")); S["fov"] = arg("--fov", S["fov"], float)
        S["fstop"] = arg("--fstop", None, float)
    elif "--fstop" in ARGS:
        S = dict(S); S["fstop"] = arg("--fstop", None, float)
    if "pos" in S:
        pos, tgt = Vector(S["pos"]), Vector(S["target"])
    else:
        tgt = Vector(S["target"]); pos = tgt + dvec(*S["dirn"]) * S["dist"]
    camera(tuple(pos), tuple(tgt), S["fov"], fstop=S["fstop"], focus=(tgt - pos).length)


if __name__ == "__main__":
    t0 = time.time()
    name = arg("--still", "hook")
    S = STILLS[name]
    parts = build(arg("--level", S["level"]))
    print(f"build {time.time()-t0:.1f} s", flush=True)
    pose(parts, arg("--s", S["s"], float))
    render_settings(arg("--samples", 32, int), arg("--res", 0.5, float))
    still_camera(S)
    out = arg("--out", os.path.join(ROOT, f"out/look/{name}.png"))
    if "--blend" in ARGS:
        bpy.ops.wm.save_as_mainfile(filepath=arg("--blend"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.context.scene.render.filepath = out
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"render {time.time()-t1:.1f} s -> {out}", flush=True)
    for k in range(arg("--repeat", 0, int)):       # timing test: re-render with the chain advanced 1/30 s each time
        pose(parts, arg("--s", S["s"], float) + (k + 1) / 30.0)
        t1 = time.time()
        bpy.context.scene.render.filepath = out.replace(".png", f"_r{k}.png")
        bpy.ops.render.render(write_still=True)
        print(f"render(repeat {k}) {time.time()-t1:.1f} s", flush=True)
