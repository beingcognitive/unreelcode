"""Large props: car, house, trees, grass (procedural, true size)."""
import math, random
import bpy, bmesh
from mathutils import Matrix, Vector, Euler, noise
import bl_util as U
import props as P


# ------------------------------------------------------------------------------------------------ car
def _loft(bm, stations, nseg=28, expo=3.0):
    """stations: list of (x, half_width, z_bottom, z_top, z_shoulder_frac). Cross-section: a superellipse.
    returns rings of verts"""
    rings = []
    for (x, hw, zb, zt, sh) in stations:
        zc = (zb + zt) / 2; hh = (zt - zb) / 2
        ring = []
        for k in range(nseg):
            a = 2 * math.pi * k / nseg
            c, s = math.cos(a), math.sin(a)
            y = hw * math.copysign(abs(c) ** (2 / expo), c)
            z = zc + hh * math.copysign(abs(s) ** (2 / expo), s)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(nseg):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % nseg], rings[i + 1][(k + 1) % nseg], rings[i + 1][k]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    return rings


def build_car(cx, cy):
    """a generic compact hatchback, 4.20 x 1.78 x 1.48 m, front toward +x; no brand"""
    paint = U.principled("car_paint", base=(0.20, 0.36, 0.52), rough=0.32, metal=0.5, coat=1.0, coat_rough=0.02)
    glass = U.principled("car_glass", base=(0.10, 0.12, 0.13), rough=0.02, coat=1.0, coat_rough=0.0, spec=0.8)
    rubber = U.principled("tyre", base=(0.025, 0.025, 0.027), rough=0.75)
    alloy = U.principled("alloy", base=(0.78, 0.79, 0.80), rough=0.22, metal=1.0)
    chrome = U.principled("chrome", base=(0.9, 0.9, 0.9), rough=0.05, metal=1.0)
    lens = U.principled("headlamp", base=(0.95, 0.96, 0.97), rough=0.02, trans=0.9)
    red = U.principled("taillamp", base=(0.65, 0.04, 0.03), rough=0.05, trans=0.5, coat=1.0)
    trim = U.principled("car_trim", base=(0.03, 0.03, 0.035), rough=0.5)
    plate = U.principled("plate", base=(0.92, 0.92, 0.90), rough=0.4)
    L = 4.20
    # lower body
    bm = bmesh.new()
    st = []
    for x, hw, zb, zt in ((-2.10, 0.80, 0.34, 0.86), (-2.04, 0.86, 0.26, 0.98), (-1.80, 0.89, 0.22, 1.00),
                          (-1.2, 0.89, 0.21, 0.98), (0.0, 0.89, 0.21, 0.96), (1.0, 0.89, 0.22, 0.90),
                          (1.60, 0.87, 0.24, 0.82), (1.95, 0.82, 0.28, 0.72), (2.10, 0.74, 0.32, 0.62)):
        st.append((x, hw, zb, zt, 0))
    _loft(bm, st, nseg=32, expo=5.0)
    body = U.obj_from_bm("car_body", bm, mats=[paint])
    sub = body.modifiers.new("sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 2
    body.data.shade_smooth()
    # greenhouse (glass) with a painted roof
    gb = bmesh.new()
    st2 = [(-1.95, 0.70, 0.90, 1.30, 0), (-1.70, 0.74, 0.90, 1.44, 0), (-0.6, 0.75, 0.90, 1.48, 0),
           (0.35, 0.75, 0.90, 1.46, 0), (0.85, 0.73, 0.90, 1.28, 0), (1.15, 0.71, 0.90, 1.02, 0)]
    _loft(gb, st2, nseg=32, expo=6.0)
    gh = U.obj_from_bm("car_glass", gb, mats=[glass])
    s2 = gh.modifiers.new("sub", "SUBSURF"); s2.levels = 2; s2.render_levels = 2
    gh.data.shade_smooth()
    rb = bmesh.new()
    _loft(rb, [(-1.62, 0.72, 1.42, 1.465, 0), (-0.6, 0.73, 1.46, 1.505, 0), (0.30, 0.73, 1.44, 1.485, 0)], nseg=24, expo=6.0)
    roof = U.obj_from_bm("car_roof", rb, mats=[paint])
    s3 = roof.modifiers.new("sub", "SUBSURF"); s3.levels = 2; s3.render_levels = 2
    roof.data.shade_smooth()
    # pillars (B pillar) and window trim
    pb = bmesh.new()
    for sy in (-1, 1):
        U.box(pb, (-0.35, sy * 0.745, 1.18), (0.10, 0.03, 0.56), rot=Euler((0, math.radians(-4), 0)).to_matrix())
        U.box(pb, (-0.35, sy * 0.80, 0.905), (3.0, 0.03, 0.03))
    U.bevel_all(pb, 0.008, segs=2)
    U.obj_from_bm("car_pillars", pb, mats=[trim], smooth=True)
    # wheels
    wb = bmesh.new(); rimb = bmesh.new()
    for wx in (-1.32, 1.30):
        for sy in (-1, 1):
            c = Vector((wx, sy * 0.79, 0.31))
            rot = Euler((math.pi / 2, 0, 0)).to_matrix()
            U.cyl(wb, c, 0.31, 0.31, 0.20, segs=48, rot=rot)
            U.cyl(rimb, c + Vector((0, sy * 0.06, 0)), 0.205, 0.205, 0.10, segs=48, rot=rot)
            for k in range(5):
                a = 2 * math.pi * k / 5
                sp = rot @ Euler((0, 0, a)).to_matrix()
                U.box(rimb, c + Vector((0, sy * 0.115, 0)) + Vector((0.11 * math.cos(a), 0, 0.11 * math.sin(a))),
                      (0.20, 0.045, 0.02), rot=Euler((0, -a, 0)).to_matrix())
            U.cyl(rimb, c + Vector((0, sy * 0.12, 0)), 0.045, 0.045, 0.03, segs=24, rot=rot)
    U.bevel_all(wb, 0.05, segs=4)
    tyre = U.obj_from_bm("car_tyres", wb, mats=[rubber], smooth=True, weighted=True)
    U.obj_from_bm("car_rims", rimb, mats=[alloy], smooth=True, weighted=True)
    # dark wheel arches (inner)
    ab = bmesh.new()
    for wx in (-1.32, 1.30):
        for sy in (-1, 1):
            U.cyl(ab, (wx, sy * 0.80, 0.31), 0.37, 0.37, 0.16, segs=40, rot=Euler((math.pi / 2, 0, 0)).to_matrix())
    arch = U.obj_from_bm("arches", ab, mats=[trim])
    U.boolean(body, arch, "DIFFERENCE", transfer=False)
    U.remove(arch)
    body.data.shade_smooth()
    # lights, mirrors, plates, bumper strips
    lb = bmesh.new()
    for sy in (-1, 1):
        U.box(lb, (2.02, sy * 0.58, 0.74), (0.12, 0.30, 0.10), rot=Euler((0, math.radians(-25), sy * math.radians(14))).to_matrix())
    U.bevel_all(lb, 0.02, segs=3)
    U.obj_from_bm("headlamps", lb, mats=[lens], smooth=True)
    tb = bmesh.new()
    for sy in (-1, 1):
        U.box(tb, (-2.06, sy * 0.66, 0.86), (0.06, 0.22, 0.16))
    U.bevel_all(tb, 0.015, segs=2)
    U.obj_from_bm("taillamps", tb, mats=[red], smooth=True)
    mb = bmesh.new()
    for sy in (-1, 1):
        U.box(mb, (0.95, sy * 0.95, 1.00), (0.20, 0.10, 0.12))
        U.box(mb, (1.02, sy * 0.86, 0.97), (0.06, 0.12, 0.03))
    U.bevel_all(mb, 0.02, segs=2)
    U.obj_from_bm("mirrors", mb, mats=[paint], smooth=True)
    pl = bmesh.new()
    U.box(pl, (2.12, 0, 0.45), (0.01, 0.50, 0.11)); U.box(pl, (-2.13, 0, 0.62), (0.01, 0.50, 0.11))
    U.obj_from_bm("plates", pl, mats=[plate])
    bb = bmesh.new()
    U.box(bb, (2.08, 0, 0.36), (0.10, 1.50, 0.10)); U.box(bb, (-2.09, 0, 0.36), (0.10, 1.55, 0.10))
    U.box(bb, (2.11, 0, 0.56), (0.03, 0.70, 0.10))                     # grille
    for sy in (-1, 1):
        U.box(bb, (0, sy * 0.895, 0.33), (2.0, 0.02, 0.06))           # sills
    U.bevel_all(bb, 0.02, segs=2)
    U.obj_from_bm("bumpers", bb, mats=[trim], smooth=True, weighted=True)
    hb = bmesh.new()
    for sy in (-1, 1):
        for x in (0.25, -0.85):
            U.box(hb, (x, sy * 0.90, 0.82), (0.18, 0.025, 0.025))
    U.bevel_all(hb, 0.008, segs=2)
    U.obj_from_bm("handles", hb, mats=[chrome], smooth=True)
    for o in list(bpy.data.objects):
        if o.name.split(".")[0] in ("car_glass", "car_roof", "car_pillars", "car_tyres", "car_rims", "headlamps",
                                    "taillamps", "mirrors", "plates", "bumpers", "handles") and o.parent is None:
            o.parent = body
    body.location = (cx, cy, 0)
    return body


# ------------------------------------------------------------------------------------------------ house
def build_house(cx, cy):
    """a two-storey house: 9 x 7 m, walls 6.0 m, tiled gable roof (ridge 8.6 m), recessed windows with frames,
    mullions, glass and sills, a panelled door, gutters and a downpipe, a brick chimney"""
    plaster = P.mat_siding("siding")
    stone = P.mat_plaster("plinth", base=(0.55, 0.54, 0.52))
    frame = U.principled("window_paint", base=(0.95, 0.95, 0.94), rough=0.35, coat=0.3)
    glass = P.mat_glass("house_glass", tint=(0.90, 0.94, 0.95))
    room = U.principled("room", base=(0.10, 0.09, 0.08), rough=0.9)
    curtain = U.principled("curtain", base=(0.82, 0.80, 0.74), rough=0.9, sss=0.0)
    tiles = P.mat_tiles("roof_tiles", base=(0.62, 0.30, 0.20))
    zinc = U.principled("zinc", base=(0.62, 0.64, 0.66), rough=0.35, metal=1.0)
    doorp = U.principled("door_paint", base=(0.20, 0.32, 0.30), rough=0.3, coat=0.6)
    brassm = U.principled("door_brass", base=(0.85, 0.66, 0.36), rough=0.2, metal=1.0)
    brick = P.mat_brick()
    W, D, Hw, Hr = 9.0, 7.0, 6.0, 8.6
    bm = bmesh.new(); U.box(bm, (0, 0, Hw / 2), (W, D, Hw))
    walls = U.obj_from_bm("house", bm, mats=[plaster, room])
    # window and door openings (front y = -D/2 and the two gable sides)
    cut = bmesh.new()
    wins = []
    for row, zc in ((0, 1.65), (1, 4.35)):
        for xw in (-3.0, -0.9, 1.4, 3.3):
            if row == 0 and xw == -0.9:
                continue
            wins.append(("f", xw, zc))
    for sx in (-1, 1):
        for zc in (1.65, 4.35):
            wins.append(("s%d" % sx, 1.0, zc))
    for kind, a, zc in wins:
        if kind == "f":
            U.box(cut, (a, -D / 2, zc), (1.10, 0.50, 1.40))
        else:
            sx = int(kind[1:])
            U.box(cut, (sx * W / 2, a, zc), (0.50, 1.10, 1.40))
    U.box(cut, (-0.9, -D / 2, 1.10), (1.10, 0.50, 2.20))
    cutter = U.obj_from_bm("house_cut", cut, mats=[room])
    U.boolean(walls, cutter, "DIFFERENCE", transfer=True); U.remove(cutter)
    # frames, mullions, glass, sills, curtains
    fb = bmesh.new(); gb = bmesh.new(); sb = bmesh.new(); cb = bmesh.new()
    for kind, a, zc in wins:
        if kind == "f":
            M = Matrix.Translation((a, -D / 2 + 0.10, zc))
        else:
            sx = int(kind[1:])
            M = Matrix.Translation((sx * (W / 2 - 0.10), a, zc)) @ Euler((0, 0, sx * math.pi / 2)).to_matrix().to_4x4()
        def B(bmx, c, s):
            c = M @ Vector(c)
            R3 = M.to_3x3()
            U.box(bmx, c, s, rot=R3)
        B(fb, (0, 0, 0.67), (1.10, 0.10, 0.07)); B(fb, (0, 0, -0.67), (1.10, 0.10, 0.07))
        B(fb, (-0.52, 0, 0), (0.07, 0.10, 1.40)); B(fb, (0.52, 0, 0), (0.07, 0.10, 1.40))
        B(fb, (0, 0, 0), (0.05, 0.08, 1.30)); B(fb, (0, 0, 0.25), (1.0, 0.08, 0.05))
        B(gb, (0, 0.01, 0), (1.0, 0.008, 1.30))
        B(sb, (0, -0.16, -0.73), (1.26, 0.22, 0.06))
        B(cb, (-0.35, 0.18, 0.05), (0.32, 0.04, 1.25)); B(cb, (0.38, 0.18, 0.05), (0.28, 0.04, 1.25))
    U.bevel_all(fb, 0.006, segs=1); U.bevel_all(sb, 0.01, segs=2)
    U.obj_from_bm("house_frames", fb, mats=[frame], smooth=True, weighted=True)
    U.obj_from_bm("house_glass", gb, mats=[glass])
    U.obj_from_bm("house_sills", sb, mats=[stone], smooth=True, weighted=True)
    U.obj_from_bm("house_curtains", cb, mats=[curtain])
    # door
    db = bmesh.new()
    U.box(db, (-0.9, -D / 2 + 0.12, 1.05), (1.0, 0.05, 2.10))
    pnl = bmesh.new()
    for zz in (0.55, 1.45):
        for xx in (-1.12, -0.68):
            U.box(pnl, (xx, -D / 2 + 0.09, zz), (0.34, 0.03, 0.70))
    U.bevel_all(pnl, 0.015, segs=2)
    U.obj_from_bm("door_panels", pnl, mats=[doorp], smooth=True, weighted=True)
    U.obj_from_bm("door", db, mats=[doorp])
    hb = bmesh.new()
    U.cyl(hb, (-0.52, -D / 2 + 0.05, 1.05), 0.025, 0.025, 0.10, segs=16, rot=Euler((math.pi / 2, 0, 0)).to_matrix())
    U.sphere(hb, (-0.52, -D / 2 + 0.0, 1.05), (0.04, 0.03, 0.04))
    U.box(hb, (-0.9, -D / 2 + 0.07, 1.65), (0.25, 0.02, 0.05))
    U.obj_from_bm("door_brass", hb, mats=[brassm], smooth=True)
    stb = bmesh.new(); U.box(stb, (-0.9, -D / 2 - 0.25, 0.08), (1.6, 0.6, 0.16)); U.bevel_all(stb, 0.02, segs=2)
    U.box(stb, (0, 0, 0.25), (W + 0.06, D + 0.06, 0.5))          # plinth band
    for sx in (-1, 1):
        for sy in (-1, 1):
            U.box(stb, (sx * (W / 2 + 0.01), sy * (D / 2 + 0.01), 3.25), (0.16, 0.16, 5.5))   # corner boards
    U.box(stb, (0, -(D / 2 + 0.03), 3.02), (W + 0.04, 0.06, 0.12))                         # floor band
    U.obj_from_bm("house_step", stb, mats=[stone], smooth=True, weighted=True)
    # roof: slabs + individual tiles in rows, fascia boards, gutters, downpipe
    rb = bmesh.new(); tb = bmesh.new(); r_tile = random.Random(7)
    slope = math.atan2(Hr - Hw, D / 2)
    ov = 0.45
    ln = math.hypot(D / 2, Hr - Hw) + ov
    for sy in (-1, 1):
        rot = Euler((-sy * slope, 0, 0)).to_matrix()
        nrm = rot @ Vector((0, 0, 1))
        c = Vector((0, sy * (D / 4 + ov / 2 * math.cos(slope)), (Hw + Hr) / 2 - ov / 2 * math.sin(slope))) + nrm * 0.08
        U.box(rb, c, (W + 0.7, ln, 0.12), rot=rot)
        rows = int(ln / 0.30)
        for i in range(rows):
            d = -ln / 2 + (i + 0.5) * (ln / rows)
            ncol = int((W + 0.6) / 0.30)
            for j in range(ncol):
                xj = -(W + 0.6) / 2 + (j + 0.5) * ((W + 0.6) / ncol)
                cc = c + rot @ Vector((xj, sy * d, 0.07 + 0.012))
                tr = rot @ Euler((sy * math.radians(5), 0, 0)).to_matrix()
                U.box(tb, cc + Vector((r_tile.uniform(-0.01, 0.01), 0, 0)), (0.285, (ln / rows) * 1.3, 0.016),
                      rot=tr @ Euler((0, r_tile.uniform(-0.03, 0.03), r_tile.uniform(-0.02, 0.02))).to_matrix())
    U.box(rb, (0, 0, Hr + 0.17), (W + 0.72, 0.30, 0.14))
    U.obj_from_bm("roof_slab", rb, mats=[tiles])
    # tiles: flatten the cylinders into curved tiles by scaling their local thickness
    for v in tb.verts:
        pass
    tiles_ob = U.obj_from_bm("roof_tiles", tb, mats=[tiles], smooth=True)
    tiles_ob.scale = (1, 1, 1)
    gu = bmesh.new()
    for sy in (-1, 1):
        y = sy * (D / 2 + ov - 0.05)
        U.cyl(gu, (0, y, Hw - 0.30), 0.075, 0.075, W + 0.7, segs=16, rot=Euler((0, math.pi / 2, 0)).to_matrix())
        U.box(gu, (0, sy * (D / 2 + 0.06), Hw - 0.2), (W + 0.7, 0.04, 0.22))          # fascia
    U.cyl(gu, (W / 2 + 0.25, -(D / 2 + 0.38), (Hw - 0.35) / 2), 0.045, 0.045, Hw - 0.35, segs=16)
    U.cyl(gu, (W / 2 + 0.25, -(D / 2 + 0.38), 0.15), 0.05, 0.05, 0.3, segs=16)
    U.obj_from_bm("gutters", gu, mats=[zinc], smooth=True)
    ch = bmesh.new()
    U.box(ch, (2.6, 1.0, 8.1), (0.70, 0.70, 2.2))
    chi = U.obj_from_bm("chimney", ch, mats=[brick])
    cc = bmesh.new()
    U.box(cc, (2.6, 1.0, 9.25), (0.82, 0.82, 0.10))
    U.cyl(cc, (2.45, 1.0, 9.45), 0.09, 0.08, 0.30, segs=16); U.cyl(cc, (2.75, 1.0, 9.45), 0.09, 0.08, 0.30, segs=16)
    U.obj_from_bm("chimney_cap", cc, mats=[stone], smooth=True)
    for o in list(bpy.data.objects):
        if o.parent is None and o is not walls and o.name.split(".")[0] in (
                "house_frames", "house_glass", "house_sills", "house_curtains", "door_panels", "door", "door_brass",
                "house_step", "roof_slab", "roof_tiles", "gutters", "chimney", "chimney_cap"):
            o.parent = walls
    walls.location = (cx, cy, 0)
    return walls


# ------------------------------------------------------------------------------------------------ trees
def build_tree(name, cx, cy, height, seed, narrow=1.0):
    """a broadleaf tree: a recursive branch skeleton turned into tubes (skin modifier) and ~20k individual leaves"""
    r = random.Random(seed)
    bark = P.mat_plaster("bark_" + name, base=(0.30, 0.25, 0.20))
    bark.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
    leafm = bpy.data.materials.get("leaf")
    if leafm is None:
        leafm = bpy.data.materials.new("leaf"); leafm.use_nodes = True
        nt = leafm.node_tree; nt.nodes.clear()
        out = U.node(nt, "ShaderNodeOutputMaterial")
        pb = U.node(nt, "ShaderNodeBsdfPrincipled")
        pb.inputs["Base Color"].default_value = (0.16, 0.30, 0.08, 1); pb.inputs["Roughness"].default_value = 0.45
        oi = U.node(nt, "ShaderNodeObjectInfo")
        tr = U.node(nt, "ShaderNodeBsdfTranslucent"); tr.inputs["Color"].default_value = (0.30, 0.48, 0.10, 1)
        mx = U.node(nt, "ShaderNodeMixShader"); mx.inputs[0].default_value = 0.35
        U.link(nt, pb.outputs[0], mx.inputs[1]); U.link(nt, tr.outputs[0], mx.inputs[2])
        U.link(nt, mx.outputs[0], out.inputs["Surface"])
        # per-leaf colour variation from the vertex colour attribute "tint"
        at = U.node(nt, "ShaderNodeAttribute"); at.attribute_name = "tint"
        U.link(nt, at.outputs["Color"], pb.inputs["Base Color"])
    bm = bmesh.new()
    radii = {}
    tips = []
    trunk_h = height * 0.33
    root = bm.verts.new((0, 0, 0)); radii[root] = height * 0.022
    def grow(v0, direction, length, radius, depth):
        n = max(2, int(length / (height * 0.06)))
        v = v0; d = direction.normalized()
        for i in range(n):
            d = (d + Vector((r.gauss(0, 0.12), r.gauss(0, 0.12), r.gauss(0, 0.08) + 0.04))).normalized()
            if narrow < 1.0:
                d = Vector((d.x * narrow, d.y * narrow, d.z)).normalized()
            nv = bm.verts.new(v.co + d * length / n)
            bm.edges.new((v, nv))
            radii[nv] = radius * (1 - 0.35 * (i + 1) / n)
            v = nv
            if depth < 4 and i >= n // 3 and r.random() < 0.6:
                ax = d.orthogonal().normalized()
                ang = r.uniform(0.5, 0.9)
                cd = Matrix.Rotation(ang, 3, ax) @ d
                cd = Matrix.Rotation(r.uniform(0, 2 * math.pi), 3, d) @ cd
                grow(v, cd, length * r.uniform(0.45, 0.65), radii[v] * 0.6, depth + 1)
        if depth >= 4:
            tips.append((v.co.copy(), d))
        else:
            for k in range(r.randint(2, 3)):
                ax = d.orthogonal().normalized()
                cd = Matrix.Rotation(r.uniform(0.4, 0.8), 3, ax) @ d
                cd = Matrix.Rotation(2 * math.pi * k / 3 + r.uniform(-0.4, 0.4), 3, d) @ cd
                grow(v, cd, length * r.uniform(0.55, 0.75), radii[v] * 0.7, depth + 1)
    grow(root, Vector((0, 0, 1)), trunk_h, radii[root], 0)
    me = bpy.data.meshes.new(name + "_wood"); bm.to_mesh(me)
    order = list(radii.keys())
    bm.free()
    ob = bpy.data.objects.new(name + "_wood", me); U.collection().objects.link(ob)
    sk = ob.modifiers.new("skin", "SKIN")
    sv = me.skin_vertices[0].data
    rl = list(radii.values())
    for i, v in enumerate(me.vertices):
        rr = max(0.004, rl[i] if i < len(rl) else 0.01)
        sv[i].radius = (rr, rr)
    sv[0].use_root = True
    ss = ob.modifiers.new("sub", "SUBSURF"); ss.levels = 1; ss.render_levels = 1
    me.materials.append(bark)
    # leaves
    lb = bmesh.new()
    tint = lb.loops.layers.color.new("tint")
    leaf_count = 0
    for (p, d) in tips:
        for k in range(r.randint(110, 140)):
            c = p + Vector((r.gauss(0, 0.42) * narrow, r.gauss(0, 0.42) * narrow, r.gauss(0, 0.30))) * height / 10
            ln = r.uniform(0.09, 0.14) * min(height, 11.0) / 10
            rot = Euler((r.uniform(0, 6.28), r.uniform(-0.8, 0.8), r.uniform(0, 6.28))).to_matrix()
            pts = [(0, 0, 0), (0.30, 0.17, 0.02), (0.65, 0.20, 0.03), (1.0, 0, 0.0), (0.65, -0.20, 0.03), (0.30, -0.17, 0.02)]
            vs = [lb.verts.new(c + rot @ (Vector(q) * ln)) for q in pts]
            f = lb.faces.new(vs)
            g = r.uniform(0.75, 1.15); y = r.uniform(-0.05, 0.08)
            col = (0.16 * g + y, 0.30 * g + y * 0.5, 0.08 * g, 1.0)
            for lp in f.loops:
                lp[tint] = col
            leaf_count += 1
    lo = U.obj_from_bm(name + "_leaves", lb, mats=[leafm])
    lo.parent = ob
    ob.location = (cx, cy, 0)
    print(f"tree {name}: {len(order)} branch nodes, {leaf_count} leaves", flush=True)
    return ob


# ------------------------------------------------------------------------------------------------ grass
def build_grass(regions, cam_xy, density=95.0, falloff=45.0):
    """grass blades instanced on the lawn with geometry nodes; density falls off with distance from the main
    eye-level camera (a rendering budget, display only)"""
    blade_m = bpy.data.materials.new("grass"); blade_m.use_nodes = True
    nt = blade_m.node_tree; p = nt.nodes["Principled BSDF"]
    oi = U.node(nt, "ShaderNodeObjectInfo")
    ramp = U.node(nt, "ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.16, 0.30, 0.07, 1); ramp.color_ramp.elements[1].color = (0.42, 0.50, 0.18, 1)
    U.link(nt, oi.outputs["Random"], ramp.inputs[0]); U.link(nt, ramp.outputs[0], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.5
    p.inputs["Subsurface Weight"].default_value = 0.0
    # a clump of 40 blades (instancing clumps instead of single blades keeps the instance count low)
    rr = random.Random(5)
    bb = bmesh.new()
    segs = 4
    for b in range(40):
        rad = 0.07 * math.sqrt(rr.random()); th = rr.uniform(0, 2 * math.pi)
        bx, by = rad * math.cos(th), rad * math.sin(th)
        hgt = 0.09 * rr.uniform(0.55, 1.35); w = 0.0045 * rr.uniform(0.7, 1.2)
        yaw = rr.uniform(0, 2 * math.pi); lean = rr.uniform(0.0, 0.035)
        R = Euler((0, 0, yaw)).to_matrix()
        prev = None
        for i in range(segs + 1):
            t = i / segs
            z = hgt * t; bend = lean * t * t; ww = w * (1 - t) + 0.0004
            a = bb.verts.new(Vector((bx, by, 0)) + R @ Vector((-ww / 2, bend, z)))
            c = bb.verts.new(Vector((bx, by, 0)) + R @ Vector((ww / 2, bend, z)))
            if prev:
                bb.faces.new((prev[0], prev[1], c, a))
            prev = (a, c)
    blade = U.obj_from_bm("grass_blade", bb, mats=[blade_m], smooth=True)
    blade.hide_render = True; blade.location = (0, 0, -50)
    # lawn mesh
    lm = bmesh.new()
    for (x0, x1, y0, y1) in regions:
        vs = [lm.verts.new((x0, y0, 0.001)), lm.verts.new((x1, y0, 0.001)), lm.verts.new((x1, y1, 0.001)), lm.verts.new((x0, y1, 0.001))]
        lm.faces.new(vs)
    bmesh.ops.subdivide_edges(lm, edges=list(lm.edges), cuts=20, use_grid_fill=True)
    soil = U.principled("lawn_ground", base=(0.16, 0.24, 0.07), rough=0.95)
    lawn = U.obj_from_bm("lawn", lm, mats=[soil])
    lawn.hide_render = False
    ng = bpy.data.node_groups.new("grass_gn", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n = ng.nodes
    gi = n.new("NodeGroupInput"); go = n.new("NodeGroupOutput")
    dist = n.new("GeometryNodeDistributePointsOnFaces"); dist.distribute_method = "RANDOM"
    pos = n.new("GeometryNodeInputPosition")
    vd = n.new("ShaderNodeVectorMath"); vd.operation = "DISTANCE"; vd.inputs[1].default_value = (cam_xy[0], cam_xy[1], 0)
    ng.links.new(pos.outputs[0], vd.inputs[0])
    m1 = n.new("ShaderNodeMath"); m1.operation = "DIVIDE"; m1.inputs[1].default_value = falloff
    ng.links.new(vd.outputs["Value"], m1.inputs[0])
    m2 = n.new("ShaderNodeMath"); m2.operation = "SUBTRACT"; m2.inputs[0].default_value = 1.0
    ng.links.new(m1.outputs[0], m2.inputs[1])
    m3 = n.new("ShaderNodeMath"); m3.operation = "MAXIMUM"; m3.inputs[1].default_value = 0.03
    ng.links.new(m2.outputs[0], m3.inputs[0])
    m4 = n.new("ShaderNodeMath"); m4.operation = "MULTIPLY"; m4.inputs[1].default_value = density
    ng.links.new(m3.outputs[0], m4.inputs[0])
    ng.links.new(gi.outputs[0], dist.inputs["Mesh"])
    ng.links.new(m4.outputs[0], dist.inputs["Density"])
    inst = n.new("GeometryNodeInstanceOnPoints")
    oi2 = n.new("GeometryNodeObjectInfo"); oi2.inputs["Object"].default_value = blade
    oi2.transform_space = "ORIGINAL"
    rv = n.new("FunctionNodeRandomValue"); rv.data_type = "FLOAT_VECTOR"
    rv.inputs["Min"].default_value = (-0.08, -0.08, 0); rv.inputs["Max"].default_value = (0.08, 0.08, 6.283)
    rs = n.new("FunctionNodeRandomValue"); rs.data_type = "FLOAT"
    rs.inputs[2].default_value = 0.8; rs.inputs[3].default_value = 1.25
    ng.links.new(dist.outputs["Points"], inst.inputs["Points"])
    ng.links.new(oi2.outputs["Geometry"], inst.inputs["Instance"])
    ng.links.new(rv.outputs[0], inst.inputs["Rotation"])
    ng.links.new(rs.outputs[1], inst.inputs["Scale"])
    join = n.new("GeometryNodeJoinGeometry")
    ng.links.new(inst.outputs[0], join.inputs[0]); ng.links.new(gi.outputs[0], join.inputs[0])
    ng.links.new(join.outputs[0], go.inputs[0])
    mod = lawn.modifiers.new("grass", "NODES"); mod.node_group = ng
    return lawn
