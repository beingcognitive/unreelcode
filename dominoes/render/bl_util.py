"""Small helpers for building the scene in Blender (bpy). Procedural only: no image textures, no assets."""
import math
import bpy, bmesh
from mathutils import Matrix, Vector, Euler

COL = None


def collection(name="v3"):
    global COL
    if COL is None:
        COL = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(COL)
    return COL


def obj_from_bm(name, bm, mats=(), smooth=False, weighted=False, sharp_angle=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for m in mats:
        me.materials.append(m)
    if smooth:
        me.shade_smooth()
        if sharp_angle is not None:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    ob = bpy.data.objects.new(name, me)
    collection().objects.link(ob)
    if weighted:
        mod = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
        mod.mode = "FACE_AREA"
    return ob


def apply_modifiers(ob):
    """bake the evaluated mesh into the object's own mesh (works in background mode)"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    return ob


def boolean(ob, cutter, op="DIFFERENCE", transfer=True):
    mod = ob.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.object = cutter
    if transfer:
        mod.material_mode = "TRANSFER"
    apply_modifiers(ob)
    return ob


def remove(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me is not None and me.users == 0:
        try:
            bpy.data.meshes.remove(me)
        except Exception:
            pass


def box(bm, center, size, rot=None):
    M = Matrix.Translation(Vector(center))
    if rot is not None:
        M = M @ rot.to_4x4()
    M = M @ Matrix.Diagonal(Vector((size[0], size[1], size[2], 1.0)))
    return bmesh.ops.create_cube(bm, size=1.0, matrix=M)


def cyl(bm, center, r1, r2, depth, segs=32, rot=None, caps=True):
    M = Matrix.Translation(Vector(center))
    if rot is not None:
        M = M @ rot.to_4x4()
    return bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r1, radius2=r2,
                                 depth=depth, matrix=M)


def sphere(bm, center, radii, segs=(24, 12), rot=None):
    M = Matrix.Translation(Vector(center))
    if rot is not None:
        M = M @ rot.to_4x4()
    M = M @ Matrix.Diagonal(Vector((radii[0], radii[1], radii[2], 1.0)))
    return bmesh.ops.create_uvsphere(bm, u_segments=segs[0], v_segments=segs[1], radius=1.0, matrix=M)


def bevel_all(bm, offset, segs=3, profile=0.5):
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=offset, offset_type="OFFSET", segments=segs, profile=profile,
                    affect="EDGES", clamp_overlap=True)


def set_mat_index(bm, idx, pred):
    for f in bm.faces:
        if pred(f):
            f.material_index = idx


# ------------------------------------------------------------------------------------------------ materials
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    return m, nt, p


def principled(name, base=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, coat=0.0, coat_rough=0.03, sss=0.0,
               sss_radius=(1.0, 0.7, 0.5), sss_scale=0.001, trans=0.0, ior=1.5, spec=0.5, aniso=0.0):
    m, nt, p = new_mat(name)
    p.inputs["Base Color"].default_value = (*base, 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Coat Roughness"].default_value = coat_rough
    p.inputs["Subsurface Weight"].default_value = sss
    p.inputs["Subsurface Radius"].default_value = sss_radius
    p.inputs["Subsurface Scale"].default_value = sss_scale
    p.inputs["Transmission Weight"].default_value = trans
    p.inputs["IOR"].default_value = ior
    p.inputs["Specular IOR Level"].default_value = spec
    p.inputs["Anisotropic"].default_value = aniso
    return m


def node(nt, typ, loc=(0, 0), **props):
    n = nt.nodes.new(typ)
    n.location = loc
    for k, v in props.items():
        setattr(n, k, v)
    return n


def link(nt, a, b):
    nt.links.new(a, b)


def math_node(nt, op, a=None, b=None, va=None, vb=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if a is not None: nt.links.new(a, n.inputs[0])
    elif va is not None: n.inputs[0].default_value = va
    if b is not None: nt.links.new(b, n.inputs[1])
    elif vb is not None: n.inputs[1].default_value = vb
    return n.outputs[0]


def rot_to(direction, up=(0, 0, 1)):
    """rotation matrix whose local Z points along direction"""
    d = Vector(direction).normalized()
    return d.to_track_quat("Z", "Y").to_matrix()
