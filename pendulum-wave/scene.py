"""Blender scene for "20 pendulums, 1 push". Procedural only: no image textures, no assets.
Every pendulum angle, the board, the flashes and the camera are read from cache/anim.json (timeline.py) and keyed per
frame, so Cycles can motion-blur between them. Resumable: frames already on disk are skipped.

  $BLENDER -b --factory-startup --python scene.py -- --a 0 --b 1932 --res 1.0 --samples 32 --dir cache/raw
  $BLENDER -b --factory-startup --python scene.py -- --list 510,960,1860 --res 1.0 --samples 32 --dir cache/check
"""
import json, math, os, sys, time
import bpy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


A = json.load(open(os.path.join(HERE, "cache/anim.json")))
L, ROW_X, ZP = A["L"], A["row_x"], A["zp"]
NP = len(L)
R_BOB = 0.019
A_STR = 0.016            # half-spacing of the two strings of a bob on the bar (spacing 40 mm)
R_STR = 0.00055
X0, X1 = -0.11, ROW_X[-1] + 0.11

# ---------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"


def mat(name, base, rough=0.5, metal=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if "Coat Weight" in p.inputs: p.inputs["Coat Weight"].default_value = coat
    if "Specular IOR Level" in p.inputs: p.inputs["Specular IOR Level"].default_value = spec
    return m


def wood_mat(name, c1, c2, stretch=(0.35, 9.0, 9.0), contrast=0.55):
    """procedural grain: noise stretched along the board's length (x) -> streaks with no regular period (no moire)"""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; Lk = nt.links
    p = N["Principled BSDF"]; p.inputs["Roughness"].default_value = 0.5
    tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = stretch
    ns = N.new("ShaderNodeTexNoise"); ns.inputs["Scale"].default_value = 4.0; ns.inputs["Detail"].default_value = 6.0
    ns.inputs["Roughness"].default_value = 0.55
    ramp = N.new("ShaderNodeMapRange"); ramp.inputs["From Min"].default_value = 0.5 - contrast / 2
    ramp.inputs["From Max"].default_value = 0.5 + contrast / 2
    mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"
    mx.inputs[6].default_value = (*c1, 1); mx.inputs[7].default_value = (*c2, 1)
    Lk.new(tc.outputs["Object"], mp.inputs["Vector"]); Lk.new(mp.outputs["Vector"], ns.inputs["Vector"])
    Lk.new(ns.outputs["Fac"], ramp.inputs["Value"]); Lk.new(ramp.outputs["Result"], mx.inputs["Factor"])
    Lk.new(mx.outputs[2], p.inputs["Base Color"])
    return m


def box(name, x0, x1, y0, y1, z0, z1, m, bevel=0.003):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.object; ob.name = name; ob.scale = (x1 - x0, y1 - y0, z1 - z0)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = ob.modifiers.new("bv", "BEVEL"); bv.width = bevel; bv.segments = 3
    ob.data.materials.append(m)
    return ob


def rod(name, p0, p1, r, m, verts=12):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(p0 + p1) / 2)
    ob = bpy.context.object; ob.name = name
    ob.rotation_mode = "QUATERNION"; ob.rotation_quaternion = d.to_track_quat("Z", "Y")
    ob.data.materials.append(m)
    for pg in ob.data.polygons: pg.use_smooth = True
    return ob


# ---------------------------------------------------------------- materials
M_BASE = wood_mat("walnut", (0.045, 0.027, 0.017), (0.085, 0.052, 0.03))
M_STEEL = mat("steel", (0.62, 0.62, 0.64), rough=0.28, metal=1.0)
M_STR = mat("string", (0.05, 0.05, 0.055), rough=0.6)
M_BOARD = bpy.data.materials.new("acrylic"); M_BOARD.use_nodes = True
_p = M_BOARD.node_tree.nodes["Principled BSDF"]
_p.inputs["Base Color"].default_value = (0.92, 0.97, 1.0, 1); _p.inputs["Roughness"].default_value = 0.02
_p.inputs["Transmission Weight"].default_value = 1.0; _p.inputs["IOR"].default_value = 1.49
M_BACK = mat("backdrop", (0.46, 0.43, 0.39), rough=0.95, spec=0.2)
M_TABLE = wood_mat("table", (0.13, 0.10, 0.075), (0.17, 0.13, 0.10), stretch=(0.25, 4.0, 4.0), contrast=0.4)


def bob_mat(k):
    import colorsys
    h = 0.02 + 0.62 * k / (NP - 1)                 # red-orange (longest) ... blue (shortest)
    r, g, b = colorsys.hsv_to_rgb(h, 0.95, 0.85)
    lin = lambda c: c ** 2.2
    m = mat(f"bob{k}", (lin(r), lin(g), lin(b)), rough=0.32, coat=0.25)
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Emission Color"].default_value = (lin(r), lin(g), lin(b), 1); p.inputs["Emission Strength"].default_value = 0.0
    return m


def glow_mat(name, col, strength):
    """transparent + emission with a soft radial falloff (object coordinates); invisible when the strength is 0"""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; Lk = nt.links
    for n in list(N): N.remove(n)
    out = N.new("ShaderNodeOutputMaterial"); em = N.new("ShaderNodeEmission"); tr = N.new("ShaderNodeBsdfTransparent")
    add = N.new("ShaderNodeAddShader"); tc = N.new("ShaderNodeTexCoord"); gr = N.new("ShaderNodeTexGradient")
    gr.gradient_type = "SPHERICAL"
    pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 2.2
    mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = strength
    em.inputs["Color"].default_value = (*col, 1)
    Lk.new(tc.outputs["Object"], gr.inputs["Vector"]); Lk.new(gr.outputs["Fac"], pw.inputs[0]); Lk.new(pw.outputs[0], mul.inputs[0])
    Lk.new(mul.outputs[0], em.inputs["Strength"])
    Lk.new(tr.outputs[0], add.inputs[0]); Lk.new(em.outputs[0], add.inputs[1]); Lk.new(add.outputs[0], out.inputs["Surface"])
    return m, mul


# ---------------------------------------------------------------- set: a table in a light room (walls behind -y, beyond +x and -x)
box("table", -4.0, 6.0, -2.6, 3.0, -0.04, 0.0, M_TABLE, bevel=0)
import bmesh


def wall(name, p0, p1, h=3.5):
    bm = bmesh.new()
    v = [bm.verts.new((p0[0], p0[1], 0.0)), bm.verts.new((p1[0], p1[1], 0.0)), bm.verts.new((p1[0], p1[1], h)), bm.verts.new((p0[0], p0[1], h))]
    bm.faces.new(v)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); me.materials.append(M_BACK)
    return ob


wall("wall_back", (-4.0, -1.9), (6.0, -1.9))
wall("wall_far", (3.6, -2.6), (3.6, 3.0))
wall("wall_near", (-2.8, 3.0), (-2.8, -2.6))

# ---------------------------------------------------------------- the rig
box("base", X0, X1, -0.17, 0.17, 0.0, 0.028, M_BASE)
for x in (X0 + 0.03, X1 - 0.03):          # posts at the two ends of the row
    rod(f"post{x:.2f}", (x, 0, 0.028), (x, 0, ZP + 0.02), 0.011, M_STEEL, 24)
    rod(f"cap{x:.2f}", (x, 0, ZP + 0.02), (x, 0, ZP + 0.026), 0.014, M_STEEL, 24)
    rod(f"foot{x:.2f}", (x, 0, 0.028), (x, 0, 0.034), 0.022, M_STEEL, 24)
rod("bar", (X0 + 0.015, 0, ZP + 0.004), (X1 - 0.015, 0, ZP + 0.004), 0.004, M_STEEL, 24)   # the pivot bar: thin, so a top view sees past it
# the centre line: a thin glowing strip on the base, right under the rest position
M_LINE = bpy.data.materials.new("line"); M_LINE.use_nodes = True
_pl = M_LINE.node_tree.nodes["Principled BSDF"]; _pl.inputs["Base Color"].default_value = (0.9, 0.85, 0.75, 1)
_pl.inputs["Emission Color"].default_value = (1.0, 0.86, 0.66, 1); _pl.inputs["Emission Strength"].default_value = 0.8
box("line", ROW_X[0] - 0.05, ROW_X[-1] + 0.05, -0.011, 0.011, 0.028, 0.0286, M_LINE, bevel=0)
spots = []
import colorsys
for k in range(NP):
    hh = 0.02 + 0.62 * k / (NP - 1); rr, gg, bb = colorsys.hsv_to_rgb(hh, 0.6, 1.0)
    bpy.ops.mesh.primitive_circle_add(vertices=32, radius=1.0, fill_type="TRIFAN", location=(ROW_X[k], 0, 0.0292))
    sp = bpy.context.object; sp.name = f"spot{k}"
    m_sp, em = glow_mat(f"spot{k}", (rr ** 2.2, gg ** 2.2, bb ** 2.2), 0.0)
    sp.data.materials.append(m_sp); sp.scale = (0.030, 0.030, 1)
    sp.visible_shadow = False
    spots.append(em)

pend = []; bob_em = []
for k in range(NP):
    e = bpy.data.objects.new(f"pivot{k}", None); sc.collection.objects.link(e)
    e.location = (ROW_X[k], 0, ZP); e.rotation_mode = "XYZ"
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=R_BOB, location=(0, 0, -L[k]))
    b = bpy.context.object; b.name = f"bob{k}"; bm_k = bob_mat(k); b.data.materials.append(bm_k)
    bob_em.append(bm_k.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"])
    for pg in b.data.polygons: pg.use_smooth = True
    b.parent = e
    for s in (-1, 1):
        st = rod(f"str{k}{s}", (s * A_STR, 0, -0.002), (0, 0, -L[k] + R_BOB * 0.6), R_STR, M_STR, 6)
        st.parent = e
        ey = rod(f"eye{k}{s}", (s * A_STR, 0, 0.0), (s * A_STR, 0, -0.004), 0.0022, M_STEEL, 10)
        ey.parent = e
    pend.append(e)

# the push board: a flat vertical panel parallel to the row; its face (local y = 0) is keyed to board_y
XM = (ROW_X[0] + ROW_X[-1]) / 2
be = bpy.data.objects.new("board_mover", None); sc.collection.objects.link(be)
be.location = (0, -0.30, 0)
pn = box("board", X0 + 0.055, X1 - 0.055, -0.008, 0.0, 0.085, 0.54, M_BOARD, bevel=0.002)
pn.parent = be
for x in (X0 + 0.07, X1 - 0.07):          # two handles on its back
    h = rod(f"handle{x:.2f}", (x, -0.008, 0.40), (x, -0.10, 0.40), 0.006, M_STEEL, 12); h.parent = be

# ---------------------------------------------------------------- camera, lights, world
cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data); sc.collection.objects.link(cam)
sc.camera = cam; cam_data.sensor_fit = "VERTICAL"; cam_data.clip_start = 0.02
cam.rotation_mode = "QUATERNION"


def area(name, loc, target, size, energy, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA"); ld.size = size; ld.energy = energy; ld.color = color
    ob = bpy.data.objects.new(name, ld); sc.collection.objects.link(ob)
    ob.location = loc; ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y")
    return ob


area("key", (1.05, 1.05, 2.7), (0.38, 0, 0.2), 0.35, 150, (1.0, 0.95, 0.88))   # soft, a little off overhead: floor shadows
area("fill", (-1.4, 1.2, 1.4), (0.38, 0, 0.35), 2.0, 45, (0.85, 0.9, 1.0))
area("wash", (1.2, 1.0, 3.0), (1.5, -1.9, 1.0), 3.0, 110, (1.0, 0.95, 0.88))
area("rim", (0.6, -1.2, 1.8), (0.55, 0, 0.4), 1.0, 110, (1.0, 0.97, 0.92))
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.40, 0.38, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12

# ---------------------------------------------------------------- keys from the timeline
FR = A["frames"]
q_prev = None
cam_data.dof.use_dof = True
for f, fr in enumerate(FR):
    for k, e in enumerate(pend):
        e.rotation_euler = (fr["th"][k], 0, 0); e.keyframe_insert("rotation_euler", index=0, frame=f)
    be.location = (0, fr["board_y"], 0); be.keyframe_insert("location", index=1, frame=f)
    pos, tgt, fov, up = fr["pos"], fr["target"], fr["fov"], fr["up"]
    p = Vector(pos); cam.location = p
    fwd = (Vector(tgt) - p).normalized(); xr = fwd.cross(Vector(up)).normalized(); yu = xr.cross(fwd)
    q = Matrix((xr, yu, -fwd)).transposed().to_quaternion()
    if q_prev is not None and q.dot(q_prev) < 0: q.negate()
    q_prev = q.copy(); cam.rotation_quaternion = q
    cam_data.angle_y = math.radians(fov)
    cam_data.dof.aperture_fstop = fr["fstop"]; cam_data.dof.focus_distance = fr["focus"]
    cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_quaternion", frame=f)
    cam_data.keyframe_insert("lens", frame=f)
    cam_data.dof.keyframe_insert("aperture_fstop", frame=f); cam_data.dof.keyframe_insert("focus_distance", frame=f)
    for k in range(NP):
        bob_em[k].default_value = 1.75 * fr["flash"][k]; bob_em[k].keyframe_insert("default_value", frame=f)
        spots[k].inputs[1].default_value = 20.0 * fr["flash"][k]; spots[k].inputs[1].keyframe_insert("default_value", frame=f)

# ---------------------------------------------------------------- render settings
res = arg("--res", 0.5, float)
sc.render.engine = "CYCLES"
sc.render.resolution_x, sc.render.resolution_y = 1080, 1920
sc.render.resolution_percentage = int(round(res * 100))
sc.cycles.samples = arg("--samples", 16, int)
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 12
sc.cycles.transmission_bounces = 12
sc.cycles.glossy_bounces = 4
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.3
sc.render.film_transparent = False
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy" if arg("--look") is None else arg("--look")
sc.render.image_settings.file_format = "PNG"
sc.render.fps = A["fps"]
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"; prefs.get_devices()
    for d in prefs.devices: d.use = True
    sc.cycles.device = "GPU"
except Exception as ex:
    print("GPU setup failed:", ex)

outdir = os.path.join(HERE, arg("--dir", "cache/raw")); os.makedirs(outdir, exist_ok=True)
if "--list" in ARGS:
    todo = [int(v) for v in arg("--list").split(",")]
else:
    todo = list(range(arg("--a", 0, int), min(arg("--b", len(FR), int), len(FR))))
todo = [f for f in todo if not os.path.exists(os.path.join(outdir, f"{f:05d}.png"))]
print(f"{len(todo)} frames to render in {outdir}", flush=True)
t0 = time.time()
for n, f in enumerate(todo):
    sc.frame_set(f)
    path = os.path.join(outdir, f"{f:05d}.png")
    sc.render.filepath = path + ".tmp.png"
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    os.replace(path + ".tmp.png", path)
    if n % 10 == 0 or n == len(todo) - 1:
        print(f"frame {f}: {time.time()-t1:.1f} s ({n+1}/{len(todo)}, {(time.time()-t0)/(n+1):.1f} s avg)", flush=True)
