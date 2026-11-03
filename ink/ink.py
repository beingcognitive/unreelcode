"""ink.py -- GPU ink-in-water solver (moderngl, OpenGL 4.1) and frame renderer.

Velocity lives on a VW x VH grid, ink on a 2x finer DW x DH grid (four layers).
Each step: MacCormack-advect velocity, forces (vorticity confinement + sinking ink),
Jacobi pressure projection, MacCormack-advect ink.
"""
import re
import numpy as np
import moderngl

import os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(f"{HERE}/shaders/ink.glsl").read()
LOOK = open(f"{HERE}/shaders/look.glsl").read()

VS = """#version 410
in vec2 pos; out vec2 uv;
void main() { uv = pos * 0.5 + 0.5; gl_Position = vec4(pos, 0.0, 1.0); }"""


def patch(src, consts):
    """Rewrite `const float NAME = value;` lines (the same edit a person would type)."""
    for k, v in consts.items():
        src, n = re.subn(rf"(const float {k}\s*=\s*)[^;]+;", lambda m: f"{m.group(1)}{v};", src)
        assert n == 1, k
    return src


class Ink:
    def __init__(self, VW=960, VH=402, scale=2, consts=None, jacobi=60, ctx=None):
        self.ctx = ctx or moderngl.create_standalone_context(require=410)
        self.VW, self.VH, self.DW, self.DH = VW, VH, VW * scale, VH * scale
        self.jacobi = jacobi
        c = self.ctx
        self.quad = c.buffer(np.array([-1, -1, 3, -1, -1, 3], "f4"))
        self.src = SRC
        self.progs = {}
        self.compile(consts or {})

        def tex(w, h, comps):
            t = c.texture((w, h), comps, dtype="f4")
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = False
            return t

        self.vel = [tex(VW, VH, 2) for _ in range(3)]
        self.prs = [tex(VW, VH, 1) for _ in range(2)]
        self.div = tex(VW, VH, 1)
        self.dye = [tex(self.DW, self.DH, 4) for _ in range(3)]
        self.fb = {}
        self.dx = (1.0 / VW, 1.0 / VH, 0.0)
        self.steps = 0
        self.clear()

    # ---------------------------------------------------------------- setup
    def compile(self, consts, source=None):
        self.source = source if source is not None else (patch(SRC, consts) if consts else SRC)
        for name in ["FORCES", "ADVECT", "MACCORMACK", "SPLAT", "DIVERGENCE", "JACOBI", "PROJECT"]:
            fs = f"#version 410\n#define {name}\n" + self.source
            p = self.ctx.program(vertex_shader=VS, fragment_shader=fs)
            self.progs[name] = (p, self.ctx.vertex_array(p, [(self.quad, "2f", "pos")]))

    def clear(self):
        for t in self.vel + self.prs + [self.div] + self.dye:
            t.write(np.zeros((t.height, t.width, t.components), "f4").tobytes())

    def fbo(self, t):
        if t.glo not in self.fb:
            self.fb[t.glo] = self.ctx.framebuffer([t])
        return self.fb[t.glo]

    def run(self, name, out, **u):
        p, va = self.progs[name]
        unit = 0
        for k, v in u.items():
            if k not in p:
                continue
            if isinstance(v, moderngl.Texture):
                v.use(unit)
                p[k].value = unit
                unit += 1
            else:
                p[k].value = v
        if "dx" in p:
            p["dx"].value = self.dx
        f = self.fbo(out)
        f.use()
        self.ctx.viewport = (0, 0, out.width, out.height)
        va.render(moderngl.TRIANGLES)

    # ---------------------------------------------------------------- state io
    def set_dye(self, arr):
        self.dye[0].write(np.ascontiguousarray(arr, "f4").tobytes())

    def set_vel(self, arr):
        self.vel[0].write(np.ascontiguousarray(arr, "f4").tobytes())

    def get_dye(self):
        return np.frombuffer(self.dye[0].read(), "f4").reshape(self.DH, self.DW, 4)

    def get_vel(self):
        return np.frombuffer(self.vel[0].read(), "f4").reshape(self.VH, self.VW, 2)

    # ---------------------------------------------------------------- physics
    def splat(self, at, r, vel=(0, 0), ink=(0, 0, 0, 0)):
        asp = self.VW / self.VH
        rad = (r / asp, r)
        if any(vel):
            self.run("SPLAT", self.vel[1], src=self.vel[0], at=at, radius=rad,
                     amount=(vel[0], vel[1], 0, 0))
            self.vel[0], self.vel[1] = self.vel[1], self.vel[0]
        if any(ink):
            self.run("SPLAT", self.dye[1], src=self.dye[0], at=at, radius=rad, amount=tuple(ink))
            self.dye[0], self.dye[1] = self.dye[1], self.dye[0]

    def step(self, dt, keep=1.0, vkeep=1.0):
        V, D = self.vel, self.dye
        # advect velocity (MacCormack)
        self.run("ADVECT", V[1], vel=V[0], src=V[0], dt=dt)
        self.run("MACCORMACK", V[2], vel=V[0], src=V[0], hat=V[1], dt=dt, keep=vkeep)
        V[0], V[2] = V[2], V[0]
        # forces: vorticity confinement + sinking ink
        self.run("FORCES", V[1], vel=V[0], dye=D[0], dt=dt)
        V[0], V[1] = V[1], V[0]
        # pressure projection
        self.run("DIVERGENCE", self.div, vel=V[0])
        P = self.prs
        for _ in range(self.jacobi):
            self.run("JACOBI", P[1], prs=P[0], div=self.div)
            P[0], P[1] = P[1], P[0]
        self.run("PROJECT", V[1], vel=V[0], prs=P[0])
        V[0], V[1] = V[1], V[0]
        # advect ink (MacCormack) on the finer grid
        self.run("ADVECT", D[1], vel=V[0], src=D[0], dt=dt)
        self.run("MACCORMACK", D[2], vel=V[0], src=D[0], hat=D[1], dt=dt, keep=keep)
        D[0], D[2] = D[2], D[0]
        self.steps += 1

    def finish(self):
        self.ctx.finish()


LOOK_DEFAULT = dict(
    pig=[(1.0, 0.35, 0.12), (1.0, 0.75, 0.3), (0.2, 0.6, 1.0), (0.8, 0.8, 0.85)],
    absb=[(0.6, 2.2, 3.0), (0.3, 0.9, 2.5), (2.5, 1.2, 0.4), (1.0, 1.0, 1.0)],
    lod=(0.0, 0.0, 0.0, 2.5), gain=(1, 1, 1, 1),
    ldir=(-0.0015, 0.0025), lcol=(1.0, 0.92, 0.8), amb=(0.03, 0.035, 0.05),
    bg0=(0.004, 0.005, 0.008), bg1=(0.012, 0.014, 0.02),
    blcol=(0.25, 0.18, 0.12), blpos=(0.6, 0.6, 0.45),
    shadowk=0.06, refr=0.02, bump=6.0, rim=0.6, opac=1.2, deep=0.25,
    exposure=1.0, grain=0.035, vign=0.35,
    lift=(0.0, 0.0, 0.0), gamma_=(2.2, 2.2, 2.2), gainc=(1.0, 1.0, 1.0),
    view=(0.0, 0.0, 1.0, 1.0), fade=0.0, hl=(0.0, 0.0, 1.0, 1.0), hlk=0.0,
)


class Look:
    W, H, BARS = 1080, 1920, 0          # v2: native vertical, no letterbox

    def __init__(self, ctx):
        self.ctx = ctx
        self.quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], "f4"))
        self.prog = ctx.program(vertex_shader=VS, fragment_shader="#version 410\n" + LOOK)
        self.va = ctx.vertex_array(self.prog, [(self.quad, "2f", "pos")])
        self.out = ctx.texture((self.W, self.H), 4)
        self.fbo = ctx.framebuffer([self.out])
        self.mip = None

    def render(self, dye_tex, seed, **params):
        P = dict(LOOK_DEFAULT)
        P.update(params)
        # mip chain of the ink for depth of field / soft lighting
        if self.mip is None or self.mip.size != dye_tex.size:
            self.mip = self.ctx.texture(dye_tex.size, 4, dtype="f2")
            self.mip.repeat_x = self.mip.repeat_y = False
            self.mipfbo = self.ctx.framebuffer([self.mip])
        if not hasattr(self, "srcfb"):
            self.srcfb = {}
        if dye_tex.glo not in self.srcfb:
            self.srcfb[dye_tex.glo] = self.ctx.framebuffer([dye_tex])
        self.ctx.copy_framebuffer(self.mipfbo, self.srcfb[dye_tex.glo])
        self.mip.build_mipmaps()
        self.mip.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        self.mip.use(0)
        p = self.prog
        p["dye"].value = 0
        for k, v in P.items():
            if k not in p:
                continue
            if k in ("pig", "absb"):
                p[k].write(np.array(v, "f4").tobytes())
            elif k == "gamma_" or k in ("lift", "gainc", "hl"):
                p[k].value = tuple(v)
            else:
                p[k].value = v
        p["res"].value = (self.W, self.H)
        p["bars"].value = float(self.BARS)
        p["seed"].value = float(seed)
        self.fbo.use()
        self.ctx.viewport = (0, 0, self.W, self.H)
        self.va.render(moderngl.TRIANGLES)
        img = np.frombuffer(self.fbo.read(components=3), "u1").reshape(self.H, self.W, 3)
        return img[::-1]
