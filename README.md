<p align="center"><img src="media/avatar-240.png" width="140" alt="( ^ ‿ ^ ) drawn in ink"></p>

<h1 align="center">unreel()</h1>

<p align="center"><b>Films written in code, not filmed.</b><br>
Made by Claude Code · directed by <a href="https://instagram.com/nolimit">nolimit</a> / <a href="https://x.com/racewithai">racewithai</a></p>

Every frame here is computed: no camera, no hand animation, music synthesised in code. Each folder holds the complete
code for one film, plus notes on what is simulated, what is guided and what is only display. Films are added one at a
time.

| | Film | What it is |
|---|---|---|
| <img src="media/4_ink.jpg" width="120"> | [**Ink**](ink/) | Ink in water gathers into the 107 lines of GLSL that simulate it. One sign is flipped, the shader is recompiled from that text, and the ink rises. |

**Watch:** the finished film (1080x1920, with sound) is attached to the
[latest release](https://github.com/beingcognitive/unreelcode/releases/latest).

## Honest notes
- Ink's code-forming shot is the forward simulation of the code dissolving, played in reverse. The retype of one
  line is a guided edit. Everything after it is a real forward simulation of the recompiled shader.
- The film's README lists what is simplified or stylised, including its known flaws.
- The music was checked by measurement only (loudness, peaks, timing).

## Running the code
Python 3.11 on macOS (Apple Silicon), with ffmpeg on PATH. The fluid solver runs on the GPU through moderngl
(OpenGL 4.1).
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ink && ../.venv/bin/python render.py hook     # see ink/README.md for the full build
```
Renders are cached in `cache/` and finished films are written to `out/` (both git-ignored).

`media/avatar_selfportrait.py` draws the account's avatar, `( ^ ‿ ^ )`, in wet ink with the Ink film's solver.

Unofficial project, not affiliated with Anthropic.

## License
[MIT](LICENSE): use, remix and share the code freely, with the copyright notice kept.
