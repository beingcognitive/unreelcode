// look.glsl -- turns four ink-density layers into a lit, graded frame (vertical 9:16 in v2).
// Everything here is display shading of the simulated density; nothing moves ink.
uniform sampler2D dye;      // mipmapped density layers
uniform vec3 pig[4];        // scattering colour of each pigment (albedo)
uniform vec3 absb[4];       // absorption (rgb) of each pigment per unit density
uniform vec4 lod;           // depth-of-field blur per layer (mip level)
uniform vec4 gain;          // density multiplier per layer
uniform vec2 ldir;          // direction toward the key light (uv per step)
uniform vec3 lcol;          // key light colour
uniform vec3 amb;           // ambient fill
uniform vec3 bg0, bg1;      // background gradient (bottom, top)
uniform vec3 blcol;         // backlight colour
uniform vec3 blpos;         // backlight centre (uv) and size
uniform float shadowk, refr, bump, rim, opac, deep;
uniform float exposure, grain, seed, vign;
uniform vec3 lift, gamma_, gainc;
uniform vec4 view;          // uv = view.xy + uv * view.zw (camera)
uniform vec2 res;           // output size in pixels
uniform float bars;         // letterbox height in pixels (top and bottom)
uniform float fade;         // 0..1 fade to black
uniform vec4 hl;            // display only: screen-uv rect kept bright (x0, y0, x1, y1)
uniform float hlk;          // how much everything outside hl is dimmed toward the background
in vec2 uv;
out vec4 o;

float tot(vec2 p, float l) { return dot(textureLod(dye, p, l) * gain, vec4(1.0)); }

uint pcg(uint v) {
    uint s = v * 747796405u + 2891336453u;
    uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
    return (w >> 22u) ^ w;
}
float rnd(uvec3 p) { return float(pcg(p.x + pcg(p.y + pcg(p.z)))) / 4294967295.0; }

vec3 aces(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main() {
    vec2 px = uv * res;
    if (px.y < bars || px.y > res.y - bars) { o = vec4(0, 0, 0, 1); return; }
    vec2 s = vec2(uv.x, (px.y - bars) / (res.y - 2.0 * bars));
    vec2 p = view.xy + s * view.zw;
    float aspect = (res.x) / (res.y - 2.0 * bars);

    // density per pigment, each at its own focus
    vec4 d;
    d.x = textureLod(dye, p, lod.x).x;
    d.y = textureLod(dye, p, lod.y).y;
    d.z = textureLod(dye, p, lod.z).z;
    d.w = textureLod(dye, p, lod.w).w;
    d = max(d, 0.0) * gain;

    // 2.5D: a height field from blurred density gives a surface normal
    vec2 e = vec2(1.5) / vec2(textureSize(dye, 0));
    float hx = tot(p + vec2(e.x, 0), 1.5) - tot(p - vec2(e.x, 0), 1.5);
    float hy = tot(p + vec2(0, e.y), 1.5) - tot(p - vec2(0, e.y), 1.5);
    vec3 n = normalize(vec3(-hx * bump, -hy * bump, 1.0));

    // self-shadow: march toward the key light through blurred ink
    float sh = 0.0;
    for (int i = 1; i <= 12; i++) {
        float f = float(i);
        sh += tot(p + ldir * f * f * 0.6, 1.0 + f * 0.25) * (0.6 + 0.08 * f);
    }
    float T_sh = exp(-shadowk * sh);

    // background with a soft backlight; refracted by the ink's gradient
    vec2 q = s + vec2(hx, hy) * refr;
    vec3 bg = mix(bg0, bg1, smoothstep(0.0, 1.0, q.y));
    vec2 bd = (q - blpos.xy) * vec2(aspect, 1.0);
    bg += blcol * exp(-dot(bd, bd) / (blpos.z * blpos.z));

    // ink: absorbs the backlight, scatters the key light
    vec3 tau = absb[0] * d.x + absb[1] * d.y + absb[2] * d.z + absb[3] * d.w;
    vec3 T = exp(-tau);
    float D = d.x + d.y + d.z + d.w;
    float alpha = 1.0 - exp(-opac * D);
    vec3 alb = (pig[0] * d.x + pig[1] * d.y + pig[2] * d.z + pig[3] * d.w) / max(D, 1e-4);
    alb *= exp(-tau * deep);                           // light inside thick ink is coloured further
    vec3 L3 = normalize(vec3(ldir * 400.0, 0.6));
    float diff = 0.35 + 0.65 * max(dot(n, L3), 0.0);
    float edge = alpha * (1.0 - alpha) * 4.0;          // thin ink lets the backlight through
    vec3 lit = lcol * T_sh * diff + amb;
    vec3 col = bg * T + alb * alpha * lit + bg * edge * rim * alb;
    // display-only emphasis: wash everything outside the highlight rect toward the background
    float inside = step(hl.x, s.x) * step(s.x, hl.z) * step(hl.y, s.y) * step(s.y, hl.w);
    col = mix(col, bg, hlk * 0.72 * (1.0 - inside));
    col *= exposure;
    col = aces(col);
    // grade
    col = pow(max(col * gainc + lift * (1.0 - col), 0.0), 1.0 / gamma_);
    vec2 vq = (s - 0.5) * vec2(aspect, 1.0);
    col *= 1.0 - vign * dot(vq, vq);
    col *= 1.0 - fade;
    // film grain: per-pixel hash (no lattice), stronger in the mids
    uvec3 g = uvec3(uvec2(px), uint(seed));
    float gr = (rnd(g) + rnd(g + uvec3(0, 0, 7919u)) - 1.0);
    float l = dot(col, vec3(0.3, 0.6, 0.1));
    col += grain * gr * (0.35 + 1.4 * l * (1.0 - l));
    col += (rnd(g + uvec3(0, 0, 104729u)) + rnd(g + uvec3(0, 0, 15485863u)) - 1.0) * 1.5 / 255.0;   // TPDF dither vs banding
    o = vec4(clamp(col, 0.0, 1.0), 1.0);
}
