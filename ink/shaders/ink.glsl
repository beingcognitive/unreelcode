// ink.glsl -- every pass of the ink solver (stable fluids, MacCormack advection,
// vorticity confinement, Jacobi pressure). ink.py compiles one program per #define.
// Units: velocity in velocity-grid cells per second, dye = ink density per layer.

uniform sampler2D vel;   // velocity grid
uniform sampler2D dye;   // four ink layers, rgba
uniform sampler2D src;   // field being advected / splatted
uniform sampler2D hat;   // forward-advected field (MacCormack)
uniform sampler2D prs;   // pressure
uniform sampler2D div;   // divergence
uniform vec3 dx;         // (1/W, 1/H, 0) of the velocity grid
uniform float dt;
in vec2 uv;
out vec4 o;

// vorticity (curl of the velocity) at p
float curl(vec2 p) {
    return 0.5 * (texture(vel, p + dx.xz).y - texture(vel, p - dx.xz).y
                - texture(vel, p + dx.zy).x + texture(vel, p - dx.zy).x);
}

#ifdef FORCES
// vorticity confinement: push along the curl gradient
vec2 swirl(vec2 p) {
    float L = abs(curl(p - dx.xz)), R = abs(curl(p + dx.xz));
    float B = abs(curl(p - dx.zy)), T = abs(curl(p + dx.zy));
    vec2 n = vec2(T - B, R - L);
    n /= length(n) + 1e-5;
    return curl(p) * vec2(n.x, -n.y);
}
float total(vec2 p) { return dot(texture(dye, p), vec4(1.0)); }

// forces on the water
// CURL: how much the ink swirls
const float CURL = 0.0;
// ink is heavier than water
const float SINK = 30.0;
void main() {
  vec2 v = texture(vel, uv).xy;
  v += dt * CURL * swirl(uv);
  v.y -= dt * SINK * total(uv);
  o = vec4(v, 0.0, 1.0);
}
#endif

#ifdef ADVECT
// semi-Lagrangian step with an RK2 backtrace: src(x - dt * u)
void main() {
    vec2 u = texture(vel, uv).xy;
    vec2 m = uv - 0.5 * dt * u * dx.xy;
    o = texture(src, uv - dt * texture(vel, m).xy * dx.xy);
}
#endif

#ifdef MACCORMACK
// error-corrected advection, clamped to the source texels it came from
uniform float keep;      // per-step dissipation (1 = none)
void main() {
    vec2 u = texture(vel, uv).xy;
    vec2 m = uv - 0.5 * dt * u * dx.xy;
    vec2 back = uv - dt * texture(vel, m).xy * dx.xy;
    vec2 fwd = uv + dt * u * dx.xy;
    vec4 phi = texture(hat, uv) + 0.5 * (texture(src, uv) - texture(hat, fwd));
    vec2 sz = vec2(textureSize(src, 0));
    vec2 t = back * sz - 0.5;
    ivec2 i = ivec2(floor(t));
    ivec2 hi = ivec2(sz) - 1;
    vec4 a = texelFetch(src, clamp(i, ivec2(0), hi), 0);
    vec4 b = texelFetch(src, clamp(i + ivec2(1, 0), ivec2(0), hi), 0);
    vec4 c = texelFetch(src, clamp(i + ivec2(0, 1), ivec2(0), hi), 0);
    vec4 d = texelFetch(src, clamp(i + ivec2(1, 1), ivec2(0), hi), 0);
    phi = clamp(phi, min(min(a, b), min(c, d)), max(max(a, b), max(c, d)));
    o = phi * keep;
}
#endif

#ifdef SPLAT
// add a soft blob of momentum or ink
uniform vec2 at;         // centre, uv
uniform vec2 radius;     // gaussian radius in uv (x already aspect-corrected)
uniform vec4 amount;
void main() {
    vec2 d = (uv - at) / radius;
    o = texture(src, uv) + amount * exp(-dot(d, d));
}
#endif

#ifdef DIVERGENCE
void main() {
    float L = texture(vel, uv - dx.xz).x, R = texture(vel, uv + dx.xz).x;
    float B = texture(vel, uv - dx.zy).y, T = texture(vel, uv + dx.zy).y;
    o = vec4(0.5 * (R - L + T - B), 0.0, 0.0, 1.0);
}
#endif

#ifdef JACOBI
void main() {
    float L = texture(prs, uv - dx.xz).x, R = texture(prs, uv + dx.xz).x;
    float B = texture(prs, uv - dx.zy).x, T = texture(prs, uv + dx.zy).x;
    o = vec4(0.25 * (L + R + B + T - texture(div, uv).x), 0.0, 0.0, 1.0);
}
#endif

#ifdef PROJECT
// subtract the pressure gradient: the water cannot be compressed
void main() {
    float L = texture(prs, uv - dx.xz).x, R = texture(prs, uv + dx.xz).x;
    float B = texture(prs, uv - dx.zy).x, T = texture(prs, uv + dx.zy).x;
    vec2 v = texture(vel, uv).xy - 0.5 * vec2(R - L, T - B);
    // closed tank: no flow through the walls
    vec2 c = uv / dx.xy;
    vec2 lim = 1.0 / dx.xy - 1.0;
    if (c.x < 1.0 || c.x > lim.x) v.x = 0.0;
    if (c.y < 1.0 || c.y > lim.y) v.y = 0.0;
    o = vec4(v, 0.0, 1.0);
}
#endif
