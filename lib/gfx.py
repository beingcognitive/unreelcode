"""Shared GPU drawing: instanced SDF capsules / discs / balls (moderngl), 1080x1920."""
import moderngl
import numpy as np

W, H = 1080, 1920

VS = """
#version 330
in vec2 corner;
in vec4 a; in vec4 b; in vec4 col; in vec4 col2;
uniform vec2 cam; uniform float scale; uniform vec2 res; uniform float pad;
out vec2 wp; flat out vec4 A; flat out vec4 B; flat out vec4 C; flat out vec4 C2;
void main(){
    float r = b.x + (int(b.y + 0.5) == 6 ? 0.0 : b.w);
    vec2 lo = min(a.xy, a.zw) - r - pad / scale, hi = max(a.xy, a.zw) + r + pad / scale;
    vec2 w = mix(lo, hi, corner * 0.5 + 0.5);
    wp = w;
    vec2 s = (w - cam) * scale + res * 0.5;
    gl_Position = vec4(s.x / res.x * 2.0 - 1.0, 1.0 - s.y / res.y * 2.0, 0.0, 1.0);
    A = a; B = b; C = col; C2 = col2;
}
"""
# b = (radius, type, param, glow_radius)
FS = """
#version 330
in vec2 wp; flat in vec4 A; flat in vec4 B; flat in vec4 C; flat in vec4 C2;
uniform float scale;
out vec4 o;
float sdCap(vec2 p, vec2 a, vec2 b){ vec2 pa=p-a, ba=b-a; float h=clamp(dot(pa,ba)/max(dot(ba,ba),1e-6),0.,1.); return length(pa-ba*h); }
void main(){
    float aa = 1.0 / scale;
    int type = int(B.y + 0.5);
    float r = B.x;
    float d0 = sdCap(wp, A.xy, A.zw);
    float d = d0 - r;
    float cov = 1.0 - smoothstep(-aa, aa, d);
    vec3 c = C.rgb;
    if (type == 0) {                       // flat capsule with soft tube shading
        float t = clamp(d0 / max(r, 1e-3), 0., 1.);
        vec2 ab = normalize(A.zw - A.xy + vec2(1e-5));
        vec2 nn = vec2(-ab.y, ab.x);
        float side = sign(dot(wp - A.xy, nn));
        c = C.rgb * (0.80 + 0.30 * (1.0 - t * t)) + C.rgb * 0.25 * side * t;
    } else if (type == 1) {                // wood bar: grain + flash
        vec2 ab = normalize(A.zw - A.xy + vec2(1e-5));
        float s = dot(wp - A.xy, ab);
        float q = dot(wp - A.xy, vec2(-ab.y, ab.x));
        float grain = 0.06 * sin(s * 0.9 + 3.0 * sin(q * 0.35 + B.z)) + 0.04 * sin(s * 2.3 + B.z * 3.0);
        float t = clamp(d0 / max(r, 1e-3), 0., 1.);
        c = C.rgb * (0.85 + grain) * (0.82 + 0.25 * (1.0 - t * t));
        c = mix(c, C2.rgb, C2.a);
    } else if (type == 2) {                // chrome / glossy ball
        vec2 q = (wp - A.xy) / r;
        float rr = dot(q, q);
        float z = sqrt(max(0., 1. - rr));
        vec3 N = vec3(q, z);
        vec3 L = normalize(vec3(-0.4, -0.75, 0.6));
        float dif = clamp(dot(N, L), 0., 1.);
        float env = 0.5 + 0.5 * N.y;                  // floor-ish reflection below, sky above
        vec3 base = C.rgb;
        if (B.z > 0.5) {                              // chrome
            c = mix(vec3(0.95, 0.85, 0.70) * 0.35, vec3(0.98, 0.95, 0.9), smoothstep(0.35, 0.65, 1.0 - env));
            c = mix(c, base, 0.25) * (0.55 + 0.6 * dif);
        } else {                                      // glossy dark pearl
            c = base * (0.35 + 0.75 * dif);
        }
        c += vec3(1.0) * pow(clamp(dot(reflect(-L, N), vec3(0, 0, 1)), 0., 1.), 30.0) * 0.9;
        c *= 1.0 - 0.25 * smoothstep(0.8, 1.0, sqrt(rr));
    } else if (type == 3) {                // glow (additive look via alpha falloff)
        float g = exp(-max(d0, 0.0) / max(B.w, 1.0));
        o = vec4(C.rgb, C.a * g);
        return;
    } else if (type == 5) {                // premultiplied glow, for MAX blending (seamless trails)
        float g = exp(-max(d0, 0.0) / max(B.w, 1.0));
        o = vec4(C.rgb * C.a * g, 1.0);
        return;
    } else if (type == 6) {                // a little star with a face; param = rotation, glow = face on/off
        float ca = cos(B.z), sa = sin(B.z);
        vec2 p = wp - A.xy;
        p = vec2(ca * p.x + sa * p.y, -sa * p.x + ca * p.y);
        p.y = -p.y;
        float R = r;
        const vec2 k1 = vec2(0.809016994375, -0.587785252292);
        const vec2 k2 = vec2(-0.809016994375, -0.587785252292);
        vec2 q = vec2(abs(p.x), p.y);
        q -= 2.0 * max(dot(k1, q), 0.0) * k1;
        q -= 2.0 * max(dot(k2, q), 0.0) * k2;
        q.x = abs(q.x);
        q.y -= R;
        vec2 ba = 0.48 * vec2(-k1.y, k1.x) - vec2(0.0, 1.0);
        float h = clamp(dot(q, ba) / dot(ba, ba), 0.0, R);
        float ds = length(q - ba * h) * sign(q.y * ba.x - q.x * ba.y) - R * 0.12;
        float cv = 1.0 - smoothstep(-aa, aa, ds);
        vec3 sc = C.rgb * (1.0 + 0.25 * clamp(p.y / R, -1.0, 1.0));
        sc = mix(sc * vec3(0.92, 0.8, 0.6), sc, smoothstep(-2.0 * aa - 1.5, -0.5, ds));
        if (B.w > 0.5) {
            vec2 e = p / R;
            float ey = 0.02;
            float k = 1.0 - smoothstep(0.075, 0.075 + 1.5 / (R * scale), min(length(e - vec2(-0.2, ey)), length(e - vec2(0.2, ey))));
            sc = mix(sc, vec3(0.35, 0.22, 0.12), k);
            float m = abs(length(e - vec2(0.0, 0.0)) - 0.13);
            sc = mix(sc, vec3(0.35, 0.22, 0.12), (1.0 - smoothstep(0.03, 0.03 + 1.5 / (R * scale), m)) * step(e.y, -0.05) * step(abs(e.x), 0.09));
        }
        o = vec4(sc, cv * C.a);
        return;
    } else if (type == 4) {                // plain fill
        c = C.rgb;
    }
    o = vec4(c, cov * C.a);
}
"""
BG_FS = """
#version 330
in vec2 uv; out vec4 o;
uniform vec3 top; uniform vec3 bot; uniform vec3 spot; uniform vec2 spotpos; uniform float spotr;
void main(){
    vec3 c = mix(top, bot, uv.y);
    vec2 p = vec2(uv.x, 1.0 - uv.y) * vec2(1080., 1920.);
    float s = exp(-pow(length(p - spotpos) / spotr, 2.0));
    c += spot * s;
    o = vec4(c, 1.0);
}
"""
BG_VS = """
#version 330
in vec2 corner; out vec2 uv;
void main(){ uv = corner * 0.5 + 0.5; uv.y = 1.0 - uv.y; gl_Position = vec4(corner, 0., 1.); }
"""


class GPU:
    def __init__(self):
        self.ctx = moderngl.create_standalone_context()
        self.fbo = self.ctx.simple_framebuffer((W, H), components=4)
        self.prog = self.ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.bg = self.ctx.program(vertex_shader=BG_VS, fragment_shader=BG_FS)
        q = self.ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32))
        self.bgvao = self.ctx.vertex_array(self.bg, [(q, "2f", "corner")])
        self.ibuf = self.ctx.buffer(reserve=4 * 16 * 40000)
        self.vao = self.ctx.vertex_array(self.prog, [(q, "2f", "corner"),
                                                     (self.ibuf, "4f 4f 4f 4f/i", "a", "b", "col", "col2")])
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def begin(self, cam, top, bot, spot=(0, 0, 0), spotpos=(540, 600), spotr=900.0):
        self.fbo.use()
        self.fbo.clear(0, 0, 0, 1)
        self.bg["top"].value = top
        self.bg["bot"].value = bot
        self.bg["spot"].value = spot
        self.bg["spotpos"].value = spotpos
        self.bg["spotr"].value = spotr
        self.bgvao.render(moderngl.TRIANGLE_STRIP)
        cx, cy, s = cam
        self.prog["cam"].value = (cx, cy)
        self.prog["scale"].value = s
        self.prog["res"].value = (W, H)

    def draw(self, inst, pad=2.0, additive=False, maxblend=False):
        if not len(inst):
            return
        data = np.asarray(inst, np.float32).reshape(-1, 16)
        for i in range(0, len(data), 40000):
            chunk = data[i:i + 40000]
            self.ibuf.write(chunk.tobytes())
            self.prog["pad"].value = pad
            if additive:
                self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
            if maxblend:
                self.ctx.blend_equation = moderngl.MAX
            self.vao.render(moderngl.TRIANGLE_STRIP, instances=len(chunk))
            if maxblend:
                self.ctx.blend_equation = moderngl.FUNC_ADD
            if additive:
                self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    def read(self):
        return np.frombuffer(self.fbo.read(components=3), np.uint8).reshape(H, W, 3)[::-1].copy()


def I(p0, p1, r, typ, col, col2=(0, 0, 0, 0), param=0.0, glow=0.0):
    return [p0[0], p0[1], p1[0], p1[1], r, typ, param, glow, *col, *col2]
