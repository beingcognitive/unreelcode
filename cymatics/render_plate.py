"""Renders the sand plate with moderngl: shadow-mapped raking key light, grain impostors with glints,
heap height from grain density, motion streaks for flying grains, depth-of-field, filmic tonemap,
film grain. v3: native vertical 1080x1920, no letterbox.  Frames are piped to ffmpeg per shot."""
import numpy as np, moderngl, torch, math, subprocess, sys, os, time
import plate as P

W, H = 1080, 1920
SS = 1.5
RW, RH = int(W * SS), int(H * SS)
FPS = 30
import shutil
FF = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'

def look_at(eye, tgt, up=(0, 0, 1)):
    eye, tgt, up = map(np.array, (eye, tgt, up))
    f = tgt - eye; f = f / np.linalg.norm(f)
    s = np.cross(f, up); s /= np.linalg.norm(s); u = np.cross(s, f)
    M = np.eye(4); M[0, :3] = s; M[1, :3] = u; M[2, :3] = -f
    M[:3, 3] = -M[:3, :3] @ eye
    return M

def persp(fov, asp, n, f, shift=(0, 0)):
    t = 1 / math.tan(math.radians(fov) / 2)
    M = np.zeros((4, 4)); M[0, 0] = t / asp; M[1, 1] = t
    M[0, 2] = shift[0]; M[1, 2] = shift[1]
    M[2, 2] = (f + n) / (n - f); M[2, 3] = 2 * f * n / (n - f); M[3, 2] = -1
    return M

def ortho(l, r, b, t, n, f):
    M = np.eye(4); M[0, 0] = 2 / (r - l); M[1, 1] = 2 / (t - b); M[2, 2] = -2 / (f - n)
    M[0, 3] = -(r + l) / (r - l); M[1, 3] = -(t + b) / (t - b); M[2, 3] = -(f + n) / (f - n)
    return M

def m4(M): return M.T.astype('f4').tobytes()

COMMON = """
#version 410
uniform mat4 VP; uniform mat4 LVP; uniform vec3 eye; uniform vec3 Ldir; uniform vec3 Lcol;
uniform sampler2D shadow; uniform sampler2D heap; uniform float heapScale;
float hash(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }
float shadowAt(vec3 wp, float bias){
  vec4 c = LVP*vec4(wp,1.0); vec3 q = c.xyz/c.w*0.5+0.5;
  if(q.x<0.||q.x>1.||q.y<0.||q.y>1.) return 1.0;
  float s=0.; vec2 ts = 1.0/vec2(textureSize(shadow,0));
  for(int i=-1;i<=1;i++) for(int j=-1;j<=1;j++){
    float d = texture(shadow, q.xy+vec2(i,j)*ts).r; s += (q.z-bias > d) ? 0.0 : 1.0; }
  return s/9.0;
}
float heapH(vec2 xy){ return texture(heap, xy*0.5+0.5).r*heapScale; }
"""

PLATE_VS = """
in vec2 pos; out vec3 wp;
void main(){ wp = vec3(pos*1.6, 0.0); if(abs(pos.x)>1.0||abs(pos.y)>1.0) wp.z=-0.15; gl_Position = VP*vec4(wp,1.0);}"""
PLATE_FS = """
in vec3 wp; out vec4 o; uniform float time;
// rotated-octave value noise (avoids single-lattice grid)
float vn(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float s=0., a=.5; mat2 R=mat2(.8,-.6,.6,.8); for(int i=0;i<5;i++){ s+=a*vn(p); p=R*p*2.03+17.1; a*=.5;} return s; }
vec3 bg(vec3 d){ return vec3(0.0); }
void main(){
  vec3 V = normalize(eye-wp);
  bool onPlate = abs(wp.x)<=1.0 && abs(wp.y)<=1.0;
  if(!onPlate){
    // dark studio floor far below plate: very dim falloff
    float r = length(wp.xy);
    o = vec4(vec3(0.006,0.0055,0.005)*exp(-r*0.6), 1.0); return; }
  // brushed anodised aluminium: anisotropic micro-normal along x (brush direction), slight waviness
  float br = fbm(vec2(wp.x*6.0, wp.y*900.0)) - 0.5;
  float wav = fbm(wp.xy*3.0) - 0.5;
  vec3 N = normalize(vec3(0.0, br*0.05 + wav*0.01, 1.0));
  vec3 L = normalize(-Ldir); vec3 Hh = normalize(L+V);
  float sh = shadowAt(wp, 0.000005);
  float nh = max(dot(N,Hh),0.);
  float rough = 0.28; float a2 = rough*rough;
  float D = a2/(3.14159*pow(nh*nh*(a2-1.)+1.,2.));
  float fres = 0.04 + 0.96*pow(1.-max(dot(Hh,V),0.),5.);
  float spec = D*fres*max(dot(N,L),0.)*0.25;
  vec3 base = vec3(0.012,0.012,0.014)*(0.85+0.3*fbm(wp.xy*40.0));
  vec3 col = base*max(dot(N,L),0.)*Lcol*sh*0.35 + spec*Lcol*sh*vec3(0.85,0.9,1.0);
  // soft overhead fill reflected in the plate (a large dim softbox)
  vec3 Rr = reflect(-V,N); float soft = smoothstep(0.75,0.98,Rr.z)*0.010;
  col += vec3(soft)*vec3(0.8,0.85,1.0);
  // big softbox behind the key: broad sheen on the anodised surface
  float sb = smoothstep(0.55,0.97,dot(Rr,L));
  col += Lcol*sb*sb*0.012;
  // centre bolt: hex nut, dark with a bright chamfer edge
  float r = length(wp.xy);
  if(r<0.032){ float rim = smoothstep(0.024,0.030,r)*(1.-smoothstep(0.030,0.032,r));
    vec3 n2 = normalize(vec3(wp.xy/r*rim*0.8, 1.0)); float s2 = pow(max(dot(reflect(-L,n2),V),0.),60.);
    col = vec3(0.004) + s2*Lcol*0.25*sh; }
  // plate edge highlight (0.5 mm edge catches the key)
  float e = max(abs(wp.x),abs(wp.y)); col += Lcol*smoothstep(0.996,1.0,e)*0.05*sh;
  o = vec4(col,1.0);
}"""

GRAIN_VS = """
in vec4 pa; in vec4 pb; // x y z size | vx vy vz tint
uniform vec2 res; uniform float shutter; uniform vec3 camR; uniform vec3 camU;
out vec2 uv; out vec3 gc; out float tint; out float seed; out float fadeA; out float segs;
void main(){
  int c = gl_VertexID; vec2 corner = vec2((c==1||c==2||c==4)?1.:-1., (c==2||c==4||c==5)?1.:-1.);
  float r = 0.0011*(0.6+0.8*pa.w);
  vec3 p = vec3(pa.xy, pa.z + heapH(pa.xy) + r*0.7);
  vec3 p0 = p - pb.xyz*shutter;     // position at shutter open
  vec4 c1 = VP*vec4(p,1.0), c0 = VP*vec4(p0,1.0);
  // screen-space radius; keep at least 0.7 px (coverage fades instead)
  float rpx = r/c1.w*res.y*0.5*VP[1][1];
  float k = max(1.0, 0.7/max(rpx,1e-5)); fadeA = 1.0/(k*k);
  vec2 s1 = c1.xy/c1.w, s0 = c0.xy/c0.w;
  vec2 d = (s1-s0)*res*0.5; float L = length(d);
  vec2 ax = L>0.5 ? d/L : vec2(1,0); vec2 ay = vec2(-ax.y, ax.x);
  vec2 rad = vec2(rpx*k);
  vec2 mid = (s1+s0)*0.5;
  vec2 off = ax*corner.x*(rad.x + L*0.5) + ay*corner.y*rad.y;
  gl_Position = vec4((mid + off/(res*0.5))*c1.w, c1.z, c1.w);
  uv = vec2(corner.x*(1.0 + L*0.5/rad.x), corner.y); uv.x = corner.x*(rad.x+L*0.5)/rad.x;
  fadeA *= rad.x/(rad.x+L*0.5); segs = L*0.5/rad.x;
  gc = p; tint = pb.w; seed = pa.w*91.7 + pa.x*13.1;
}"""
GRAIN_FS = """
in vec2 uv; in vec3 gc; in float tint; in float seed; in float fadeA; in float segs; out vec4 o;
uniform vec3 camR; uniform vec3 camU; uniform float glint; uniform vec3 fwd;
void main(){
  // capsule along x
  vec2 q = uv; float ext = abs(q.x)-segs;
  vec2 qq = vec2(max(ext,0.0)*sign(q.x), q.y);
  float rr = dot(qq,qq); if(rr>1.0) discard;
  float zz = sqrt(1.0-rr);
  vec3 N = normalize(camR*qq.x + camU*qq.y - fwd*zz);
  // irregular grain: perturb normal per grain
  vec3 jit = vec3(hash(vec2(seed,1.)),hash(vec2(seed,2.)),hash(vec2(seed,3.)))-0.5;
  vec3 Nf = normalize(N + jit*0.9);
  vec3 L = normalize(-Ldir); vec3 V = -fwd;
  float sh = shadowAt(gc, 0.00008);
  vec3 alb = mix(vec3(0.72,0.62,0.47), vec3(0.86,0.82,0.74), tint);
  if(tint>0.93) alb = vec3(0.22,0.19,0.16);            // a few dark grains
  float lam = max(dot(N,L),0.0);
  vec3 col = alb*(lam*Lcol*sh*0.9 + vec3(0.010,0.011,0.014));
  // facet glint: quartz facets catch the key
  vec3 Hh = normalize(L+V);
  float g = pow(max(dot(Nf,Hh),0.0), 300.0) * step(0.55, hash(vec2(seed,7.)));
  col += Lcol*g*glint*sh;
  o = vec4(col, 1.0);
  if(hash(gl_FragCoord.xy*0.37+seed) > fadeA) discard;   // stochastic coverage for sub-pixel grains
}"""

SHADOW_VS = """
in vec4 pa;
void main(){ float r = 0.0011*(0.6+0.8*pa.w);
  vec3 p = vec3(pa.xy, pa.z + heapH(pa.xy) + r*0.7);
  gl_Position = LVP*vec4(p,1.0); gl_PointSize = 2.0; }"""
SHADOW_FS = "out vec4 o; void main(){ o=vec4(1); }"

QUAD_VS = "#version 410\nin vec2 pos; out vec2 v; void main(){ v=pos*0.5+0.5; gl_Position=vec4(pos,0,1);}"
DOF_FS = """#version 410
in vec2 v; out vec4 o; uniform sampler2D col; uniform sampler2D dep;
uniform float nearp, farp, focus, aper, maxc; uniform vec2 res;
float lin(float d){ float z=d*2.-1.; return 2.*nearp*farp/(farp+nearp-z*(farp-nearp)); }
float coc(float z){ return clamp(aper*abs(1.0-focus/z), 0.0, maxc); }
void main(){
  float z0 = lin(texture(dep,v).r); float c0 = coc(z0);
  vec3 acc = vec3(0); float w = 0.;
  const int NT = 64; const float GA = 2.39996;
  for(int i=0;i<NT;i++){
    float r = sqrt((float(i)+0.5)/float(NT))*maxc; float a = float(i)*GA;
    vec2 off = vec2(cos(a),sin(a))*r;
    vec2 uv2 = v + off/res;
    float zs = lin(texture(dep,uv2).r); float cs = coc(zs);
    // sample contributes if its own CoC reaches us; foreground can bleed over background
    float reach = (zs < z0) ? cs : min(cs, c0);
    float wt = smoothstep(r-1.0, r+0.5, reach) / max(reach*reach, 1.0);
    if(i==0) wt = 1.0/max(c0*c0,1.0);
    acc += texture(col,uv2).rgb*wt; w += wt;
  }
  o = vec4(acc/max(w,1e-6),1.0);
}"""
FINAL_FS = """#version 410
in vec2 v; out vec4 o; uniform sampler2D img; uniform float expo; uniform float frame; uniform vec2 res;
uniform float lbox; uniform float fade;
float h(vec2 p){ p = fract(p*vec2(443.897,441.423)); p += dot(p, p.yx+19.19); return fract((p.x+p.y)*p.x); }
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.,1.); }
void main(){
  vec2 px = 1.0/res;   // supersampled -> 1080: 4-tap box
  vec3 c = (texture(img,v+vec2(-.25,-.25)*px).rgb+texture(img,v+vec2(.25,-.25)*px).rgb+
            texture(img,v+vec2(-.25,.25)*px).rgb+texture(img,v+vec2(.25,.25)*px).rgb)*0.25;
  c = aces(c*expo);
  float vig = 1.0 - 0.35*pow(length((v-0.5)*vec2(0.75,1.0))*1.35, 2.5); c *= vig;
  c = pow(c, vec3(1.0/2.2));
  // film grain: two hashed octaves (no lattice), mid-tone weighted
  float n = (h(v*res*0.5+frame*1.37) + h(v*res*0.5*0.707+vec2(frame*0.71,3.1)) - 1.0);
  float lum = dot(c, vec3(0.3,0.59,0.11));
  c += n*0.035*(0.35+lum*(1.0-lum)*2.0);
  c *= fade;
  if(v.y < lbox || v.y > 1.0-lbox) c = vec3(0);
  o = vec4(c,1.0);
}"""

class Renderer:
    def __init__(self, n):
        self.ctx = ctx = moderngl.create_standalone_context(require=410)
        self.n = n
        self.col = ctx.texture((RW, RH), 4, dtype='f2'); self.dep = ctx.depth_texture((RW, RH))
        self.fbo = ctx.framebuffer([self.col], self.dep)
        self.dofc = ctx.texture((RW, RH), 4, dtype='f2'); self.dofc.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.dofbo = ctx.framebuffer([self.dofc])
        self.out = ctx.texture((W, H), 3); self.outbo = ctx.framebuffer([self.out])
        SM = 4096
        self.smap = ctx.depth_texture((SM, SM)); self.smfbo = ctx.framebuffer(depth_attachment=self.smap)
        self.heap = ctx.texture((512, 512), 1, dtype='f4'); self.heap.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.col.filter = (moderngl.LINEAR, moderngl.LINEAR); self.dep.filter = (moderngl.NEAREST, moderngl.NEAREST)
        # v3.2: clamp, don't wrap: the depth-of-field gather near the top edge was sampling the bottom of the frame
        for tx in (self.col, self.dep, self.dofc): tx.repeat_x = False; tx.repeat_y = False
        self.smap.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.pplate = ctx.program(vertex_shader=COMMON + PLATE_VS, fragment_shader=COMMON + PLATE_FS)
        self.pgrain = ctx.program(vertex_shader=COMMON + GRAIN_VS, fragment_shader=COMMON + GRAIN_FS)
        self.pshadow = ctx.program(vertex_shader=COMMON + SHADOW_VS, fragment_shader=COMMON + SHADOW_FS)
        self.pdof = ctx.program(vertex_shader=QUAD_VS, fragment_shader=DOF_FS)
        self.pfin = ctx.program(vertex_shader=QUAD_VS, fragment_shader=FINAL_FS)
        quad = ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], 'f4'))
        g = np.linspace(-1, 1, 3)
        big = ctx.buffer((np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], 'f4').reshape(-1, 2) * 12).astype('f4'))
        self.vplate = ctx.vertex_array(self.pplate, [(ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], 'f4') * 1 / 1.6), '2f', 'pos')])
        self.vfloor = ctx.vertex_array(self.pplate, [(big, '2f', 'pos')])
        self.ba = ctx.buffer(reserve=n * 16); self.bb = ctx.buffer(reserve=n * 16)
        self.vgrain = ctx.vertex_array(self.pgrain, [(self.ba, '4f/i', 'pa'), (self.bb, '4f/i', 'pb')])
        self.vshadow = ctx.vertex_array(self.pshadow, [(self.ba, '4f', 'pa')])
        self.vdof = ctx.vertex_array(self.pdof, [(quad, '2f', 'pos')])
        self.vfin = ctx.vertex_array(self.pfin, [(quad, '2f', 'pos')])
        ctx.enable(moderngl.PROGRAM_POINT_SIZE)

    def set(self, prog, **kw):
        for k, v in kw.items():
            if k in prog:
                if isinstance(v, np.ndarray) and v.shape == (4, 4): prog[k].write(m4(v))
                else: prog[k].value = v

    def frame(self, sand, cam, fi, light, heapgrid):
        ctx = self.ctx
        eye, tgt, fov, focus, aper, expo, shift, glint = cam
        V = look_at(eye, tgt); Pm = persp(fov, W / H, 0.01, 30.0, shift); VP = Pm @ V
        Ld = np.array(light, 'f8'); Ld /= np.linalg.norm(Ld)
        LV = look_at(-Ld * 4, (0, 0, 0), up=(0, 1, 0) if abs(Ld[2]) > 0.9 else (0, 0, 1))
        LVP = ortho(-1.45, 1.45, -1.45, 1.45, 0.5, 8) @ LV
        Lcol = (3.2, 2.95, 2.65)
        # upload grains
        p = sand.p; z = sand.z; v = sand.v; a = sand.attr
        A = torch.cat([p, z[:, None], a[:, :1]], 1).float().cpu().numpy()
        B = torch.cat([v * sand.fly[:, None].float(), a[:, 1:2]], 1).float().cpu().numpy()
        self.ba.write(A.astype('f4').tobytes()); self.bb.write(B.astype('f4').tobytes())
        self.heap.write(heapgrid.astype('f4').tobytes())
        fwd = np.array(tgt) - np.array(eye); fwd = fwd / np.linalg.norm(fwd)
        camR = np.cross(fwd, (0, 0, 1)); camR /= np.linalg.norm(camR); camU = np.cross(camR, fwd)
        for prog in (self.pplate, self.pgrain, self.pshadow):
            self.set(prog, VP=VP, LVP=LVP, eye=tuple(eye), Ldir=tuple(Ld), Lcol=Lcol, heapScale=1.0,
                     res=(float(RW), float(RH)), shutter=1 / 60, camR=tuple(camR), camU=tuple(camU),
                     glint=glint, fwd=tuple(fwd), shadow=0, heap=1)
        self.heap.use(1)
        # shadow pass
        self.smfbo.use(); self.smfbo.clear(depth=1.0); ctx.enable(moderngl.DEPTH_TEST)
        self.vshadow.render(moderngl.POINTS, vertices=self.n)
        # main pass
        self.fbo.use(); self.fbo.clear(0, 0, 0, 1, depth=1.0)
        self.smap.use(0); self.heap.use(1)
        self.vfloor.render(moderngl.TRIANGLES)
        self.vplate.render(moderngl.TRIANGLES)
        self.vgrain.render(moderngl.TRIANGLES, vertices=6, instances=self.n)
        ctx.disable(moderngl.DEPTH_TEST)
        # dof
        self.dofbo.use(); self.col.use(0); self.dep.use(1)
        self.set(self.pdof, col=0, dep=1, nearp=0.01, farp=30.0, focus=focus, aper=aper * SS, maxc=22.0 * SS,
                 res=(float(RW), float(RH)))
        self.vdof.render(moderngl.TRIANGLES)
        # final
        self.outbo.use(); self.dofc.use(0)
        self.set(self.pfin, img=0, expo=expo, frame=float(fi), res=(float(RW), float(RH)), lbox=0.0, fade=cam_fade(cam))
        self.vfin.render(moderngl.TRIANGLES)
        img = np.frombuffer(self.outbo.read(components=3), np.uint8).reshape(H, W, 3)[::-1]
        return img

def cam_fade(cam): return cam[8] if len(cam) > 8 else 1.0

def heap_grid(sand):
    """grain density on 512^2 -> heap height (plate units).  Only resting grains pile up."""
    g = 512; p = sand.p; rest = (~sand.fly).float()
    ij = ((p * 0.5 + 0.5) * (g - 1)).round().long().clamp(0, g - 1)
    idx = ij[:, 1] * g + ij[:, 0]
    d = torch.zeros(g * g, device=p.device).index_add_(0, idx, rest).view(1, 1, g, g)
    k = torch.tensor([1, 4, 6, 4, 1.], device=p.device); k = (k[:, None] * k[None]) / 256
    for _ in range(2): d = torch.nn.functional.conv2d(d, k[None, None], padding=2)
    mean = sand.n / (g * g)
    # a monolayer is ~1 grain diameter; ridges heap as sqrt of excess density
    h = 0.0012 * torch.sqrt(torch.clamp(d / mean - 1.0, min=0))
    return h[0, 0].cpu().numpy()
