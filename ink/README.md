# Ink: code that writes itself

A 60 s film of ink in water. Halfway through, the ink gathers into the lines of the shader that
simulates it. One line is retyped (`SINK = 30.0` becomes `SINK = -30.0`), the solver is recompiled from that
text, and the same letters now come apart **upward**, because the ink has become lighter than water.

## Build (resumable; every shot is cached as PNG frames)
```
python render.py <shot>    # hook rt clash drops codeA codeB bloom -> cache/<shot>/####.png + stats.json
python music.py            # -> cache/music.wav (reads stats.json for sonification)
python assemble.py         # -> out/film.mp4, stills, music-excerpt.wav
```

## Structure (96 BPM, 4/4, bar = 2.5 s; every cut is on a bar line)
| t (s) | bars | shot | music |
|---|---|---|---|
| 0–5 | 1–2 | **Hook**: a crimson/orange pipette jet, already blooming on frame 1 (1.8 s pre-roll), backlit | Sub boom on frame 1, D drone, Dm9 pad, motif D-F-A-G-F-E on an FM bell |
| 5–10 | 3–4 | Rayleigh–Taylor: a layer of Prussian/cerulean ink fingers down into mushrooms, cool light | Dm9 to Bbmaj7. Data-driven pluck pulse starts, motif first half |
| 10–15 | 5–6 | Two jets (magenta, teal) collide and roll up | F to C, full motif |
| 15–20 | 7–8 | Sumi-black and gold drops. **A drop is released on every beat**, each makes a vortex ring | Gm7 to Asus4. A soft tom on every beat (the drops), motif in eighths |
| 20–27.5 | 9–11 | **The turn**: a cloud of inks converges into code (sim A **played backwards**) | Bb/A, Gm/A, Asus over an A pedal. Pads are time-reversed swells and the motif is played as reversed bells, with a 7.5 s riser |
| 27.5–32.5 | 12–13 | The code holds, readable (sim paused, slow 3.5 % push-in). On bar 13 the SINK value is retyped, one keystroke per 16th note (9 keys) | Bar 12 resolves to Dm9 and the motif plays alone and clear (quietest point, about −22 dB RMS). Bar 13 has 9 keystroke ticks on the same 16ths, and the motif returns with **one note changed** (F-E becomes Bb-A), mirroring the one-line edit |
| 32.5–45 | 14–18 | **Released**: the same letters now rise, curl and pile under the surface | Impact on the bar-14 downbeat, kick, eighth-note bass, shaker. The motif (edited version) doubles in octaves. Loudest section (−12 to −15 dB RMS) |
| 45–55 | 19–22 | Final bloom: crimson, cerulean and gold pour together and fill the frame | Bbmaj7, F, Gm7, Asus. The pulse thins out |
| 55–60 | 23–24 | End card over the darkened bloom | Dm9, the motif's first three notes rising to a high D, fade |

Sonification: the mean kinetic energy of the velocity field on screen (from each shot's `stats.json`, reversed for
the backwards shot, log-scaled, half-second smoothing) controls only the **probability** of each 16th-note pluck,
its amplitude and its filter brightness, plus the shaker density in the release. Pitch always comes from the bar's chord.

Measured: integrated −14.0 LUFS, true peak −2.2 dBTP **after AAC** (ffmpeg ebur128 on film.mp4), LRA 5.6 LU.
RMS per bar ranges from −24 dB (bar 13, the edit) to −11.8 dB (bar 14, the release). Nobody has listened to it.
These numbers are the only check.

## What is simulated, what is guided, what is stylised
**Simulated** (`shaders/ink.glsl`, GPU fragment shaders, moderngl/OpenGL 4.1): incompressible 2D stable fluids.
- Velocity grid 960×560. Ink grid 1920×1120 with 4 pigment layers; the frame shows the top 1920×804 at 1:1.
- MacCormack advection with an RK2 backtrace and clamping, for both velocity and ink.
- Vorticity confinement (`CURL`) and buoyancy (`SINK`: ink heavier than water).
- 60 Jacobi pressure iterations per step, closed tank, dt = 1/48 s (2 steps per frame).
- Ink has no explicit diffusion; it only spreads through numerical diffusion.

**Driven**: nozzles (gaussian "splats" of momentum and ink at fixed places, like a pipette) in hook, clash, drops
and bloom. RT starts from a perturbed ink layer. Initial water motion is smoothed random noise.

**The code text, honestly:**
- The letters are typeset with Menlo Bold into the ink field as the **initial condition**. One pigment per syntax
  class: keywords crimson, numbers gold, code indigo-black, comments and line numbers grey.
- The excerpt (file lines 23–36) is read from the exact source string the solver was compiled from. An assertion
  checks that the shown line equals the compiled line after the edit.
- **Formation (20–27.5 s) is a forward simulation of the text dissolving (`CURL 0.0, SINK 30.0`, exactly as shown),
  played backwards.** No force pulls ink toward the glyphs.
- Hold: the sim is paused, so this is a held frame. The push-in is a display-only camera move.
- The edit is guided: each keystroke re-typesets the ink in the paused tank. It is not fluid motion. After the last
  key, the shader is recompiled from the edited text and the release is a real forward run with `SINK = -30.0`.
- The shots before the code use the same shader with their `CURL`/`SINK` const lines rewritten by `shots.py`
  through the same `patch()` (hook 1.5/40, RT 0.8/45, clash 1.0/8, drops 1.0/35, bloom 1.0/30).

**Stylised display (look.glsl)**, which never moves ink:
- Beer–Lambert absorption of a warm backlight per pigment.
- A small scatter term.
- Bump shading from blurred density, self-shadow march, refraction of the background by the density gradient.
- Per-layer depth-of-field via mip levels, ACES tone map, vignette, hashed film grain (per-pixel PCG, no lattice),
  2.39:1 letterbox.
- End card: typeset with PIL over the darkened last shot (composited).

## Compute (measured)
- 2,940 solver steps, including pre-rolls, for the 1,440 frames.
- Final render of all 7 shots: 104 s of wall clock, including shading and PNG writes, on a shared M3 Pro.
- Previews and tests used roughly another 10 to 15 minutes of GPU.
- 1,085 non-blank lines of code in total (ink.py, 2 shaders, shots, text, render, music, assemble). ink.glsl is 101.

## Self-scores
- Scroll-stop: **7/10**. Frame 1 is a dense, backlit crimson bloom. Ink in a backlit tank reads as real at a glance.
- Craft: **6/10**. The idea lands: you read the code, one value changes, and the ink falls up. The 2D solver gives
  itself away in places.

## Known flaws
- It is 2D. Ink sheets do not thin by stretching as they would in 3D, so large regions stay evenly dense ("marbled
  paper" more than smoke), especially in the clash and the end of the bloom.
- In the backwards formation, the glyphs come from tiny bead-like droplets (thin strokes go unstable at once). The
  text becomes readable only in the last ~0.5 s before bar 12; earlier it reads as squiggles.
- The comment `// ink is heavier than water` stays unchanged after the edit makes it false (left on purpose, but
  it can read as a mistake).
- Ink piles against the tank lid/floor in later seconds of codeB and bloom (closed walls).
- Comments are rendered faint grey and are only just legible.
- Grain is 8-bit hashed noise; on very bright backgrounds banding is held off only by the dither.
- The music was verified only by measurement (loudness, true peak, per-bar RMS/centroid), never by ear.
  Bar 13 is spectrally bright (centroid ~7.8 kHz, from the ticks and a hiss riser), but quiet.

## v2 — native vertical 1080x1920 (showcase cut, 52.5 s)
Landscape v1 kept as `out/film-landscape-v1.mp4`; v1 scripts in `bak_v1/`.

- **Native vertical sim**: velocity 540x960, ink 1080x1920 (shown 1:1, no letterbox). Splat radii x0.58 keep the v1 pixel
  sizes; the clash jets now come from top and bottom; RT layer smoothing widened (fewer, larger fingers).
- **Drops shot fixed**: in v1 it was empty — the beat test (`abs(t - k*BEAT) < dt/2`) never fired once the 1.3 s pre-roll
  put the clock off the beat grid. Now a drop is released whenever a beat line falls inside a step, at varied depths
  of the tall tank (pre-roll 2.6 s so the shot opens busy).
- **Shader excerpt reformatted** so it reads at 39 px on a phone: the vorticity-confinement maths moved into `swirl()`
  and `total()` above the shown block; the comment moved onto its own line. Physics unchanged. ink.glsl is now 107
  non-blank lines (the end card counts them at assembly).
- **The edit**: SINK `30.0 -> -30.0` (16ths) and the comment `heavier -> lighter` (32nds, so it stays true), then the solver
  is recompiled from the edited text; an assertion checks every shown line is in the compiled source
  (`cache/codeB/edited_source.glsl`). Display-only push-in (x1.2) and highlight: everything outside the edited lines is
  washed toward the background (`hl`/`hlk` in look.glsl).
- **Cut (21 bars)**: cold open on the release (0-2.5 s, "This ink spells out / the code that moves it."), hook,
  RT, clash, drops, formation (reversed), hold + edit, release (trimmed to 10 s), bloom, end card ("107 lines of GLSL /
  move all of the ink in this video. / (the code-forming shot runs in reverse)"), last 0.5 s dissolves into frame 0.
  Captions: "simulated, not filmed", "watch it spell its own code", "flip one sign", "now ink is lighter than water".
- Polish: TPDF dither against banding; text density blurred 0.8 px (no crunchy glyph edges at the release).
- Music re-mapped to the 21-bar cut (keystroke ticks at the exact retype times). −14.0 LUFS, −2.2 dBFS peak (after AAC).
- Verified: 1,260 frames, no blank frame (min per-frame luminance std 13.7 at 35.7 s).
- Not fixed: still 2D ("marbled paper" in the bloom); the formation reads as squiggles until its last ~1 s; the release
  rises slowly in the taller tank.

## v3 (3 Nov): no spoiler in the opening
The v2 cold open showed the edited code rising: the payoff, before the story. v3 removes it.
- **Opening:** the crimson plume from frame 1, with "Watch this ink. / It's about to write something." then "simulated, not filmed".
- **The formation is longer:** 7.5 s (15.0-22.5 s) instead of 5 s, using all 180 frames of the backwards run, with no text over it.
- **The reveal is named when the code is readable:** "This is the code / that moves the ink." (22.7 s), then "Now flip one sign." (24.4 s).
  "now ink is lighter than water" moved to 28.0 s, when the rise is visible.
- **End card:** adds `github.com/beingcognitive/unreelcode` in monospace under the three lines.
- **Music:** re-mapped to the new cut (hook bars 1-2, build 3-6, a 3-bar formation over an A pedal with a 7.5 s riser);
  everything from the reveal (bar 10) on is unchanged. The cut is still 21 bars, 52.5 s, -14.0 LUFS.
- Scripts of v2 are kept locally in `bak_v2/`.
