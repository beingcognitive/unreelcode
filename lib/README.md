# lib: shared physics and graphics

Used by the films that throw things to music (the Mochi Choir now, the Fountain later).

- `phys.py`: exact ballistics at a stated scale. `set_scale(px_per_m)` sets gravity to Earth's 9.80665 m/s² in pixels;
  closed-form flight positions, first-contact search against circles (sampled at 0.25 ms, refined by bisection) and
  reflection with restitution.
- `gfx.py`: an instanced signed-distance-field renderer on moderngl (OpenGL 4.1): tubes, wood, chrome balls, glows,
  flat shapes and stars, with premultiplied MAX blending for trails.
- `score.py`: J. S. Bach, Prelude in C major, BWV 846, bars 1-19 (public domain), as (time, midi, bar) note events.

Films add this folder to their import path (`sys.path.insert(0, str(ROOT.parent / "lib"))`).
