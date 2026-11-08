"""Static props, built procedurally at true size (metres). None of them is part of the physics."""
import math, random
import bpy, bmesh
from mathutils import Matrix, Vector, Euler, noise
import bl_util as U

RNG = random.Random(11)


# ------------------------------------------------------------------------------------------------ materials
def mat_steel_brushed():
    m, nt, p = U.new_mat("steel_brushed")
    p.inputs["Base Color"].default_value = (0.70, 0.70, 0.70, 1)
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.42
    p.inputs["Anisotropic"].default_value = 0.8
    p.inputs["Roughness"].default_value = 0.42
    tc = U.node(nt, "ShaderNodeTexCoord"); mp = U.node(nt, "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (20.0, 6000.0, 1.0)
    U.link(nt, tc.outputs["Object"], mp.inputs[0])
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.0; nz.inputs["Detail"].default_value = 2
    U.link(nt, mp.outputs[0], nz.inputs[0])
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.00002
    U.link(nt, nz.outputs["Fac"], bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    tg = U.node(nt, "ShaderNodeTangent"); tg.direction_type = "RADIAL"; tg.axis = "Y"
    U.link(nt, tg.outputs[0], p.inputs["Tangent"])
    return m


def mat_coin():
    """aluminium-bronze: polished highs, darker patina in the recesses (ambient occlusion), light wear"""
    m, nt, p = U.new_mat("coin_metal")
    ao = U.node(nt, "ShaderNodeAmbientOcclusion"); ao.inputs["Distance"].default_value = 0.0005
    ao.only_local = True; ao.samples = 8
    ramp = U.node(nt, "ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[0].color = (0.36, 0.26, 0.14, 1)
    ramp.color_ramp.elements[1].position = 0.95; ramp.color_ramp.elements[1].color = (0.86, 0.68, 0.40, 1)
    U.link(nt, ao.outputs["AO"], ramp.inputs[0])
    tc = U.node(nt, "ShaderNodeTexCoord")
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 900.0; nz.inputs["Detail"].default_value = 8
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    mix = U.node(nt, "ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.25
    U.link(nt, ramp.outputs[0], mix.inputs[6]); U.link(nt, nz.outputs["Color"], mix.inputs[7])
    U.link(nt, mix.outputs[2], p.inputs["Base Color"])
    p.inputs["Metallic"].default_value = 1.0
    rr = U.math_node(nt, "MULTIPLY_ADD", ao.outputs["AO"], None)
    r2 = nt.nodes.new("ShaderNodeMath"); r2.operation = "MULTIPLY_ADD"
    U.link(nt, ao.outputs["AO"], r2.inputs[0]); r2.inputs[1].default_value = -0.35; r2.inputs[2].default_value = 0.62
    U.link(nt, r2.outputs[0], p.inputs["Roughness"])
    # reeded edge + fine wear scratches as bump: sin(angle * 160) on the side, noise everywhere
    sep = U.node(nt, "ShaderNodeSeparateXYZ"); U.link(nt, tc.outputs["Object"], sep.inputs[0])
    ang = U.math_node(nt, "ARCTAN2", sep.outputs["Y"], sep.outputs["X"])
    reed = U.math_node(nt, "SINE", U.math_node(nt, "MULTIPLY", ang, vb=160.0))
    rad = U.math_node(nt, "SQRT", U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", sep.outputs["X"], sep.outputs["X"]),
                                               U.math_node(nt, "MULTIPLY", sep.outputs["Y"], sep.outputs["Y"])))
    side = U.math_node(nt, "GREATER_THAN", rad, vb=0.01195)
    h = U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", reed, side), U.math_node(nt, "MULTIPLY", nz.outputs["Fac"], vb=0.3))
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.00004
    U.link(nt, h, bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    return m


def mat_wood(name, base=(0.62, 0.45, 0.28), ring=0.004, coat=0.3, axis="Z"):
    """wood with rings around an axis (object space) and fine grain"""
    m, nt, p = U.new_mat(name)
    tc = U.node(nt, "ShaderNodeTexCoord")
    sep = U.node(nt, "ShaderNodeSeparateXYZ"); U.link(nt, tc.outputs["Object"], sep.inputs[0])
    a, b = {"Z": ("X", "Y"), "X": ("Y", "Z"), "Y": ("X", "Z")}[axis]
    r = U.math_node(nt, "SQRT", U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", sep.outputs[a], sep.outputs[a]),
                                             U.math_node(nt, "MULTIPLY", sep.outputs[b], sep.outputs[b])))
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 40.0; nz.inputs["Detail"].default_value = 3
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    rw = U.math_node(nt, "ADD", r, U.math_node(nt, "MULTIPLY", nz.outputs["Fac"], vb=ring * 1.2))
    s = U.math_node(nt, "SINE", U.math_node(nt, "MULTIPLY", rw, vb=2 * math.pi / ring))
    f = nt.nodes.new("ShaderNodeMath"); f.operation = "MULTIPLY_ADD"
    U.link(nt, s, f.inputs[0]); f.inputs[1].default_value = 0.09; f.inputs[2].default_value = 0.91
    comb = U.node(nt, "ShaderNodeCombineXYZ")
    for k in range(3):
        mm = U.math_node(nt, "MULTIPLY", f.outputs[0], vb=base[k]); U.link(nt, mm, comb.inputs[k])
    U.link(nt, comb.outputs[0], p.inputs["Base Color"])
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = ring * 0.02
    U.link(nt, s, bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.55
    p.inputs["Coat Weight"].default_value = coat; p.inputs["Coat Roughness"].default_value = 0.12
    return m


def mat_tiles(name, base=(0.60, 0.30, 0.22)):
    m, nt, p = U.new_mat(name)
    tc = U.node(nt, "ShaderNodeTexCoord")
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3.0; nz.inputs["Detail"].default_value = 4
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    vr = U.node(nt, "ShaderNodeTexWhiteNoise"); vr.noise_dimensions = "1D"
    oi = U.node(nt, "ShaderNodeObjectInfo")
    mix = U.node(nt, "ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.45
    mix.inputs[6].default_value = (*base, 1)
    U.link(nt, nz.outputs["Color"], mix.inputs[7])
    U.link(nt, mix.outputs[2], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.6
    return m


def mat_plaster(name, base=(0.90, 0.88, 0.83)):
    m, nt, p = U.new_mat(name)
    tc = U.node(nt, "ShaderNodeTexCoord")
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 60.0; nz.inputs["Detail"].default_value = 10
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    nz2 = U.node(nt, "ShaderNodeTexNoise"); nz2.inputs["Scale"].default_value = 1.5; nz2.inputs["Detail"].default_value = 3
    U.link(nt, tc.outputs["Object"], nz2.inputs[0])
    f = U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", nz2.outputs["Fac"], vb=0.10), vb=0.95)
    comb = U.node(nt, "ShaderNodeCombineXYZ")
    for k in range(3):
        U.link(nt, U.math_node(nt, "MULTIPLY", f, vb=base[k]), comb.inputs[k])
    U.link(nt, comb.outputs[0], p.inputs["Base Color"])
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    U.link(nt, nz.outputs["Fac"], bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.85
    return m


def mat_siding(name, base=(0.90, 0.89, 0.85), board=0.16):
    """painted horizontal clapboard: board lines every 16 cm with a small shadow step, fine paint texture"""
    m, nt, p = U.new_mat(name)
    tc = U.node(nt, "ShaderNodeTexCoord")
    sep = U.node(nt, "ShaderNodeSeparateXYZ"); U.link(nt, tc.outputs["Object"], sep.inputs[0])
    fr = U.math_node(nt, "FRACT", U.math_node(nt, "DIVIDE", sep.outputs["Z"], vb=board))
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 80.0; nz.inputs["Detail"].default_value = 8
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    shade = U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", fr, vb=0.10), vb=0.88)
    comb = U.node(nt, "ShaderNodeCombineXYZ")
    for k in range(3):
        U.link(nt, U.math_node(nt, "MULTIPLY", shade, vb=base[k]), comb.inputs[k])
    U.link(nt, comb.outputs[0], p.inputs["Base Color"])
    h = U.math_node(nt, "ADD", fr, U.math_node(nt, "MULTIPLY", nz.outputs["Fac"], vb=0.05))
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.012
    U.link(nt, h, bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.6
    return m


def mat_glass(name="glass", tint=(0.92, 0.95, 0.96)):
    return U.principled(name, base=tint, rough=0.0, trans=1.0, ior=1.5)


def mat_brick(name="brick"):
    m, nt, p = U.new_mat(name)
    tc = U.node(nt, "ShaderNodeTexCoord")
    br = U.node(nt, "ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0; br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Brick Width"].default_value = 0.22; br.inputs["Row Height"].default_value = 0.075
    br.inputs["Color1"].default_value = (0.55, 0.26, 0.18, 1); br.inputs["Color2"].default_value = (0.45, 0.22, 0.16, 1)
    br.inputs["Mortar"].default_value = (0.70, 0.68, 0.64, 1)
    sep = U.node(nt, "ShaderNodeSeparateXYZ"); U.link(nt, tc.outputs["Object"], sep.inputs[0])
    comb = U.node(nt, "ShaderNodeCombineXYZ")
    U.link(nt, U.math_node(nt, "ADD", sep.outputs["X"], sep.outputs["Y"]), comb.inputs[0])
    U.link(nt, sep.outputs["Z"], comb.inputs[1])
    U.link(nt, comb.outputs[0], br.inputs["Vector"])
    U.link(nt, br.outputs["Color"], p.inputs["Base Color"])
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Distance"].default_value = 0.004
    U.link(nt, br.outputs["Fac"], bump.inputs["Height"]); bump.invert = True
    U.link(nt, bump.outputs[0], p.inputs["Normal"])
    p.inputs["Roughness"].default_value = 0.9
    return m


# ------------------------------------------------------------------------------------------------ pencil (the pusher)
def build_pencil():
    """a sharpened hexagonal pencil, 7 mm across flats; tip at the local origin, body along +Z.
    The painted hexagon intersected with the sharpening cone gives the scalloped paint edge; faces are assigned
    by geometry afterwards: cone surface = wood, its first 3.5 mm = graphite, the rest = paint."""
    paint = U.principled("pencil_paint", base=(0.95, 0.62, 0.04), rough=0.28, coat=0.6, coat_rough=0.08)
    wood = mat_wood("pencil_wood", base=(0.92, 0.62, 0.36), ring=0.00045, coat=0.0, axis="Z")
    wood.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    graph = U.principled("graphite", base=(0.06, 0.06, 0.065), rough=0.30, metal=0.7)
    R_in = 0.0035
    R_hex = R_in / math.cos(math.pi / 6)
    L = 0.20; Lc = 0.020; Rc = 0.0040
    bm = bmesh.new()
    U.cyl(bm, (0, 0, L / 2), R_hex, R_hex, L, segs=6)
    U.bevel_all(bm, 0.00025, segs=2)
    body = U.obj_from_bm("pencil", bm, mats=[paint, wood, graph])
    # a finely ringed cone (small faces, so the graphite boundary is clean)
    cb = bmesh.new()
    zs = [0.0] + [0.00025 * k for k in range(1, 101)] + [L * 1.1]
    rings = []
    for z in zs:
        rr = Rc * z / Lc
        if z == 0.0:
            rings.append([cb.verts.new((0, 0, 0))])
        else:
            rings.append([cb.verts.new((rr * math.cos(2 * math.pi * k / 72), rr * math.sin(2 * math.pi * k / 72), z)) for k in range(72)])
    for k in range(72):
        cb.faces.new((rings[0][0], rings[1][k], rings[1][(k + 1) % 72]))
    for i in range(1, len(rings) - 1):
        for k in range(72):
            cb.faces.new((rings[i][k], rings[i + 1][k], rings[i + 1][(k + 1) % 72], rings[i][(k + 1) % 72]))
    cb.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(cb, faces=list(cb.faces))
    cone = U.obj_from_bm("pencil_cone", cb, mats=[wood])
    U.boolean(body, cone, "INTERSECT", transfer=False)
    U.remove(cone)
    me = body.data
    for poly in me.polygons:
        c = poly.center
        rad = math.hypot(c.x, c.y)
        on_cone = c.z < Lc * 1.05 and rad < R_in * 0.995 and abs(rad - Rc * c.z / Lc) < 0.00015
        if on_cone:
            poly.material_index = 2 if c.z < 0.0035 else 1
        else:
            poly.material_index = 0
    me.shade_smooth(); me.set_sharp_from_angle(angle=math.radians(30))
    return body


def place_pencil(ob, tip, tilt_deg=14, yaw_deg=25):
    t, y = math.radians(tilt_deg), math.radians(yaw_deg)
    back = Vector((-math.cos(t) * math.cos(y), -math.cos(t) * math.sin(y), math.sin(t)))
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = back.to_track_quat("Z", "Y")
    ob.location = tip


# ------------------------------------------------------------------------------------------------ rice
def build_rice(name, mat, seed):
    """a grain of rice, ~5.4-6.0 x 2.5 x 1.9 mm: an irregular, slightly flattened spindle with one end cut at an
    angle at the germ notch; sizes and shapes vary per grain"""
    r = random.Random(seed)
    a = 0.0029 * r.uniform(0.93, 1.05); b = 0.00125 * r.uniform(0.92, 1.08); c = 0.00095 * r.uniform(0.92, 1.06)
    bm = bmesh.new()
    U.sphere(bm, (0, 0, 0), (1, 1, 1), segs=(48, 24))
    off = Vector((r.random() * 10, r.random() * 10, r.random() * 10))
    cut_n = Vector((math.cos(math.radians(32)), math.sin(math.radians(32)), 0)).normalized()
    cut_d = 0.80 * r.uniform(0.96, 1.03)
    for v in bm.verts:
        p = v.co.copy()
        x, y, z = p
        # spindle: narrower towards both ends, a little more at one
        prof = (1 - 0.18 * x * x) * (1 - 0.06 * max(0.0, -x))
        n = noise.noise(p * 2.0 + off) * 0.03 + noise.noise(p * 6.5 + off) * 0.006
        q = Vector((x, y * prof, z * prof)) * (1 + n)
        # the angled germ end: everything beyond the cut plane is pulled back onto it (with a soft rounding)
        dd = q.dot(cut_n) - cut_d
        if dd > 0:
            q = q - cut_n * (dd * 0.85)
        v.co = Vector((q.x * a, q.y * b, q.z * c))
    return U.obj_from_bm(name, bm, mats=[mat], smooth=True), c


def mat_rice():
    m = U.principled("rice", base=(0.93, 0.92, 0.86), rough=0.45, sss=1.0, sss_radius=(1.0, 0.9, 0.7),
                     sss_scale=0.0009)
    nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    p.inputs["Coat Weight"].default_value = 0.0
    p.inputs["Specular IOR Level"].default_value = 0.35
    # faint lengthwise grooves of a polished grain
    tc = U.node(nt, "ShaderNodeTexCoord"); sep = U.node(nt, "ShaderNodeSeparateXYZ")
    U.link(nt, tc.outputs["Object"], sep.inputs[0])
    ang = U.math_node(nt, "ARCTAN2", sep.outputs["Z"], sep.outputs["Y"])
    gr = U.math_node(nt, "SINE", U.math_node(nt, "MULTIPLY", ang, vb=5.0))
    nz = U.node(nt, "ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 3000.0
    U.link(nt, tc.outputs["Object"], nz.inputs[0])
    h = U.math_node(nt, "ADD", U.math_node(nt, "MULTIPLY", gr, vb=0.3), nz.outputs["Fac"])
    bump = U.node(nt, "ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.00002
    U.link(nt, h, bump.inputs["Height"]); U.link(nt, bump.outputs[0], p.inputs["Normal"])
    return m


# ------------------------------------------------------------------------------------------------ ruler
def build_ruler(R):
    """a 300 mm steel ruler, 25 mm wide, 1 mm thick, lying along x; mm marks and numbers on the edge facing the
    chain (painted engraving, 6 um proud of the surface)"""
    steel = mat_steel_brushed()
    ink = U.principled("engraving", base=(0.025, 0.025, 0.028), rough=0.55)
    x0, x1, y0, y1 = R["x0"], R["x1"], R["y0"], R["y1"]
    bm = bmesh.new()
    U.box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, 0.0005), (x1 - x0, abs(y1 - y0), 0.001))
    U.bevel_all(bm, 0.00015, segs=2)
    ruler = U.obj_from_bm("ruler", bm, mats=[steel], smooth=True, weighted=True)
    mb = bmesh.new()
    edge = y0 - 0.0006
    zero = x0 + 0.005
    n_mm = int((x1 - 0.003 - zero) * 1000)
    for i in range(n_mm + 1):
        x = zero + i * 0.001
        ln = 0.0065 if i % 10 == 0 else (0.0045 if i % 5 == 0 else 0.003)
        U.box(mb, (x, edge - ln / 2, 0.001003), (0.00014, ln, 0.000006))
    marks = U.obj_from_bm("ruler_marks", mb, mats=[ink])
    nums = []
    for cm in range(0, n_mm // 10 + 1):
        cu = bpy.data.curves.new(f"num{cm}", "FONT")
        cu.body = str(cm); cu.size = 0.0026; cu.align_x = "CENTER"; cu.align_y = "CENTER"
        cu.extrude = 0.000003
        o = bpy.data.objects.new(f"num{cm}", cu); U.collection().objects.link(o)
        o.data.materials.append(ink)
        o.location = (zero + cm * 0.010, edge - 0.0095, 0.001003)
        o.rotation_euler = (0, 0, 0)
        nums.append(o)
    return ruler


# ------------------------------------------------------------------------------------------------ coin
def build_coin(cx, cy):
    """a generic 24 mm coin: raised rim, reeded edge, the numeral 10, a laurel wreath and a year. No country,
    no real design."""
    metal = mat_coin()
    R, T = 0.012, 0.0015
    bm = bmesh.new()
    U.cyl(bm, (0, 0, T / 2), R, R, T, segs=128)
    U.bevel_all(bm, 0.00012, segs=2)
    coin = U.obj_from_bm("coin", bm, mats=[metal], smooth=True, weighted=True)
    rb = bmesh.new()
    U.cyl(rb, (0, 0, T + 0.00006), R - 0.00005, R - 0.00005, 0.00024, segs=128)
    rim = U.obj_from_bm("coin_rim", rb, mats=[metal], smooth=True)
    hb = bmesh.new(); U.cyl(hb, (0, 0, T + 0.00006), R - 0.0011, R - 0.0011, 0.001, segs=128)
    hole = U.obj_from_bm("coin_hole", hb, mats=[metal])
    U.boolean(rim, hole, "DIFFERENCE"); U.remove(hole)
    rim.data.shade_smooth()
    # numerals "10", built from geometry so the 1 has a flag and a foot
    nb = bmesh.new()
    zt = T + 0.00006; hgt = 0.0060; th = 0.00012
    x1 = -0.0021
    U.box(nb, (x1, 0.0006, zt), (0.00085, hgt, th))                                   # stem of the 1
    U.box(nb, (x1 - 0.0008, 0.0006 + hgt / 2 - 0.0007, zt), (0.0019, 0.00075, th),
          rot=Euler((0, 0, math.radians(-35))).to_matrix())                           # flag
    U.box(nb, (x1, 0.0006 - hgt / 2 + 0.0003, zt), (0.0026, 0.0006, th))              # foot
    ring_o, ring_i = (0.00205, 0.0031), (0.00115, 0.0022)
    seg = 64
    vo, vi = [], []
    for k in range(seg):
        t = 2 * math.pi * k / seg
        for lst, (rx, ry) in ((vo, ring_o), (vi, ring_i)):
            lst.append((0.0021 + rx * math.cos(t), 0.0006 + ry * math.sin(t)))
    top = [nb.verts.new((x, y, zt + th / 2)) for x, y in vo]; topi = [nb.verts.new((x, y, zt + th / 2)) for x, y in vi]
    bot = [nb.verts.new((x, y, zt - th / 2)) for x, y in vo]; boti = [nb.verts.new((x, y, zt - th / 2)) for x, y in vi]
    for k in range(seg):
        k2 = (k + 1) % seg
        nb.faces.new((top[k], top[k2], topi[k2], topi[k]))
        nb.faces.new((bot[k], boti[k], boti[k2], bot[k2]))
        nb.faces.new((top[k], bot[k], bot[k2], top[k2]))
        nb.faces.new((topi[k], topi[k2], boti[k2], boti[k]))
    U.bevel_all(nb, 0.00003, segs=1)
    numer = U.obj_from_bm("coin_numeral", nb, mats=[metal], smooth=True, weighted=True)
    # laurel: two continuous branches, each a stem with paired leaves, meeting at the bottom
    lb = bmesh.new()
    rr = 0.0088
    for side in (-1, 1):
        n = 26
        prev = None
        for i in range(n + 1):
            t = i / n
            ang = -math.pi / 2 + side * (math.radians(8) + t * math.radians(118))
            p = Vector((rr * math.cos(ang), rr * math.sin(ang), T + 0.00004))
            if prev is not None:
                d = p - prev; L = d.length
                U.box(lb, (prev + p) / 2, (L * 1.05, 0.00018, 0.00008),
                      rot=Euler((0, 0, math.atan2(d.y, d.x))).to_matrix())
            prev = p
            if i % 2 == 0 and 0 < i < n:
                tang = Vector((-math.sin(ang), math.cos(ang), 0)) * side
                for off in (-1, 1):
                    outv = Vector((math.cos(ang), math.sin(ang), 0)) * off
                    leaf_dir = (tang * 0.75 + outv * 0.65).normalized()
                    c = p + leaf_dir * 0.00062
                    U.sphere(lb, c, (0.00068, 0.00024, 0.00009), segs=(14, 6),
                             rot=Euler((0, 0, math.atan2(leaf_dir.y, leaf_dir.x))).to_matrix())
            if i == n:   # a berry-like tip
                U.sphere(lb, p + tang * 0.0004, (0.0003, 0.0003, 0.0001), segs=(10, 5))
    U.sphere(lb, (0, -rr - 0.0001, T + 0.00005), (0.0005, 0.00035, 0.00011), segs=(12, 6))   # the tie
    leaves = U.obj_from_bm("coin_wreath", lb, mats=[metal], smooth=True)
    texts = [numer]
    cu = bpy.data.curves.new("ctext", "FONT"); cu.body = "2026"; cu.size = 0.0021
    cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.extrude = 0.00006; cu.space_character = 1.15
    o = bpy.data.objects.new("ctext", cu); U.collection().objects.link(o); o.data.materials.append(metal)
    o.location = (0, -0.0047, T + 0.00006); texts.append(o)
    for o in [rim, leaves] + texts:
        o.parent = coin
    coin.location = (cx, cy, 0)
    coin.rotation_euler = (0, 0, math.radians(-30))
    return coin


# ------------------------------------------------------------------------------------------------ mug
def build_mug(cx, cy):
    glaze = U.principled("glaze", base=(0.62, 0.72, 0.74), rough=0.12, coat=0.6, coat_rough=0.03)
    Ro, Ri, H = 0.041, 0.037, 0.095
    bm = bmesh.new(); U.cyl(bm, (0, 0, H / 2), Ro, Ro * 0.97, H, segs=96)
    mug = U.obj_from_bm("mug", bm, mats=[glaze])
    ib = bmesh.new(); U.cyl(ib, (0, 0, H / 2 + 0.006), Ri, Ri * 0.97, H, segs=96)
    inner = U.obj_from_bm("mug_in", ib, mats=[glaze])
    U.boolean(mug, inner); U.remove(inner)
    # handle: a tube along a half-ellipse
    hb = bmesh.new()
    rings = []
    for i in range(25):
        t = math.pi * (-0.5 + i / 24.0)
        c = Vector((Ro - 0.004 + 0.026 * math.cos(t), 0, H * 0.52 + 0.030 * math.sin(t)))
        tang = Vector((-0.026 * math.sin(t), 0, 0.030 * math.cos(t))).normalized()
        q = tang.to_track_quat("Z", "Y").to_matrix()
        ring = []
        for k in range(16):
            a = 2 * math.pi * k / 16
            ring.append(hb.verts.new(c + q @ Vector((0.0045 * math.cos(a), 0.0065 * math.sin(a), 0))))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(16):
            hb.faces.new((rings[i][k], rings[i][(k + 1) % 16], rings[i + 1][(k + 1) % 16], rings[i + 1][k]))
    handle = U.obj_from_bm("mug_handle", hb, mats=[glaze], smooth=True)
    handle.parent = mug
    mug.data.shade_smooth(); mug.data.set_sharp_from_angle(angle=math.radians(50))
    mug.location = (cx, cy, 0); mug.rotation_euler = (0, 0, math.radians(200))
    return mug


# ------------------------------------------------------------------------------------------------ dust
def build_dust(region, n=60, seed=4):
    r = random.Random(seed)
    dust = U.principled("dust", base=(0.70, 0.68, 0.64), rough=1.0)
    bm = bmesh.new()
    x0, x1, y0, y1 = region
    for i in range(n):
        x, y = r.uniform(x0, x1), r.uniform(y0, y1)
        if r.random() < 0.75:
            s = r.uniform(0.000012, 0.00005)
            U.sphere(bm, (x, y, s * 0.6), (s, s * r.uniform(0.6, 1.0), s * 0.6), segs=(8, 5))
        else:
            ln = r.uniform(0.0003, 0.0012); a = r.uniform(0, math.pi)
            U.cyl(bm, (x, y, 0.000006), 0.000005, 0.000005, ln, segs=5,
                  rot=Euler((math.pi / 2, 0, a)).to_matrix())
    return U.obj_from_bm("dust", bm, mats=[dust])


# ------------------------------------------------------------------------------------------------ chair
def build_chair(cx, cy):
    wood = mat_wood("chair_wood", base=(0.66, 0.47, 0.29), ring=0.006, coat=0.35, axis="X")
    bm = bmesh.new()
    U.box(bm, (0, 0, 0.445), (0.44, 0.42, 0.024))
    for sx in (-1, 1):
        for sy in (-1, 1):
            back = sy > 0
            top = 0.93 if back else 0.433
            lean = Euler((math.radians(-6) if back else 0, 0, 0)).to_matrix()
            c = (sx * 0.195, sy * 0.185, top / 2)
            U.cyl(bm, c, 0.017, 0.013 if not back else 0.014, top, segs=16, rot=lean if back else None)
    for z, hgt in ((0.62, 0.05), (0.76, 0.05), (0.88, 0.07)):
        U.box(bm, (0, 0.185 + (z - 0.44) * math.tan(math.radians(6)), z), (0.37, 0.018, hgt))
    for z in (0.16,):
        U.cyl(bm, (0, -0.185, z), 0.009, 0.009, 0.37, segs=12, rot=Euler((0, math.pi / 2, 0)).to_matrix())
        U.cyl(bm, (0, 0.185, z), 0.009, 0.009, 0.37, segs=12, rot=Euler((0, math.pi / 2, 0)).to_matrix())
        for sx in (-1, 1):
            U.cyl(bm, (sx * 0.195, 0, z + 0.06), 0.009, 0.009, 0.35, segs=12, rot=Euler((math.pi / 2, 0, 0)).to_matrix())
    U.bevel_all(bm, 0.003, segs=2)
    ch = U.obj_from_bm("chair", bm, mats=[wood], smooth=True, weighted=True)
    ch.location = (cx, cy, 0)
    return ch


# ------------------------------------------------------------------------------------------------ lamp post
def build_lamp(cx, cy):
    paint = U.principled("lamp_paint", base=(0.05, 0.075, 0.065), rough=0.35, metal=0.6, coat=0.3)
    glass = mat_glass("lamp_glass", tint=(0.97, 0.97, 0.94))
    bulb = U.principled("bulb", base=(0.95, 0.93, 0.86), rough=0.2, trans=0.6)
    bm = bmesh.new()
    U.cyl(bm, (0, 0, 0.12), 0.24, 0.22, 0.24, segs=8)
    U.cyl(bm, (0, 0, 0.30), 0.17, 0.12, 0.14, segs=24)
    U.cyl(bm, (0, 0, 0.42), 0.10, 0.075, 0.12, segs=24)
    U.cyl(bm, (0, 0, 2.0), 0.065, 0.05, 3.1, segs=32)
    for z in (0.55, 3.45):
        U.cyl(bm, (0, 0, z), 0.085, 0.085, 0.05, segs=24)
    for k in range(16):                                # flutes
        a = 2 * math.pi * k / 16
        U.box(bm, (0.061 * math.cos(a), 0.061 * math.sin(a), 1.6), (0.012, 0.012, 2.0), rot=Euler((0, 0, a)).to_matrix())
    U.cyl(bm, (0, 0, 3.55), 0.05, 0.12, 0.18, segs=24)
    U.box(bm, (0, 0, 3.66), (0.34, 0.34, 0.04))
    for sx in (-1, 1):
        for sy in (-1, 1):
            U.box(bm, (sx * 0.155, sy * 0.155, 3.92), (0.022, 0.022, 0.50))
    U.box(bm, (0, 0, 4.18), (0.38, 0.38, 0.03))
    U.cyl(bm, (0, 0, 4.30), 0.27, 0.0, 0.22, segs=4, rot=Euler((0, 0, math.pi / 4)).to_matrix())
    U.sphere(bm, (0, 0, 4.45), (0.035, 0.035, 0.035))
    U.bevel_all(bm, 0.003, segs=1)
    lamp = U.obj_from_bm("lamp", bm, mats=[paint], smooth=True, weighted=True)
    gb = bmesh.new()
    for a in range(4):
        rot = Euler((0, 0, a * math.pi / 2)).to_matrix()
        U.box(gb, rot @ Vector((0.15, 0, 3.92)), (0.006, 0.28, 0.48), rot=rot)
    g = U.obj_from_bm("lamp_glass", gb, mats=[glass]); g.parent = lamp
    bb = bmesh.new(); U.sphere(bb, (0, 0, 3.88), (0.05, 0.05, 0.07))
    b = U.obj_from_bm("lamp_bulb", bb, mats=[bulb], smooth=True); b.parent = lamp
    lamp.location = (cx, cy, 0)
    return lamp


# ------------------------------------------------------------------------------------------------ kerb
def build_kerb(y_edge, x0=-30, x1=90):
    gran = U.principled("granite", base=(0.62, 0.62, 0.60), rough=0.75)
    m = gran; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    tc = U.node(nt, "ShaderNodeTexCoord")
    vo = U.node(nt, "ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 400.0
    U.link(nt, tc.outputs["Object"], vo.inputs[0])
    mix = U.node(nt, "ShaderNodeMix"); mix.data_type = "RGBA"; mix.inputs["Factor"].default_value = 0.35
    mix.inputs[6].default_value = (0.64, 0.63, 0.61, 1)
    U.link(nt, vo.outputs["Color"], mix.inputs[7]); U.link(nt, mix.outputs[2], p.inputs["Base Color"])
    bm = bmesh.new()
    x = x0
    while x < x1:
        for sy in (-1, 1):
            U.box(bm, (x + 0.495, sy * (y_edge + 0.075), 0.05), (0.985, 0.15, 0.10))
        x += 1.0
    U.bevel_all(bm, 0.008, segs=2)
    return U.obj_from_bm("kerb", bm, mats=[gran], smooth=True, weighted=True)


# ------------------------------------------------------------------------------------------------ fence, gate, bicycle
def _tube_ring(bm, center, R, r, axis_rot, segs=48, sides=10):
    """a torus (ring tube) of major radius R and tube radius r, in the plane given by axis_rot (local xz plane)"""
    rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        c = Vector((R * math.cos(a), 0, R * math.sin(a)))
        t = Vector((-math.sin(a), 0, math.cos(a)))
        n = Vector((math.cos(a), 0, math.sin(a))); b = Vector((0, 1, 0))
        ring = [bm.verts.new(Vector(center) + axis_rot @ (c + (n * math.cos(2 * math.pi * k / sides) + b * math.sin(2 * math.pi * k / sides)) * r))
                for k in range(sides)]
        rings.append(ring)
    for i in range(segs):
        j = (i + 1) % segs
        for k in range(sides):
            k2 = (k + 1) % sides
            bm.faces.new((rings[i][k], rings[j][k], rings[j][k2], rings[i][k2]))


def _rod(bm, p0, p1, r, segs=12):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    U.cyl(bm, (p0 + p1) / 2, r, r, d.length, segs=segs, rot=U.rot_to(d))


def build_fence(y, x0, x1, gate=(5.0, 6.0)):
    """a painted wooden picket fence, 1.1 m, with posts, two rails and a garden gate (1.15 m)"""
    paint = U.principled("fence_paint", base=(0.88, 0.85, 0.78), rough=0.55)
    gatep = U.principled("gate_paint", base=(0.52, 0.58, 0.50), rough=0.5)
    metal = U.principled("gate_metal", base=(0.10, 0.10, 0.10), rough=0.4, metal=1.0)
    bm = bmesh.new(); gb = bmesh.new(); mb = bmesh.new()
    x = x0
    while x <= x1 + 1e-6:                        # posts every 2 m
        if not (gate[0] - 0.05 < x < gate[1] + 0.05):
            U.box(bm, (x, y, 0.62), (0.09, 0.09, 1.24))
            U.cyl(bm, (x, y, 1.27), 0.065, 0.0, 0.08, segs=4, rot=Euler((0, 0, math.pi / 4)).to_matrix())
        x += 2.0
    for gx in gate:
        U.box(bm, (gx + (-0.06 if gx == gate[0] else 0.06), y, 0.66), (0.10, 0.10, 1.32))
    for z in (0.25, 0.85):
        for (a, b) in ((x0, gate[0] - 0.11), (gate[1] + 0.11, x1)):
            U.box(bm, ((a + b) / 2, y + 0.04, z), (b - a, 0.022, 0.07))
    x = x0 + 0.08
    while x < x1:
        if not (gate[0] - 0.12 < x < gate[1] + 0.12):
            U.box(bm, (x, y + 0.065, 0.53), (0.085, 0.022, 1.06))
            U.box(bm, (x, y + 0.065, 1.075), (0.06, 0.022, 0.06), rot=Euler((0, math.pi / 4, 0)).to_matrix())
        x += 0.15
    # the gate: pickets, rails and a Z brace, hinges and a latch
    g0, g1 = gate[0] + 0.03, gate[1] - 0.03
    x = g0 + 0.06
    while x < g1:
        U.box(gb, (x, y + 0.02, 0.60), (0.085, 0.022, 1.08))
        U.box(gb, (x, y + 0.02, 1.145), (0.06, 0.022, 0.06), rot=Euler((0, math.pi / 4, 0)).to_matrix())
        x += 0.12
    for z in (0.22, 0.95):
        U.box(gb, ((g0 + g1) / 2, y - 0.005, z), (g1 - g0, 0.025, 0.09))
    L = math.hypot(g1 - g0 - 0.1, 0.73)
    U.box(gb, ((g0 + g1) / 2, y - 0.005, 0.585), (L, 0.024, 0.08), rot=Euler((0, -math.atan2(0.73, g1 - g0 - 0.1), 0)).to_matrix())
    for z in (0.22, 0.95):
        U.box(mb, (g0 + 0.10, y - 0.025, z), (0.22, 0.008, 0.035))
    _rod(mb, (g1 - 0.02, y - 0.03, 0.80), (g1 + 0.10, y - 0.03, 0.80), 0.008)
    U.box(mb, (g1 - 0.06, y - 0.035, 0.80), (0.05, 0.02, 0.05))
    U.bevel_all(bm, 0.004, segs=1); U.bevel_all(gb, 0.004, segs=1)
    fence = U.obj_from_bm("fence", bm, mats=[paint], smooth=True, weighted=True)
    g = U.obj_from_bm("gate", gb, mats=[gatep], smooth=True, weighted=True); g.parent = fence
    m = U.obj_from_bm("gate_metal", mb, mats=[metal], smooth=True); m.parent = fence
    return fence


def build_bicycle(cx, cy, lean_deg=10.0, yaw_deg=0.0):
    """a generic bicycle (no marks): 0.68 m wheels with tyres, rims, 18 spokes each and hubs; a diamond frame;
    fork, stem and handlebar with grips; saddle on a seat post; chainring, chain, cranks and pedals.
    Front toward +x; leaning lean_deg toward +y (against the fence)"""
    framep = U.principled("bike_paint", base=(0.20, 0.36, 0.40), rough=0.3, coat=0.8, coat_rough=0.05)
    rubber = U.principled("bike_tyre", base=(0.03, 0.03, 0.03), rough=0.8)
    alu = U.principled("bike_alu", base=(0.78, 0.79, 0.80), rough=0.25, metal=1.0)
    dark = U.principled("bike_dark", base=(0.04, 0.04, 0.045), rough=0.5)
    saddle = U.principled("bike_saddle", base=(0.25, 0.16, 0.10), rough=0.45, coat=0.3)
    Rw, wb = 0.34, 1.02
    rear, front = Vector((-wb / 2, 0, Rw)), Vector((wb / 2, 0, Rw))
    I = Matrix.Identity(3)
    tb = bmesh.new(); rb = bmesh.new(); fb = bmesh.new(); db = bmesh.new(); sb = bmesh.new()
    for c in (rear, front):
        _tube_ring(tb, c, Rw - 0.018, 0.018, I, segs=64, sides=10)          # tyre
        _tube_ring(rb, c, Rw - 0.040, 0.008, I, segs=64, sides=8)           # rim
        U.cyl(rb, c, 0.022, 0.022, 0.10, segs=16, rot=Euler((math.pi / 2, 0, 0)).to_matrix())   # hub
        for k in range(18):
            a = 2 * math.pi * k / 18
            side = 0.03 if k % 2 else -0.03
            _rod(rb, c + Vector((0, side, 0)), c + Vector(((Rw - 0.045) * math.cos(a), 0, (Rw - 0.045) * math.sin(a))), 0.0012, segs=4)
    bb = Vector((0.0, 0, 0.29))                     # bottom bracket
    seat_top = Vector((-0.17, 0, 0.82)); head_top = Vector((0.40, 0, 0.84)); head_bot = Vector((0.44, 0, 0.66))
    for a, b in ((bb, seat_top), (seat_top + Vector((0.01, 0, -0.04)), head_top), (bb, head_bot), (head_top, head_bot)):
        _rod(fb, a, b, 0.017)
    for s in (-0.035, 0.035):
        _rod(fb, rear + Vector((0, s, 0)), bb + Vector((0, s * 0.6, 0)), 0.010)
        _rod(fb, rear + Vector((0, s, 0)), seat_top + Vector((0.01, s * 0.3, -0.05)), 0.009)
        _rod(fb, front + Vector((0, s, 0)), head_bot + Vector((0, s * 0.4, 0)), 0.011)
    _rod(db, head_top, head_top + Vector((-0.04, 0, 0.10)), 0.013)                       # stem
    hb = head_top + Vector((0.02, 0, 0.11))
    _rod(db, hb + Vector((0, -0.24, 0)), hb + Vector((0, 0.24, 0)), 0.011)              # handlebar
    for s in (-1, 1):
        U.cyl(db, hb + Vector((0, s * 0.21, 0)), 0.017, 0.017, 0.11, segs=12, rot=Euler((math.pi / 2, 0, 0)).to_matrix())
    _rod(db, seat_top, seat_top + Vector((-0.03, 0, 0.14)), 0.013)                      # seat post
    U.sphere(sb, seat_top + Vector((-0.05, 0, 0.18)), (0.14, 0.075, 0.035), segs=(20, 10))
    U.sphere(sb, seat_top + Vector((0.07, 0, 0.175)), (0.06, 0.03, 0.03), segs=(14, 8))
    U.cyl(db, bb + Vector((0, -0.06, 0)), 0.10, 0.10, 0.006, segs=40, rot=Euler((math.pi / 2, 0, 0)).to_matrix())   # chainring
    # chain: a flat loop of small links around the chainring and the rear cog
    pts = []
    for i in range(80):
        t = i / 80
        if t < 0.5:
            a = math.pi / 2 + t * 2 * math.pi
            p = bb + Vector((0.10 * math.cos(a), -0.06, 0.10 * math.sin(a)))
        else:
            a = -math.pi / 2 + (t - 0.5) * 2 * math.pi
            p = rear + Vector((0.04 * math.cos(a), -0.06, 0.04 * math.sin(a)))
        pts.append(p)
    for i in range(0, 80, 2):
        U.box(db, (pts[i] + pts[(i + 1) % 80]) / 2, (0.012, 0.004, 0.006))
    _rod(db, Vector((0.02, -0.06, 0.26)), Vector((0.02, -0.08, 0.10)), 0.008)
    U.box(db, (0.02, -0.12, 0.10), (0.09, 0.06, 0.02))
    _rod(db, Vector((-0.02, 0.06, 0.32)), Vector((-0.02, 0.08, 0.47)), 0.008)
    U.box(db, (-0.02, 0.12, 0.47), (0.09, 0.06, 0.02))
    tyre = U.obj_from_bm("bicycle", tb, mats=[rubber], smooth=True)
    for bmx, mat, nm in ((rb, alu, "bike_rims"), (fb, framep, "bike_frame"), (db, dark, "bike_parts"), (sb, saddle, "bike_saddle")):
        o = U.obj_from_bm(nm, bmx, mats=[mat], smooth=True); o.parent = tyre
    tyre.rotation_euler = (-math.radians(lean_deg), 0, math.radians(yaw_deg))
    tyre.location = (cx, cy, 0.0)
    return tyre
