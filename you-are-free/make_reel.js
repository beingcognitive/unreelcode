#!/usr/bin/env node
// YOU ARE FREE -- vertical reel: 64 seconds, 1080x1920, 30 fps.
// Every pixel and every audio sample is computed here; ffmpeg only encodes.
// Usage:  node make_reel.js                         -> we-are-free-vertical.mp4
//         node make_reel.js --test 2,10.2,45 <dir>  -> PNG stills at those times (seconds of film time)
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

// The film is the default run. Two earlier endings are kept, unused, for reference:
//   --ending-a   the flock recedes to a single point on the horizon, with a small drawn title (52.8 s)
//   --big-title  the title as three large stacked lines
const VAR = process.argv.includes('--ending-a') ? 'A' : process.argv.includes('--big-title') ? '' : 'B'; // default: the small one-line title
const W = 1080, H = 1920, FPS = 30, HOLD = 4, DUR = (VAR === 'A' ? 48.8 : 60) + HOLD, NF = Math.round(FPS * DUR), N = 90000;
const CX = W / 2, CY = 800, HALF = 150;
// ---- the timeline, in seconds ----
const T = {
  implode: 9.4,        // a held breath: the lights collapse to a point
  free: 10,            // the cage breaks
  split: 15, dive: 20.5, merge: 26,
  birdIn: 28, birdOut: 34,
  words: VAR === 'B' ? [36.2, 37.6, 39] : [35.5, 38.2, 40.8], // WE / ARE / FREE arrive
  rise: 47.5,          // the words take flight
  fade: VAR === 'A' ? 47.3 : 58,
  far: 36, point: 43.75, // ending A: the flock reappears far off, and becomes one point
};
const FADE_END = VAR === 'A' ? 48.7 : 59.8, DAWN = VAR === 'A' ? 47 : 56, PX = 540, PY = 1300; // PX, PY: where the last point of light rests
const BEATS = [1.5, 2.9, 4.2, 5.4, 6.4, 7.3, 8.0, 8.6, 9.1];
const TAU = Math.PI * 2;

// ---------- helpers ----------
let seed = 20261114;
function rnd() {
  seed = (seed + 0x6D2B79F5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const sstep = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;
function lerp3(c0, c1, c2, d) {
  return d < 0.5
    ? [lerp(c0[0], c1[0], d * 2), lerp(c0[1], c1[1], d * 2), lerp(c0[2], c1[2], d * 2)]
    : [lerp(c1[0], c2[0], d * 2 - 1), lerp(c1[1], c2[1], d * 2 - 1), lerp(c1[2], c2[2], d * 2 - 1)];
}
function hash3(i, j, k) {
  let h = (Math.imul(i, 374761393) + Math.imul(j, 668265263) + Math.imul(k, 1274126177)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
function noise3(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  let fx = x - xi, fy = y - yi, fz = z - zi;
  fx = fx * fx * fx * (fx * (fx * 6 - 15) + 10);
  fy = fy * fy * fy * (fy * (fy * 6 - 15) + 10);
  fz = fz * fz * fz * (fz * (fz * 6 - 15) + 10);
  const a = lerp(lerp(hash3(xi, yi, zi), hash3(xi + 1, yi, zi), fx), lerp(hash3(xi, yi + 1, zi), hash3(xi + 1, yi + 1, zi), fx), fy);
  const b = lerp(lerp(hash3(xi, yi, zi + 1), hash3(xi + 1, yi, zi + 1), fx), lerp(hash3(xi, yi + 1, zi + 1), hash3(xi + 1, yi + 1, zi + 1), fx), fy);
  return lerp(a, b, fz);
}
const psi = (x, y, t) => noise3(x / 260, y / 260, t * 0.22) + 0.45 * noise3(x / 105 + 17, y / 105 + 5, t * 0.35);
function beatEnv(t) {
  let e = 0;
  for (const b of BEATS) {
    if (t >= b) e = Math.max(e, Math.exp(-(t - b) * 8));
    if (t >= b + 0.2) e = Math.max(e, 0.6 * Math.exp(-(t - b - 0.2) * 8));
  }
  return e;
}

// ---------- title: a hand-built stroke font, three stacked lines ----------
const GLYPH = (() => {
  const bowl = [];
  for (let k = 0; k <= 12; k++) { const a = -Math.PI / 2 + Math.PI * k / 12; bowl.push([0.36 + 0.25 * Math.cos(a), 0.25 + 0.25 * Math.sin(a)]); }
  const poly = (p) => p.slice(1).map((q, i) => [p[i][0], p[i][1], q[0], q[1]]);
  return {
    W: { w: 1.0, s: poly([[0, 0], [0.25, 1], [0.5, 0.15], [0.75, 1], [1, 0]]) },
    E: { w: 0.6, s: [[0, 0, 0, 1], [0, 0, 0.6, 0], [0, 0.5, 0.52, 0.5], [0, 1, 0.6, 1]] },
    A: { w: 0.75, s: [[0, 1, 0.375, 0], [0.375, 0, 0.75, 1], [0.14, 0.62, 0.61, 0.62]] },
    R: { w: 0.62, s: [[0, 0, 0, 1], [0, 0, 0.36, 0], ...poly(bowl), [0.36, 0.5, 0, 0.5], [0.3, 0.5, 0.62, 1]] },
    F: { w: 0.6, s: [[0, 0, 0, 1], [0, 0, 0.6, 0], [0, 0.5, 0.5, 0.5]] },
    Y: { w: 0.7, s: [[0, 0, 0.35, 0.52], [0.7, 0, 0.35, 0.52], [0.35, 0.52, 0.35, 1]] },
    O: { w: 0.76, s: poly(Array.from({ length: 29 }, (_, k) => [0.38 + 0.38 * Math.cos(TAU * k / 28), 0.5 + 0.5 * Math.sin(TAU * k / 28)])) },
    U: { w: 0.64, s: [[0, 0, 0, 0.68], ...poly(Array.from({ length: 13 }, (_, k) => [0.32 - 0.32 * Math.cos(Math.PI * k / 12), 0.68 + 0.32 * Math.sin(Math.PI * k / 12)])), [0.64, 0.68, 0.64, 0]] },
  };
})();
function strokeSegs(c) { // lines of words -> stroke segments [x0, y0, x1, y1, cumulative length, word index]
  const segs = []; let len = 0, wi = 0;
  c.lines.forEach((line, li) => {
    const words = line.split(' ');
    let total = (words.length - 1) * c.SPACE; for (const w of words) { total += (w.length - 1) * c.GAP; for (const ch of w) total += GLYPH[ch].w * c.CAP; }
    let x = (W - total) / 2; const y0 = c.Y0 + li * c.LINE;
    for (const w of words) {
      for (const ch of w) {
        for (const [a, b, e, d] of GLYPH[ch].s) {
          const sg = [x + a * c.CAP, y0 + b * c.CAP, x + e * c.CAP, y0 + d * c.CAP];
          len += Math.hypot(sg[2] - sg[0], sg[3] - sg[1]); segs.push([...sg, len, wi]);
        }
        x += GLYPH[ch].w * c.CAP + c.GAP;
      }
      x += c.SPACE - c.GAP; wi++;
    }
  });
  return { segs, len };
}
const TITLE = VAR === 'B' ? { lines: ['YOU ARE FREE'], CAP: 84, GAP: 22, SPACE: 70, LINE: 0, Y0: 980, TH: 5 } : { lines: ['YOU', 'ARE', 'FREE'], CAP: 230, GAP: 56, SPACE: 0, LINE: 320, Y0: 560, TH: 14 };
const TK = TITLE.CAP / 230, TE = VAR === 'B' ? 0.2 : 1; // scale of the title's depth, and of each light's energy in it
function titleTargets() {
  const { segs, len } = strokeSegs(TITLE), TH = TITLE.TH;
  return (onEdge) => { // onEdge: on the outline of the stroke (crisp faces, and the walls of the extrusion)
    const u = rnd() * len, sg = segs.find((q) => q[4] >= u), k = rnd();
    if (onEdge && rnd() < 0.85) {
      const dx = sg[2] - sg[0], dy = sg[3] - sg[1], l = Math.hypot(dx, dy), sgn = rnd() < 0.5 ? -TH : TH;
      return [lerp(sg[0], sg[2], k) - dy / l * sgn, lerp(sg[1], sg[3], k) + dx / l * sgn, sg[5]];
    }
    const r = TH * (onEdge ? 1 : Math.sqrt(rnd())), a = rnd() * TAU;
    return [lerp(sg[0], sg[2], k) + r * Math.cos(a), lerp(sg[1], sg[3], k) + r * Math.sin(a), sg[5]];
  };
}

// ---------- soundtrack ----------
function synthAudio(file) {
  const SR = 44100, n = Math.round(SR * DUR), HIT = HIT_R, M0 = T.free + HOLD, BAR = 3.75, STEP = BAR / 16, BEAT = BAR / 8;
  const dL = new Float32Array(n), dR = new Float32Array(n), wL = new Float32Array(n), wR = new Float32Array(n);
  const pan = (p) => [Math.cos((p + 1) * Math.PI / 4), Math.sin((p + 1) * Math.PI / 4)];
  function thump(t0, amp, f0, f1, decay, len = 0.9) {
    let ph = 0; const s0 = Math.floor(t0 * SR);
    for (let i = 0; i < len * SR && s0 + i < n; i++) {
      const tt = i / SR, f = f1 + (f0 - f1) * Math.exp(-tt * 20);
      ph += TAU * f / SR;
      const s = Math.sin(ph) * Math.exp(-tt * decay) * amp * Math.min(1, tt * 400);
      dL[s0 + i] += s; dR[s0 + i] += s;
    }
  }
  function pad(f, t0, t1, amp, p) {
    const [gl, gr] = pan(p), s0 = Math.floor(t0 * SR), s1 = Math.min(n, Math.floor((t1 + 1.6) * SR));
    for (let i = s0; i < s1; i++) {
      const t = i / SR, tt = t - t0;
      const env = Math.min(1, tt / 0.9) * (t > t1 ? Math.max(0, 1 - (t - t1) / 1.6) : 1);
      const s = (Math.sin(TAU * f * t) + Math.sin(TAU * f * 1.004 * t + 1) + Math.sin(TAU * f * 0.996 * t + 2)
        + 0.3 * Math.sin(TAU * f * 2 * t)) * amp * env;
      wL[i] += s * gl; wR[i] += s * gr;
    }
  }
  function pluck(f, t0, amp, p) {
    const [gl, gr] = pan(p), s0 = Math.floor(t0 * SR);
    for (let i = 0; i < 1.4 * SR && s0 + i < n; i++) {
      const tt = i / SR;
      const s = (Math.sin(TAU * f * tt) + 0.4 * Math.sin(TAU * 2 * f * tt) + 0.15 * Math.sin(TAU * 3 * f * tt))
        * Math.exp(-tt * 5) * Math.min(1, tt * 300) * amp;
      wL[s0 + i] += s * gl; wR[s0 + i] += s * gr;
    }
  }
  function lead(f, t0, dur, amp) {
    let ph = 0; const s0 = Math.floor(t0 * SR);
    for (let i = 0; i < (dur + 0.3) * SR && s0 + i < n; i++) {
      const tt = i / SR;
      ph += TAU * f * (1 + 0.004 * Math.sin(TAU * 5.5 * tt) * Math.min(1, tt / 0.3)) / SR;
      const env = Math.min(1, tt / 0.04) * Math.exp(-tt * 0.6) * (tt > dur ? Math.max(0, 1 - (tt - dur) / 0.3) : 1);
      const s = (Math.sin(ph) + 0.3 * Math.sin(2 * ph) + 0.1 * Math.sin(3 * ph)) * amp * env;
      wL[s0 + i] += s * 0.75; wR[s0 + i] += s * 0.65;
    }
  }
  function bass(f, t0, dur, amp) {
    const s0 = Math.floor(t0 * SR);
    for (let i = 0; i < (dur + 0.1) * SR && s0 + i < n; i++) {
      const tt = i / SR, env = Math.min(1, tt / 0.015) * Math.exp(-tt * 1.4) * (tt > dur ? Math.max(0, 1 - (tt - dur) / 0.1) : 1);
      const s = (Math.sin(TAU * f * tt) + 0.5 * Math.sin(TAU * 2 * f * tt) + 0.25 * Math.sin(TAU * 3 * f * tt)) * amp * env;
      dL[s0 + i] += s; dR[s0 + i] += s;
    }
  }
  function hat(t0, amp) {
    let hp = 0; const s0 = Math.floor(t0 * SR);
    for (let i = 0; i < 0.06 * SR && s0 + i < n; i++) {
      const w = rnd() * 2 - 1; hp += 0.4 * (w - hp);
      const s = (w - hp) * Math.exp(-i / SR * 70) * amp;
      dL[s0 + i] += s * 0.8; dR[s0 + i] += s;
    }
  }
  function riser(t0, t1, amp) {
    let lp = 0;
    for (let i = Math.floor(t0 * SR); i < t1 * SR; i++) {
      const u = (i / SR - t0) / (t1 - t0), a = 0.01 + 0.5 * u * u * u;
      lp += a * ((rnd() * 2 - 1) - lp);
      dL[i] += lp * u * u * amp; dR[i] += lp * u * u * amp;
    }
  }
  function impact(t0, amp) {
    thump(t0, 0.8 * amp, 70, 30, 3, 2.5);
    let hp = 0; const s0 = Math.floor(t0 * SR);
    for (let i = 0; i < 2 * SR && s0 + i < n; i++) {
      const tt = i / SR, w = rnd() * 2 - 1; hp += 0.25 * (w - hp);
      const s = (w - hp) * Math.exp(-tt * 3.5) * 0.22 * amp;
      dL[s0 + i] += s * (0.8 + 0.2 * rnd()); dR[s0 + i] += s * (0.8 + 0.2 * rnd());
    }
  }
  // drone
  for (let i = 0; i < n; i++) {
    const t = i / SR, env = Math.min(1, t / 3) * (t < HIT ? 1 : 0.5), l = Math.sin(TAU * 0.13 * t) * 1.5;
    dL[i] += 0.09 * env * (Math.sin(TAU * 73.42 * t) + 0.45 * Math.sin(TAU * 146.84 * t + l) + 0.2 * Math.sin(TAU * 220.3 * t));
    dR[i] += 0.09 * env * (Math.sin(TAU * 73.62 * t) + 0.45 * Math.sin(TAU * 147.1 * t - l) + 0.2 * Math.sin(TAU * 219.8 * t));
  }
  // the cage: heartbeat, riser, release
  for (const b of BEATS) { thump(b, 0.5, 58, 38, 16); thump(b + 0.2, 0.3, 52, 36, 18); }
  riser(6.5, T.implode, 0.6);
  for (let i = Math.floor((T.implode - 0.04) * SR); i < HIT * SR; i++) { // silence before the hit
    const g = Math.max(0, 1 - (i / SR - (T.implode - 0.04)) / 0.09) ** 2; dL[i] *= g; dR[i] *= g;
  }
  impact(HIT, 1.25);
  thump(HIT, 0.9, 120, 28, 1.5, 3.5); // sub drop
  for (let i = 0, s0 = Math.floor(HIT * SR); i < 0.05 * SR; i++) { // crack
    const c = (rnd() * 2 - 1) * Math.exp(-i / SR * 110) * 0.8; dL[s0 + i] += c; dR[s0 + i] += c;
  }
  for (let i = 0, s0 = Math.floor(HIT * SR); i < 4.8 * SR; i++) { // a thin ringing tone hanging over the slow motion
    const tt = i / SR, c = Math.sin(TAU * 3136 * tt) * 0.024 * Math.exp(-tt * 0.65) * Math.min(1, tt * 20); dL[s0 + i] += c; dR[s0 + i] += c * 0.9;
  }
  riser(HIT + 0.8, M0 + 1.1, 0.14); // a long, quiet swell under the single zoom
  riser(M0 + 1.1, M0 + 2.05, 0.3); thump(M0 + 2.05, 0.35, 80, 40, 9); // whoosh as time snaps back to speed
  riser(T.birdOut - 1.5 + HOLD, T.birdOut + 0.1 + HOLD, 0.32); thump(T.birdOut + 0.1 + HOLD, 0.75, 90, 30, 3.5, 1.8); // the bird rushing at the camera
  // harmony: D Bm G A | D Bm G A | G A | D
  const chords = [[146.83, 220, 293.66, 369.99], [123.47, 185, 246.94, 293.66], [98, 196, 246.94, 293.66], [110, 220, 277.18, 329.63]];
  const roots = [73.42, 61.74, 49.0, 55.0], seq = VAR === 'A' ? [0, 1, 2, 3, 0, 1, 2, 2, 3] : [0, 1, 2, 3, 0, 1, 2, 3, 2, 3], END = M0 + seq.length * BAR;
  const RSTOP = VAR === 'A' ? T.birdOut + 0.15 + HOLD : END, SOFT = VAR === 'A' ? 0.4 : 1; // ending A: the rhythm stops as the bird passes, and the resolve is quiet
  seq.forEach((c, k) => chords[c].forEach((f, j) => pad(f, M0 + k * BAR, M0 + (k + 1) * BAR, 0.038, (j - 1.5) * 0.4)));
  [73.42, 146.83, 220, 293.66, 369.99, 440].forEach((f, j) => pad(f, END, VAR === 'A' ? DUR - 0.3 : 56.5 + HOLD, 0.045, (j - 2.5) * 0.3));
  const pat = [0, 2, 1, 3, 2, 3, 1, 2];
  for (let s = 9; M0 + s * STEP < RSTOP; s++) {
    const t = M0 + s * STEP, c = chords[seq[Math.floor((t - M0) / BAR)]];
    pluck(c[pat[s % 8]] * (s % 4 === 3 ? 4 : 2), t, 0.09 * sstep(M0 + 2, M0 + 6, t), s % 2 ? 0.5 : -0.5);
  }
  // rhythm: sparse in the first pass, full from the second
  for (let t = M0 + 2 * BAR; t < M0 + 4 * BAR - 0.01; t += BAR / 2) thump(t, 0.26, 70, 42, 12);
  for (let t = M0 + 4 * BAR; t < RSTOP - 0.01; t += BAR / 4) thump(t, 0.3, 70, 42, 12);
  for (let t = M0 + 4 * BAR; t < RSTOP - 0.01; t += STEP * 2) hat(t + STEP, 0.05);
  // bass + melody from the second pass
  for (let k = 4; k < seq.length; k++) {
    const t0 = M0 + k * BAR, r = roots[seq[k]];
    [[0, 3], [3, 2], [5, 3]].forEach(([b, d]) => t0 + b * BEAT < RSTOP - 0.3 && bass(r * (b === 3 ? 2 : 1), t0 + b * BEAT, d * BEAT * 0.9, 0.17));
  }
  const melody = [
    [[369.99, 2], [440, 2], [587.33, 3], [440, 1]], [[493.88, 3], [440, 1], [369.99, 4]],
    [[392, 2], [493.88, 2], [587.33, 3], [493.88, 1]], [[554.37, 3], [493.88, 1], [440, 2], [329.63, 2]],
    [[493.88, 2], [587.33, 2], [783.99, 4]], [[440, 2], [554.37, 2], [659.25, 2], [880, 2]],
  ];
  melody.forEach((bar, k) => { let b = 0; for (const [f, d] of bar) { if (M0 + (4 + k) * BAR + b * BEAT < RSTOP - 0.3) lead(f, M0 + (4 + k) * BAR + b * BEAT, d * BEAT * 0.92, 0.085); b += d; } });
  // the resolve
  riser(END - 2, END, 0.3 * SOFT);
  impact(END, 0.75 * SOFT * SOFT);
  lead(587.33, END, 4, 0.07); lead(739.99, END, 4, 0.05);
  [587.33, 739.99, 880, 1174.66, 1479.98, 1760, 2349.32].forEach((f, k) => {
    pluck(f, END + k * STEP / 2, 0.08, k % 2 ? 0.6 : -0.6);
    pluck(f, END + BAR + k * STEP, 0.045, k % 2 ? -0.6 : 0.6);
  });
  // ping-pong delay on the musical bus, then master
  const dl = Math.round(STEP * 1.5 * SR), dl2 = Math.round(0.127 * SR);
  for (let i = dl; i < n; i++) { wL[i] += 0.42 * wR[i - dl]; wR[i] += 0.42 * wL[i - dl]; }
  for (let i = dl2; i < n; i++) { wL[i] += 0.22 * wR[i - dl2]; wR[i] += 0.22 * wL[i - dl2]; }
  let peak = 0;
  for (let i = 0; i < n; i++) {
    const fade = 1 - (VAR === 'A' ? sstep(DUR - 2.8, DUR - 0.1, i / SR) : sstep(56 + HOLD, 59.8 + HOLD, i / SR));
    dL[i] = Math.tanh((dL[i] + wL[i]) * 1.2) * fade; dR[i] = Math.tanh((dR[i] + wR[i]) * 1.2) * fade;
    peak = Math.max(peak, Math.abs(dL[i]), Math.abs(dR[i]));
  }
  const buf = Buffer.alloc(44 + n * 4), g = 0.92 / peak * 32767;
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28);
  buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) { buf.writeInt16LE(Math.round(dL[i] * g), 44 + i * 4); buf.writeInt16LE(Math.round(dR[i] * g), 46 + i * 4); }
  fs.writeFileSync(file, buf);
}

// ---------- choreography ----------
function flockCenters(t) {
  let wx = CX + 240 * Math.sin(t * 0.5), wy = 800 + 360 * Math.sin(t * 0.37 + 1);
  const s = sstep(T.split, T.split + 2, t) * (1 - sstep(T.merge - 0.5, T.merge + 1.5, t));
  const ox = s * 230 * Math.cos(t * 0.8), oy = s * 270 * Math.sin(t * 0.8);
  let ax = wx + ox, ay = wy + oy, bx = wx - ox, by = wy - oy;
  const dv = sstep(T.dive, T.dive + 2, t) * (1 - sstep(T.dive + 3, T.dive + 5, t)); // behind the hills and back
  ay = lerp(ay, 1790, dv); by = lerp(by, 1770, sstep(T.dive + 0.6, T.dive + 2.6, t) * (1 - sstep(T.dive + 3.4, T.dive + 5.4, t)));
  const m = sstep(T.merge, T.birdIn, t) * (1 - sstep(T.birdOut - 0.5, T.birdOut + 1.5, t)); // gather where the bird will form
  ax = lerp(ax, CX, m); ay = lerp(ay, 1000, m); bx = lerp(bx, CX, m); by = lerp(by, 1000, m);
  const u = sstep(T.birdOut - 0.5, T.birdOut + 1.5, t); // wait above the title
  const hx = CX + 250 * Math.sin(t * 0.7), hy = 300 + 90 * Math.sin(t * 1.1);
  return [lerp(ax, hx, u), lerp(ay, hy, u), lerp(bx, CX - 250 * Math.sin(t * 0.7), u), lerp(by, hy, u)];
}

// ---------- pacing: sim time runs slow right after the hit, then races to catch up ----------
const Z1 = 1.5, Z2 = 2.9; // seconds after the hit at which the camera pushes in
const PAUSE = 1.3; // seconds the collapsed light hangs, silent, before the hit
function simSpeed(tr, deficit, t) {
  if (t < T.free) { // the collapse slows to a standstill -- a held breath -- then snaps
    const p = tr - (T.implode + 0.2);
    if (p < 0) return 1;
    if (p < PAUSE) return lerp(1, 0.02, 1 - (1 - sstep(0, 0.35, p)) ** 2);
    return 2.6;
  }
  const a = tr - HIT_R, P = HOLD - PRE_DEF, SLOW = 0.06, owed = Math.max(0, deficit - HOLD); // HOLD seconds are never repaid
  if (a < 0.08) return 1;
  if (a > 2.3 + P && owed < 0.004) return 1 + owed * FPS;
  const down = 1 - (1 - sstep(0.08, 0.62, a)) ** 2;     // ease into slow motion: quick at first, a long soft tail
  const up = sstep(1.4 + P, 2.3 + P, a) ** 2;           // a slow wind-up, then the rush
  const rush = 1 + 1.25 * Math.tanh(owed * 1.4);        // catch-up speed melts back to 1 as the lost time is repaid
  return lerp(lerp(1, SLOW, down), rush, up);
}
let HIT_R = 0, PRE_DEF = 0; // the real time of the hit, and the time already spent pausing before it
{ let def = 0; for (let f = 0; ; f++) { const tr = f / FPS, t = tr - def; if (t >= T.free) { HIT_R = tr; PRE_DEF = def; break; } def = Math.max(0, def + (1 - simSpeed(tr, def, t)) / FPS); } }
function cageHalf(t) { // the cage starts as a point and grows a little with every heartbeat
  let h = 5, prev = 5;
  BEATS.forEach((b, k) => {
    const tgt = 5 + 145 * Math.pow((k + 1) / BEATS.length, 0.85), u = clamp01((t - b) / 0.34) - 1;
    h += (tgt - prev) * (1 + 2.4 * u * u * u + 1.4 * u * u); prev = tgt; // ease-out with a small overshoot
  });
  return h;
}
function camera(tr) { // [zoom, shakeX, shakeY] about the cage
  const a = tr - HIT_R;
  if (a < 0) return [1 + 0.05 * sstep(7, T.implode, tr) + (tr > T.implode ? 0.1 * ((tr - T.implode) / (HIT_R - T.implode)) ** 2 : 0), 0, 0];
  // the bird coming at the lens: a tremor that builds as it nears, peaks as it passes, then dies away
  const b = tr - (T.birdOut + 0.1 + HOLD), kb = b < 0 ? 40 * clamp01(1 + b / 0.12) : 40 * Math.exp(-b * 3.4);
  if (b > -0.12 && b < 2) return [1.004 + 0.1 * kb / 46, kb * (0.7 * Math.sin(b * 72) + 0.3 * Math.sin(b * 29)), kb * (0.7 * Math.cos(b * 57) + 0.3 * Math.sin(b * 35 + 1))];
  const k = 26 * Math.exp(-a * 6);
  // one unbroken move: the punch on the hit is where the zoom starts, and it only ever gains speed through the slow motion;
  // it lets go as time takes off again
  const P = HOLD - PRE_DEF, w = Math.pow(clamp01(a / (1.6 + P)), 1.8), zin = 1.32 * Math.exp(0.82 * w * (2 - w)); // gathers speed, then slows into its deepest point
  return [1 + (zin - 1) * (1 - sstep(1.6 + P, 3.3 + P, a)), k * Math.sin(a * 75), k * Math.cos(a * 58)];
}

// ---------- the bird: a rigged 3D figure (X along the span, Y toward the head, Z up) ----------
// Seen from behind and above (52 deg), so both the body length and the wing beat show.
const D2R = Math.PI / 180, FLAP = 0.8, BS = 0.9;
// the last act of the bird: a hushed glide, then it turns and rushes straight at the camera
const glideAt = (tt) => sstep(T.birdOut - 2.9, T.birdOut - 2.1, tt) * (1 - sstep(T.birdOut - 1.6, T.birdOut - 1.1, tt)) + sstep(T.birdOut + 2.5, T.birdOut + 3.3, tt) * (1 - sstep(T.rise - 0.5, T.rise + 0.3, tt));
const rushAt = (tt) => clamp01((tt - (T.birdOut - 1.5)) / 1.65);
const BODY = [[-105, 10], [-80, 17], [-40, 30], [5, 36], [35, 30], [62, 11], [80, 18], [95, 16], [105, 6], [125, 0]]; // tail base .. beak tip
function bodyW(Y) {
  for (let k = 1; k < BODY.length; k++) if (Y <= BODY[k][0]) return lerp(BODY[k - 1][1], BODY[k][1], sstep(BODY[k - 1][0], BODY[k][0], Y));
  return 0;
}
const PRI_LEN = [125, 140, 152, 162, 168, 166, 158, 144, 124];
function birdPose(tt) {
  const glide = glideAt(tt), p = (((tt * FLAP) % 1) + 1) % 1; let th, fold, down = 0;
  if (p < 0.4) { const q = 0.5 - 0.5 * Math.cos(Math.PI * p / 0.4); th = lerp(48, -30, q); down = Math.sin(Math.PI * p / 0.4); fold = -12 * down; }
  else { const q = 0.5 - 0.5 * Math.cos(Math.PI * (p - 0.4) / 0.6); th = lerp(-30, 48, q); fold = 55 * Math.sin(Math.PI * (p - 0.4) / 0.6); }
  th = lerp(th, 10 + 3 * Math.sin(tt * 2.5), glide); fold = lerp(fold, -5, glide); down *= 1 - glide;
  const fa = Math.max(0, fold) / 55;
  const dir = (el, sw) => [Math.cos(el * D2R) * Math.cos(sw * D2R), -Math.cos(el * D2R) * Math.sin(sw * D2R), Math.sin(el * D2R)];
  const add = (a, d, k) => [a[0] + d[0] * k, a[1] + d[1] * k, a[2] + d[2] * k];
  // humerus sweeps back, forearm forward, hand back again; the hand folds further back on the upstroke
  const d1 = dir(th * 0.85, 15 + 10 * fa), d2 = dir(th - 0.35 * fold, -20 - 5 * fa), d3 = dir(th - fold, 15 + 45 * fa);
  const S = [26, 28, 6], E = add(S, d1, 95), Wr = add(E, d2, 135);
  const P = { S, E, Wr, d1, d2, d3, sec: new Float32Array(120), pri: new Float32Array(90), tail: new Float32Array(90) };
  const feather = (arr, j, root, bone, a, len) => { // a blade trailing back from the bone, fanned outward by angle a
    let fx = bone[0] * Math.sin(a), fy = -Math.cos(a) + bone[1] * Math.sin(a), fz = bone[2] * Math.sin(a), n = Math.hypot(fx, fy, fz); fx /= n; fy /= n; fz /= n;
    const dt = bone[0] * fx + bone[1] * fy + bone[2] * fz; let lx = bone[0] - dt * fx, ly = bone[1] - dt * fy, lz = bone[2] - dt * fz; n = Math.hypot(lx, ly, lz) + 1e-6;
    arr.set([root[0], root[1], root[2], fx, fy, fz, lx / n, ly / n, lz / n, len], j * 10);
  };
  for (let j = 0; j < 12; j++) { // secondaries along the arm
    const s = (j + 0.5) / 12 * 230, inner = s < 95;
    feather(P.sec, j, inner ? add(S, d1, s) : add(E, d2, s - 95), inner ? d1 : d2, lerp(-8, 14, s / 230) * D2R, j < 2 ? 82 + 10 * j : lerp(104, 112, s / 230));
  }
  for (let j = 0; j < 9; j++) { // primaries: the splayed fingers of the hand
    const q = j / 8;
    feather(P.pri, j, add(Wr, d3, 60 * q), d3, lerp(22, 80, Math.pow(q, 0.9)) * (1 - 0.4 * fa) * D2R, PRI_LEN[j]);
  }
  const spread = 24 + 8 * down + 6 * glide;
  for (let j = 0; j < 9; j++) { // tail fan
    const a = (j - 4) / 4 * spread * D2R;
    P.tail.set([0, -98, 0, Math.sin(a), -Math.cos(a), -0.08, Math.cos(a), Math.sin(a), 0, 106 - 14 * Math.abs(j - 4) / 4], j * 10);
  }
  return P;
}

// ---------- picture ----------
async function main() {
  const ti = process.argv.indexOf('--test');
  const testTimes = ti > 0 ? process.argv[ti + 1].split(',').map(Number) : null;
  const outDir = ti > 0 ? process.argv[ti + 2] : __dirname;
  const testFrames = testTimes && new Set(testTimes.map((t) => Math.round(t * FPS)));
  const lastFrame = testTimes ? Math.max(...testFrames) : NF - 1;

  const sampleTitle = titleTargets();
  const F = () => new Float32Array(N);
  const px = F(), py = F(), vx = F(), vy = F(), tx = F(), ty = F(), tStart = F(), tLeave = F();
  const bri = F(), ka = F(), r1 = F(), r2 = F(), wr = F(), wg = F(), wb = F(), born = F();
  const tBirdIn = F(), tBirdOut = F(), bu = F(), box = F(), boy = F(), tz = F(), pz = F();
  const stay = new Uint8Array(N); // the lights that remain the bird to the end
  const bpart = new Uint8Array(N), bidx = new Uint8Array(N), blag = new Uint8Array(N), bside = new Int8Array(N);
  const warm = [[1.0, 0.58, 0.2], [1.0, 0.34, 0.3], [1.0, 0.85, 0.55]];
  for (let i = 0; i < N; i++) {
    px[i] = CX + (rnd() * 2 - 1) * 4; py[i] = CY + (rnd() * 2 - 1) * 4; pz[i] = rnd() * 2 - 1; stay[i] = 0;
    tz[i] = rnd() < 0.42 ? 0 : 0.04 + 0.96 * rnd(); // 42% on the front face, the rest along the extruded depth
    const [x, y, w] = sampleTitle(tz[i] > 0 || rnd() < 0.3); tx[i] = x; ty[i] = y;
    tStart[i] = T.words[w] + rnd() * 1.5; tLeave[i] = T.rise + (y - 560) / 870 * 1.6 + rnd() * 0.5;
    if (VAR === 'A') { tStart[i] = 1e9; tLeave[i] = 1e9; }
    born[i] = i < 12 ? 0 : 2 + rnd() * 4;
    tBirdIn[i] = T.birdIn + rnd() * 1.5; tBirdOut[i] = T.birdOut + 0.2 + rnd() * 0.3; // let go only once it has passed out of sight
    const q = rnd(), edge = () => (rnd() < 0.3 ? (rnd() < 0.5 ? -1 : 1) : rnd() - rnd()); // 30% on the outline, for crisp feather edges
    bside[i] = rnd() < 0.5 ? -1 : 1;
    if (q < 0.14) { // body, sampled by area from its profile
      let Y; do { Y = lerp(-105, 125, rnd()); } while (rnd() * 36 > bodyW(Y));
      bpart[i] = 0; bu[i] = Y; box[i] = rnd() * TAU; boy[i] = rnd() < 0.3 ? 1 : Math.sqrt(rnd());
    } else if (q < 0.22) { bpart[i] = 1; bidx[i] = Math.floor(rnd() * 9); bu[i] = rnd(); box[i] = edge(); } // tail feathers
    else if (q < 0.44) { bpart[i] = 2; bu[i] = rnd(); box[i] = rnd() * rnd(); boy[i] = rnd() - 0.5; blag[i] = Math.round(bu[i] * 6); } // coverts on the leading edge
    else if (q < 0.71) { bpart[i] = 3; bidx[i] = Math.floor(rnd() * 12); bu[i] = rnd(); box[i] = edge(); blag[i] = Math.round((bu[i] * 0.6 + (bidx[i] + 0.5) / 12 * 0.24) * 15); }
    else { bpart[i] = 4; bidx[i] = Math.floor(rnd() * 9); bu[i] = rnd(); box[i] = edge(); blag[i] = Math.round((bu[i] * 0.6 + 0.24 + 0.16 * bidx[i] / 8) * 15); }
    bri[i] = 0.5 + rnd(); ka[i] = 0.6 + rnd() * 0.7; r1[i] = rnd(); r2[i] = rnd() * 2 - 1;
    const c = warm[rnd() < 0.55 ? 0 : rnd() < 0.5 ? 1 : 2];
    wr[i] = c[0]; wg[i] = c[1]; wb[i] = c[2];
  }
  // scenery
  const stars = [];
  for (let i = 0; i < 950; i++) stars.push([Math.floor(rnd() * W), Math.floor(rnd() * 1640), 0.06 + 0.6 * rnd() ** 3, rnd() * TAU, 1 + rnd() * 3]);
  const hillFar = new Float32Array(W), hillNear = new Float32Array(W);
  for (let x = 0; x < W; x++) {
    hillFar[x] = 1660 - 120 * noise3(x / 260, 3.3, 0) - 38 * noise3(x / 80, 8.1, 0) - 8 * noise3(x / 20, 1.7, 0);
    hillNear[x] = 1810 - 105 * noise3(x / 340 + 40, 5.5, 0) - 28 * noise3(x / 70 + 9, 2.2, 0) - 6 * noise3(x / 14, 6.6, 0);
  }
  const vig = new Float32Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const u = (x - CX) / CX, v = (y - H / 2) / (H / 2);
    vig[y * W + x] = 1 - 0.3 * (u * u * 0.6 + v * v * 0.8);
  }
  const LUTN = 8192, LUTS = 1024, lut = new Float32Array(LUTN);
  for (let i = 0; i < LUTN; i++) lut[i] = Math.pow(1 - Math.exp(-(i / LUTS) * 1.6), 1 / 2.2) * 255;

  const trail = new Float32Array(W * H * 3), fb = new Float32Array(W * H * 3);
  const BW = W / 4, BH = H / 4;
  const bl = [0, 1, 2].map(() => new Float32Array(BW * BH)), tmp = new Float32Array(BW * BH);
  const frame = Buffer.alloc(W * H * 3);
  const bx0 = new Int32Array(W), bfx = new Float32Array(W);
  for (let x = 0; x < W; x++) { const u = Math.max(0, Math.min(BW - 1.001, (x + 0.5) / 4 - 0.5)); bx0[x] = u | 0; bfx[x] = u - bx0[x]; }

  function disc(buf, x, y, rad, r, g, b) { // a soft disc with a brighter rim, like an out-of-focus point of light
    if (rad < 1.4) { splat(buf, x, y, r * 2.5, g * 2.5, b * 2.5); return; }
    const xa = Math.max(0, Math.floor(x - rad - 1)), xb = Math.min(W - 1, Math.ceil(x + rad + 1)), ya = Math.max(0, Math.floor(y - rad - 1)), yb = Math.min(H - 1, Math.ceil(y + rad + 1));
    for (let yy = ya; yy <= yb; yy++) for (let xx = xa; xx <= xb; xx++) {
      const d = Math.hypot(xx - x, yy - y), a = clamp01(rad - d + 0.5) * (0.5 + 0.5 * d / rad);
      if (a > 0) { const o = (yy * W + xx) * 3; buf[o] += r * a; buf[o + 1] += g * a; buf[o + 2] += b * a; }
    }
  }
  const GN = 5200, GL0 = T.birdOut + 0.15, gdx = new Float32Array(GN), gdy = new Float32Array(GN), gs = new Float32Array(GN), gph = new Float32Array(GN), gf = new Float32Array(GN), gsz = new Float32Array(GN);
  for (let i = 0; i < GN; i++) {
    const a = rnd() * TAU, rr = 0.12 + 0.88 * Math.sqrt(rnd());
    gdx[i] = Math.cos(a) * rr; gdy[i] = Math.sin(a) * rr * 1.2; gs[i] = GL0 + 1.5 * Math.pow(rnd(), 1.5); gph[i] = rnd() * TAU; gf[i] = 9 + rnd() * 16; gsz[i] = rnd() * rnd();
  }
  function splat(buf, x, y, r, g, b) {
    if (x < 0 || y < 0 || x >= W - 1 || y >= H - 1) return;
    const xi = x | 0, yi = y | 0, fx = x - xi, fy = y - yi, o = (yi * W + xi) * 3, o2 = o + W * 3;
    const a = (1 - fx) * (1 - fy), bq = fx * (1 - fy), c = (1 - fx) * fy, d = fx * fy;
    buf[o] += r * a; buf[o + 1] += g * a; buf[o + 2] += b * a;
    buf[o + 3] += r * bq; buf[o + 4] += g * bq; buf[o + 5] += b * bq;
    buf[o2] += r * c; buf[o2 + 1] += g * c; buf[o2 + 2] += b * c;
    buf[o2 + 3] += r * d; buf[o2 + 4] += g * d; buf[o2 + 5] += b * d;
  }
  const frame2 = Buffer.alloc(W * H * 3);
  function punch(z, ox, oy) { // camera zoom + shake, resampling the finished frame
    frame.copy(frame2);
    for (let y = 0; y < H; y++) {
      const v = Math.min(H - 1.001, Math.max(0, (y - CY) / z + CY + oy)), y0 = v | 0, fy = v - y0;
      for (let x = 0; x < W; x++) {
        const u = Math.min(W - 1.001, Math.max(0, (x - CX) / z + CX + ox)), x0 = u | 0, fx = u - x0;
        const a = (y0 * W + x0) * 3, b = a + W * 3, o = (y * W + x) * 3;
        for (let c = 0; c < 3; c++) frame[o + c] = (frame2[a + c] * (1 - fx) + frame2[a + 3 + c] * fx) * (1 - fy) + (frame2[b + c] * (1 - fx) + frame2[b + 3 + c] * fx) * fy;
      }
    }
  }
  function boxBlur(a, r) {
    for (let pass = 0; pass < 2; pass++) {
      for (let y = 0; y < BH; y++) {
        let s = 0; const row = y * BW;
        for (let x = -r; x <= r; x++) s += a[row + Math.min(BW - 1, Math.max(0, x))];
        for (let x = 0; x < BW; x++) { tmp[row + x] = s / (2 * r + 1); s += a[row + Math.min(BW - 1, x + r + 1)] - a[row + Math.max(0, x - r)]; }
      }
      for (let x = 0; x < BW; x++) {
        let s = 0;
        for (let y = -r; y <= r; y++) s += tmp[Math.min(BH - 1, Math.max(0, y)) * BW + x];
        for (let y = 0; y < BH; y++) { a[y * BW + x] = s / (2 * r + 1); s += tmp[Math.min(BH - 1, y + r + 1) * BW + x] - tmp[Math.max(0, y - r) * BW + x]; }
      }
    }
  }

  // encoder
  const SUF = VAR === 'A' ? '-A' : VAR === '' ? '-big' : '', wav = path.join(outDir, `we-are-free-vertical${SUF}.wav`);
  let args;
  if (testTimes) args = ['-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', `${W}x${H}`, '-i', '-', path.join(outDir, 'still_%02d.png')];
  else {
    synthAudio(wav);
    args = ['-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', `${W}x${H}`, '-r', String(FPS), '-i', '-', '-i', wav,
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
      '-shortest', '-movflags', '+faststart', path.join(outDir, `we-are-free-vertical${SUF}.mp4`)];
  }
  const ff = spawn('ffmpeg', args, { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => ff.on('close', (c) => (c === 0 ? res() : rej(new Error('ffmpeg exit ' + c)))));

  let released = false, grainSeed = 12345, deficit = 0, farDone = false;
  const endTitle = strokeSegs({ lines: ['YOU ARE FREE'], CAP: 24, GAP: 13, SPACE: 36, LINE: 0, Y0: PY + 134 }).segs;
  for (let f = 0; f <= lastFrame; f++) {
    const tr = f / FPS, t = tr - deficit, speed = simSpeed(tr, deficit, t), dt = speed / FPS, be = beatEnv(t); // tr: real time, t: sim time
    deficit = Math.max(0, deficit + (1 - speed) / FPS);
    const beatHit = BEATS.some((b) => t >= b && t - dt < b) ? 1 : BEATS.some((b) => t >= b + 0.2 && t - dt < b + 0.2) ? 0.55 : 0;
    const justReleased = !released && t >= T.free; if (justReleased) released = true;
    const birdness = sstep(T.birdIn, T.birdIn + 1.5, t) * (1 - sstep(T.birdOut - 0.3, T.birdOut + 0.7, t));
    const decay = t < T.free ? 0.7 : lerp(0.8, 0.55, birdness), burstGain = 1 + 3 * Math.exp(-Math.max(0, t - T.free) * 3);
    const decayF = Math.pow(decay, speed);
    for (let i = 0; i < trail.length; i++) trail[i] *= decayF;

    // --- simulate + draw particles ---
    const [c1x, c1y, c2x, c2y] = flockCenters(t);
    const attract = sstep(T.free + 0.4, T.free + 3, t), rate = Math.min(1, (0.5 + 2.5 * sstep(T.free, T.free + 2, t)) * dt);
    const warmth = sstep(T.free, T.free + 3, t), solo = lerp(45, 1, sstep(2, 6, t));
    // the bird the flock becomes: a body and two flapping wings
    const glide = glideAt(t), rush = rushAt(t), rushE = rush * rush * (3 - 2 * rush);
    const ret = 0, retE = ret * ret * (3 - 2 * ret), away = sstep(T.rise - 0.2, T.rise + 7, t);
    const bob = 12 * (1 - glide) * Math.cos(TAU * (t * FLAP - 0.4));
    let bScale, bPitch, bRoll, bcx, bcy, persp = rushE;
    if (ret <= 0) { // drifts away, banks, then swells head-on and climbs over the camera, whole
      bScale = BS * (1 - 0.14 * glide * (1 - rush)) * Math.exp(2.2 * Math.pow(rush, 2.4));
      bPitch = lerp(52, 9, rushE) * D2R; bRoll = 0.4 * Math.sin(Math.PI * Math.min(1, rush * 1.25)) * (1 - rush);
      bcx = CX + 60 * Math.sin(t * 0.6);
      bcy = 1000 + 70 * Math.sin(t * 0.9) - 120 * sstep(T.birdIn + 2, T.birdOut, t) - bob + 90 * rushE - 2500 * clamp01((rush - 0.72) / 0.28) ** 2 - 6000 * clamp01((t - (T.birdOut + 0.15)) / 0.45);
    } else { // having looped over us, it comes back in from the top: turning, shrinking into the distance, settling above the words
      bScale = BS * Math.exp(lerp(0.95, -0.5, retE)) * (1 - 0.4 * away); persp = 0;
      bPitch = lerp(14, 52, retE) * D2R; bRoll = Math.PI * (1 - sstep(0.15, 0.9, ret));
      bcx = CX + 280 * Math.sin(Math.PI * retE) * (1 - retE) * 2 + 46 * Math.sin(t * 0.5) * retE;
      bcy = lerp(-700, 330, retE) + 20 * Math.sin(t * 0.8) * retE - bob * 0.6 - 900 * away;
    }
    const VS = Math.sin(bPitch), VC = Math.cos(bPitch), RC = Math.cos(bRoll), RS = Math.sin(bRoll);
    const bGain = Math.min(7, Math.pow(bScale / BS, 1.5)) * (1 + 1.5 * sstep(T.words[0], T.words[2] + 1.5, t));
    const poses = t > T.birdIn - 0.1 && t < T.birdOut + 0.8 ? Array.from({ length: 16 }, (_, j) => birdPose(t - j * 0.0072)) : null; // feathers lag by bucket
    const titleSway = 20 + 46 * Math.sin((t - T.words[0]) * 0.55 + 0.4), glintPos = lerp(-200, 2100, (t - 43.8) / 2.6); // a slow drift of the view, and one sweep of light
    // ending A: far off, the bird has come apart into a loose flock again; it recedes toward the sun until it is one point
    const justFar = VAR === 'A' && !farDone && t >= T.far; if (justFar) farDone = true;
    const fu = clamp01((t - T.far) / (T.point - T.far)), fue = fu * fu * (3 - 2 * fu), fs = 0.4 * Math.pow(1 - fu, 1.5) + 0.004;
    const farFx = lerp(CX - 120, PX, fue) + 40 * Math.sin(t * 0.6) * (1 - fu), farFy = lerp(640, PY, fue);
    const farE = 0.22 * sstep(T.far + 0.1, T.far + 1.8, t) * (1 - sstep(T.point - 0.5, T.point + 0.5, t)) * Math.min(1, fs * fs * 3.4 + 0.015);
    const f1x = CX + 200 * Math.sin(t * 0.9), f1y = 900 + 130 * Math.sin(t * 1.3), f2x = CX - 200 * Math.sin(t * 0.9 + 1), f2y = 900 + 130 * Math.cos(t * 1.1);
    // the cage as a cube in perspective, turning slowly; it squares up to the camera before the collapse
    const hb = cageHalf(t), hbGain = Math.max(0.1, Math.pow(hb / 150, 1.15)), CF = 1000, square = 1 - sstep(T.implode - 1.6, T.implode - 0.1, t);
    const yaw = (0.5 * Math.sin(t * 0.55 + 0.3) + 0.12) * square, pit = 0.2 * square, cYaw = Math.cos(yaw), sYaw = Math.sin(yaw), cPit = Math.cos(pit), sPit = Math.sin(pit);
    for (let i = 0; i < N; i++) {
      const ox = px[i], oy = py[i];
      let e, fade = 1, cg = 1, cb = 1, spread = 0, caged = false, far = false;
      if (t < T.free && t >= T.implode) { // collapsing to a point
        vx[i] += ((CX - ox) * 110 - vx[i] * 16) * dt; vy[i] += ((CY - oy) * 110 - vy[i] * 16) * dt;
        vx[i] -= (oy - CY) * 70 * dt; vy[i] += (ox - CX) * 70 * dt; // a swirl: the light spirals in instead of drawing straight diagonals
        px[i] += vx[i] * dt; py[i] += vy[i] * dt;
        e = 0.017; caged = true;
      } else if (t < T.free) { // caged
        vx[i] = (vx[i] + (rnd() - 0.5) * 1200 * dt) * 0.96; vy[i] = (vy[i] + (rnd() - 0.5) * 1200 * dt) * 0.96;
        if (beatHit) {
          const dx = ox - CX, dy = oy - CY, d = Math.hypot(dx, dy) + 1, k = (200 + rnd() * 520) * beatHit;
          vx[i] += dx / d * k; vy[i] += dy / d * k;
        }
        px[i] += vx[i] * dt; py[i] += vy[i] * dt;
        if (px[i] < CX - hb) { px[i] = CX - hb; vx[i] = Math.abs(vx[i]) * 0.7; } else if (px[i] > CX + hb) { px[i] = CX + hb; vx[i] = -Math.abs(vx[i]) * 0.7; }
        if (py[i] < CY - hb) { py[i] = CY - hb; vy[i] = Math.abs(vy[i]) * 0.7; } else if (py[i] > CY + hb) { py[i] = CY + hb; vy[i] = -Math.abs(vy[i]) * 0.7; }
        e = 0.03 * (1 + 2.2 * be) * clamp01((t - born[i]) / 0.6) * (i < 12 ? solo : 1) * hbGain; caged = true;
      } else if (t >= tLeave[i]) { // flying away
        const age = t - tLeave[i], up = Math.min(1, age * 1.5);
        const cvx = (psi(ox, oy + 1, t) - psi(ox, oy - 1, t)) * 16000, cvy = -(psi(ox + 1, oy, t) - psi(ox - 1, oy, t)) * 16000;
        vx[i] += (cvx + r2[i] * 60 - vx[i]) * 2 * dt; vy[i] += (cvy - (120 + r1[i] * 300) * up - vy[i]) * 2 * dt;
        px[i] += vx[i] * dt; py[i] += vy[i] * dt;
        fade = Math.max(0, 1 - age / 9); e = 0.42;
      } else if (t >= tStart[i]) { // becoming the words
        // solid letters: the back of each one shrinks toward a vanishing point and swings as the view drifts
        const z = tz[i], gx = CX + (tx[i] - CX) * (1 - 0.05 * z * TK) + titleSway * z * TK, gy = ty[i] + 58 * z * TK;
        // fastest as it leaves, slowing all the way down: it drifts in and comes to rest, never sucked in
        const wa = t - tStart[i], kq = 1 - Math.exp(-(0.4 + 2.0 * sstep(0, 0.45, wa)) * dt), dxw = gx - ox, dyw = gy - oy, far = clamp01(Math.hypot(dxw, dyw) / 420);
        px[i] = ox + dxw * kq + Math.sin(t * 2.1 + r1[i] * TAU) * 80 * far * dt; py[i] = oy + dyw * kq; vx[i] = 0; vy[i] = 0;
        if (z === 0) { const q = (tx[i] + ty[i] * 0.45 - glintPos) / 70; e = (0.5 + 0.06 * Math.sin(t * 5 + r1[i] * TAU)) * (1 + 1.8 * Math.exp(-q * q)) * 0.85 * TE; cg = 1.05; cb = 1.1; spread = 1.0; }
        else { e = 0.2 * (1 - 0.55 * z) * TE; cg = 0.5 - 0.28 * z; cb = 0.16 - 0.12 * z; spread = 1.0; }
      } else if (VAR === 'A' && t >= T.far) { // the far flock (simulated full size, drawn small and distant)
        if (justFar) { const a = rnd() * TAU, r = 260 * Math.sqrt(-Math.log(1 - rnd() * 0.98)); px[i] = CX + Math.cos(a) * r; py[i] = 900 + Math.sin(a) * r; vx[i] = (rnd() - 0.5) * 300; vy[i] = (rnd() - 0.5) * 300; continue; }
        const cvx = (psi(ox, oy + 1, t) - psi(ox, oy - 1, t)) * 32000, cvy = -(psi(ox + 1, oy, t) - psi(ox - 1, oy, t)) * 32000;
        const gx = i & 1 ? f1x : f2x, gy = i & 1 ? f1y : f2y, k = ka[i], rt = Math.min(1, 3 * dt);
        vx[i] += (cvx + (gx - ox) * k - vx[i]) * rt; vy[i] += (cvy + (gy - oy) * k - vy[i]) * rt;
        px[i] += vx[i] * dt; py[i] += vy[i] * dt; e = farE; far = true;
      } else if (t >= tBirdOut[i]) { // gone over the top with the bird: waiting above the frame, over its place in the words
        const gx = tx[i] + pz[i] * 90, gy = -270 + pz[i] * 110;
        vx[i] += ((gx - ox) * 20 - vx[i] * 8) * dt; vy[i] += ((gy - oy) * 20 - vy[i] * 8) * dt;
        px[i] += vx[i] * dt; py[i] += vy[i] * dt; e = 0.1;
      } else if (t >= tBirdIn[i]) { // the bird
        const P = poses[blag[i]], kd = bpart[i], sd = bside[i]; let X, Y, Z;
        if (kd === 0) { const w = bodyW(bu[i]) * boy[i]; X = w * Math.cos(box[i]); Y = bu[i]; Z = w * Math.sin(box[i]) * 0.8; e = 0.36; }
        else if (kd === 2) {
          const s = bu[i] * 290, b = s < 95 ? P.S : s < 230 ? P.E : P.Wr, dd = s < 95 ? P.d1 : s < 230 ? P.d2 : P.d3, q = s < 95 ? s : s < 230 ? s - 95 : s - 230;
          X = sd * (b[0] + dd[0] * q); Y = b[1] + dd[1] * q - box[i] * 30 * (1 - 0.5 * bu[i]); Z = b[2] + dd[2] * q + boy[i] * 4; e = 0.42;
        } else {
          const A = kd === 1 ? P.tail : kd === 3 ? P.sec : P.pri, o = bidx[i] * 10, l = bu[i], L = A[o + 9] * l;
          const hw = (kd === 1 ? 9 : 8.5) * Math.sqrt(4 * l * (1 - l)) * (0.55 + 0.45 * (1 - l)) * box[i];
          X = A[o] + A[o + 3] * L + A[o + 6] * hw; Y = A[o + 1] + A[o + 4] * L + A[o + 7] * hw; Z = A[o + 2] + A[o + 5] * L + A[o + 8] * hw;
          if (kd !== 1) X *= sd; e = 0.5;
        }
        const pf = bScale * (1 + persp * 0.0013 * (Y * VC - Z * VS)), sx = X * pf, sy = (Y * VS + Z * VC) * pf; // the head leads, so it looms larger
        const gx = bcx + sx * RC - sy * RS, gy = bcy - (sx * RS + sy * RC); e *= bGain;
        vx[i] += ((gx - ox) * 90 - vx[i] * 17) * dt; vy[i] += ((gy - oy) * 90 - vy[i] * 17) * dt;
        px[i] += vx[i] * dt; py[i] += vy[i] * dt;
      } else { // murmuration
        if (justReleased) {
          const a = rnd() * TAU, k = 240 + rnd() * rnd() * 1900; // a clean radial explosion from the point
          vx[i] = Math.cos(a) * k; vy[i] = Math.sin(a) * k;
        }
        const cvx = (psi(ox, oy + 1, t) - psi(ox, oy - 1, t)) * 32000, cvy = -(psi(ox + 1, oy, t) - psi(ox - 1, oy, t)) * 32000;
        const gx = i & 1 ? c1x : c2x, gy = i & 1 ? c1y : c2y, k = ka[i] * attract;
        vx[i] += (cvx + (gx - ox) * k - vx[i]) * rate; vy[i] += (cvy + (gy - oy) * k - vy[i]) * rate;
        px[i] += vx[i] * dt; py[i] += vy[i] * dt;
        e = 0.22 * burstGain;
      }
      e *= bri[i] * fade * speed / 3;
      if (e <= 0) continue;
      const r = lerp(0.55, wr[i], warmth) * e, g = lerp(0.75, wg[i], warmth) * e * cg, b = lerp(1.0, wb[i], warmth) * e * cb;
      if (spread) { // settled letters: each light covers three nearby spots, so the faces read as solid
        const a = (r1[i] - 0.5) * 2 * spread, c = (r2[i] - 0.5) * 2 * spread;
        splat(trail, px[i] + a, py[i] + c, r, g, b); splat(trail, px[i] - c, py[i] + a, r, g, b); splat(trail, px[i] - a - c, py[i] - c + a, r, g, b);
      } else {
        let x0 = ox, y0 = oy, x1 = px[i], y1 = py[i];
        if (far) { x0 = farFx + (ox - CX) * fs; y0 = farFy + (oy - 900) * fs; x1 = farFx + (x1 - CX) * fs; y1 = farFy + (y1 - 900) * fs; }
        if (caged) { // inside the cage the lights have depth: seen through the same slow turn as the bars
          const z = pz[i] * hb;
          let x = ox - CX, y = oy - CY, xr = x * cYaw + z * sYaw, z1 = -x * sYaw + z * cYaw, sc = CF / (CF + y * sPit + z1 * cPit + hb);
          x0 = CX + xr * sc; y0 = CY + (y * cPit - z1 * sPit) * sc;
          x = x1 - CX; y = y1 - CY; xr = x * cYaw + z * sYaw; z1 = -x * sYaw + z * cYaw; sc = CF / (CF + y * sPit + z1 * cPit + hb);
          x1 = CX + xr * sc; y1 = CY + (y * cPit - z1 * sPit) * sc;
        }
        for (let s = 1; s <= 3; s++) splat(trail, x0 + (x1 - x0) * s / 3, y0 + (y1 - y0) * s / 3, r, g, b);
      }
    }
    if (testFrames && !testFrames.has(f)) continue;

    // --- stars + cage into the per-frame layer ---
    fb.fill(0);
    const d = sstep(T.free, DAWN, t), starA = (1 - d) * (1 - d);
    for (const [sx, sy, sb, ph, sp] of stars) {
      if (sy > hillFar[sx]) continue;
      const v = sb * starA * (0.65 + 0.35 * Math.sin(t * sp + ph)), o = (sy * W + sx) * 3;
      fb[o] += v * 0.9; fb[o + 1] += v * 0.95; fb[o + 2] += v * 1.1;
    }
    const age = t - T.free;
    if (age <= 0) {
      const gone = age > 0 ? 1 - age / 0.9 : 1, flick = t > T.free - 1.5 && age < 0 ? 1 - 0.45 * rnd() * Math.min(1, speed) : 1; // the flicker stops with time
      const cb = 0.3 * gone * flick * (1 + 0.8 * be), shake = be * 4 * Math.sin(t * 90);
      const line = (x, y, w = 1) => { const c = cb * w; splat(fb, x, y, c * 0.6, c * 0.78, c); splat(fb, x + 1, y, c * 0.6, c * 0.78, c); };
      if (age <= 0) { // a wire cube: bars on the near and far faces, joined at the corners
        const P3 = (x, y, z) => { const xr = x * cYaw + z * sYaw, z1 = -x * sYaw + z * cYaw, sc = CF / (CF + y * sPit + z1 * cPit + hb); return [CX + shake + xr * sc, CY + (y * cPit - z1 * sPit) * sc]; };
        const seg = (a, b, w) => { const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1])) + 1; for (let q = 0; q <= n; q++) line(lerp(a[0], b[0], q / n), lerp(a[1], b[1], q / n), w); };
        for (const [z, w] of [[hb, 0.38], [-hb, 1]]) {
          for (let k = 0; k <= 8; k++) { const off = (k - 4) * hb / 4; seg(P3(off, -hb, z), P3(off, hb, z), w); }
          seg(P3(-hb, -hb, z), P3(hb, -hb, z), w * 1.6); seg(P3(-hb, hb, z), P3(hb, hb, z), w * 1.6);
        }
        for (const sx of [-1, 1]) for (const sy of [-1, 1]) seg(P3(sx * hb, sy * hb, -hb), P3(sx * hb, sy * hb, hb), 0.6);
      }
      if (t >= T.implode && age < 0) { // the gathered energy: a round core that keeps charging through the pause
        const c = sstep(T.implode, T.implode + 0.4, t), charge = clamp01((tr - T.implode) / (HIT_R - T.implode));
        const I = c * (0.45 + 1.0 * charge) * (1 + 0.07 * Math.sin(tr * 11)), a1 = 1 / (2 * (15 + 11 * charge) ** 2), a2 = 1 / (2 * (32 + 14 * charge) ** 2);
        for (let y = CY - 130; y <= CY + 130; y++) for (let x = CX - 130; x <= CX + 130; x++) {
          const r2 = (x - CX) * (x - CX) + (y - CY) * (y - CY); if (r2 >= 16900) continue;
          const v = I * (1.5 * Math.exp(-r2 * a1) + 0.26 * Math.exp(-r2 * a2)) * (1 - r2 / 16900) ** 2, o = (y * W + x) * 3; // fades to nothing at the edge, so no box shows
          fb[o] += v * 0.72; fb[o + 1] += v * 0.86; fb[o + 2] += v;
        }
      }
    }

    if (VAR === 'A' && t > T.point - 1.3) { // the last light: one point in open sky, the sun rising behind it, a small title under it
      const pa = sstep(T.point - 1.3, T.point, t) * (1 + 0.1 * Math.sin(t * 7)), sw = sstep(T.point + 1.6, T.point + 3.6, t), sr = 26 + 170 * sw, a3 = 1 / (2 * sr * sr);
      const RR = Math.ceil(Math.max(70, sr * 2.6));
      for (let y = Math.max(0, PY - RR); y <= PY + RR; y++) for (let x = Math.max(0, PX - RR); x <= Math.min(W - 1, PX + RR); x++) {
        const r2 = (x - PX) * (x - PX) + (y - PY) * (y - PY), v = pa * (2.4 * Math.exp(-r2 / 9) + 0.45 * Math.exp(-r2 / 260)), g = sw * 0.75 * Math.exp(-r2 * a3), o = (y * W + x) * 3;
        fb[o] += v + g; fb[o + 1] += v * 0.93 + g * 0.8; fb[o + 2] += v * 0.8 + g * 0.52;
      }
      const ta = 0.6 * sstep(T.point + 0.9, T.point + 2.1, t);
      if (ta > 0) for (const sg of endTitle) { const n = Math.ceil(Math.hypot(sg[2] - sg[0], sg[3] - sg[1])); for (let q = 0; q <= n; q++) { const x = lerp(sg[0], sg[2], q / n), y = lerp(sg[1], sg[3], q / n); splat(fb, x, y, ta, ta * 0.93, ta * 0.82); splat(fb, x + 0.6, y + 0.6, ta * 0.6, ta * 0.56, ta * 0.5); } }
    }
    // --- bloom ---
    for (let c = 0; c < 3; c++) {
      const a = bl[c];
      for (let y = 0; y < BH; y++) for (let x = 0; x < BW; x++) {
        let s = 0;
        for (let j = 0; j < 4; j++) { const o = ((y * 4 + j) * W + x * 4) * 3 + c; s += trail[o] + trail[o + 3] + trail[o + 6] + trail[o + 9]; }
        a[y * BW + x] = s / 16;
      }
      boxBlur(a, 6);
    }

    // --- compose ---
    const top = lerp3([0.004, 0.006, 0.018], [0.03, 0.055, 0.17], [0.05, 0.11, 0.32], d);
    const hor = lerp3([0.012, 0.015, 0.04], [0.5, 0.19, 0.16], [1.1, 0.62, 0.3], d);
    const sunY = 2010 - 440 * sstep(14, DAWN + 2, t), ga = 0.55 * d, gb = 1.8 * d * d;
    const ageR = tr - HIT_R, flash = ageR >= 0 ? 1.6 * Math.exp(-ageR * 3.5) : 0, white = ageR >= 0 && ageR < 1 / FPS ? 3 : 0, fxOn = flash > 0.002 || (age >= 0 && age < 1.4);
    const ringR = age * 1500, ringW = 14 + age * 70, ringA = 1.2 * Math.exp(-age * 3);
    const fadeIO = sstep(0, 1.6, t) * (1 - sstep(T.fade, FADE_END, t));
    const farC = [hor[0] * 0.1 + top[0] * 0.5, hor[1] * 0.1 + top[1] * 0.5, hor[2] * 0.1 + top[2] * 0.5];
    const nearC = [hor[0] * 0.015 + top[0] * 0.1, hor[1] * 0.015 + top[1] * 0.1, hor[2] * 0.015 + top[2] * 0.1];
    for (let y = 0; y < H; y++) {
      const fy = Math.pow(y / (H - 1), 3.2);
      const sr = lerp(top[0], hor[0], fy), sg = lerp(top[1], hor[1], fy), sb = lerp(top[2], hor[2], fy);
      const v = Math.max(0, Math.min(BH - 1.001, (y + 0.5) / 4 - 0.5)), y0 = v | 0, wy = v - y0, dy = y - sunY;
      const sunRow = ga > 0.001;
      for (let x = 0; x < W; x++) {
        const o = (y * W + x) * 3, dx = x - CX;
        let R, G, B, g1 = 0, g2 = 0, tk = 1, bk = 0.8;
        if (sunRow) { const r = Math.sqrt(dx * dx + dy * dy); g1 = ga * Math.exp(-r / 380); g2 = gb * Math.exp(-r / 100); }
        if (y > hillNear[x]) { R = nearC[0] + g1 * 0.03; G = nearC[1] + g1 * 0.015; B = nearC[2] + g1 * 0.01; tk = 0; bk = 0.2; } // the flock passes behind this ridge
        else if (y > hillFar[x]) { R = farC[0] + g1 * 0.16; G = farC[1] + g1 * 0.07; B = farC[2] + g1 * 0.04; }
        else { R = sr + g1 + g2 + fb[o]; G = sg + g1 * 0.5 + g2 * 0.8 + fb[o + 1]; B = sb + g1 * 0.22 + g2 * 0.5 + fb[o + 2]; }
        const i0 = y0 * BW + bx0[x], wx = bfx[x], w00 = (1 - wx) * (1 - wy), w10 = wx * (1 - wy), w01 = (1 - wx) * wy, w11 = wx * wy;
        R += tk * trail[o] + bk * (bl[0][i0] * w00 + bl[0][i0 + 1] * w10 + bl[0][i0 + BW] * w01 + bl[0][i0 + BW + 1] * w11);
        G += tk * trail[o + 1] + bk * (bl[1][i0] * w00 + bl[1][i0 + 1] * w10 + bl[1][i0 + BW] * w01 + bl[1][i0 + BW + 1] * w11);
        B += tk * trail[o + 2] + bk * (bl[2][i0] * w00 + bl[2][i0 + 1] * w10 + bl[2][i0 + BW] * w01 + bl[2][i0 + BW + 1] * w11);
        if (fxOn) {
          const rr = dx * dx + (y - CY) * (y - CY), q = (Math.sqrt(rr) - ringR) / ringW;
          const fl = flash * Math.exp(-rr / 260000) + ringA * Math.exp(-q * q) + white;
          R += fl * 0.7; G += fl * 0.85; B += fl;
        }
        grainSeed = (Math.imul(grainSeed, 1664525) + 1013904223) | 0;
        const m = vig[y * W + x] * fadeIO, gr = ((grainSeed >>> 16) / 65536 - 0.5) * 5;
        const ri = R * LUTS, gi = G * LUTS, bi = B * LUTS;
        frame[o] = Math.max(0, Math.min(255, lut[ri < LUTN ? ri | 0 : LUTN - 1] * m + gr));
        frame[o + 1] = Math.max(0, Math.min(255, lut[gi < LUTN ? gi | 0 : LUTN - 1] * m + gr));
        frame[o + 2] = Math.max(0, Math.min(255, lut[bi < LUTN ? bi | 0 : LUTN - 1] * m + gr));
      }
    }
    { const [z, sx, sy] = camera(tr); if (z > 1.002) punch(z, sx, sy); } // creep in, punch on the hit, pull back through the slow motion
    if (!ff.stdin.write(frame)) await new Promise((r) => ff.stdin.once('drain', r));
    if (!testTimes && f % 150 === 0) process.stdout.write(`frame ${f}/${NF}\n`);
  }
  ff.stdin.end();
  await done;
  if (!testTimes) fs.unlinkSync(wav);
  console.log('done');
}
main().catch((e) => { console.error(e); process.exit(1); });
