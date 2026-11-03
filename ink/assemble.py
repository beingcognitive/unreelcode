"""assemble.py -- v2 (native 1080x1920 vertical): cut the cached shots on bar lines, add the captions and the end
card, dissolve the last frames into frame 0 (so the film loops), mux the score.

Timeline (96 BPM, bar = 2.5 s = 60 frames, 21 bars = 52.5 s). v3: no cold open (it spoiled the reveal);
the freed bar goes to the formation, which is now 7.5 s long.
  0.0- 5.0 hook (pipette plume)                     "Watch this ink. / It's about to write something."
                                                    then "simulated, not filmed"
  5.0- 7.5 Rayleigh-Taylor | 7.5-10.0 clash | 10.0-15.0 drops on the beat
 15.0-22.5 codeA PLAYED BACKWARDS (the formation), no text: let it happen
 22.5-27.5 codeB hold + the edit (push-in, highlight)  "This is the code / that moves the ink." then "Now flip one sign."
 27.5-37.5 codeB release                               "now ink is lighter than water"
 37.5-52.5 bloom; end card from 47.5 over the darkened bloom; last 0.5 s dissolves into frame 0
"""
import os, subprocess, glob, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
C, OUT = f"{HERE}/cache", f"{HERE}/out"
FF = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FPS = 24
W, H = 1080, 1920
# (shot, first source frame, frame count, reversed, film start in s)
SEGS = [("hook", 0, 120, False, 0.0), ("rt", 40, 60, False, 5.0), ("clash", 30, 60, False, 7.5),
        ("drops", 0, 120, False, 10.0), ("codeA", 0, 180, True, 15.0),
        ("codeB", 0, 120, False, 22.5), ("codeB", 120, 240, False, 27.5), ("bloom", 0, 360, False, 37.5)]
TOTAL = 1260
LOOP = 12                      # frames of dissolve back into frame 0
SERIF = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
SANS = "/System/Library/Fonts/Avenir Next.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
REPO = "github.com/beingcognitive/unreelcode"
INK = (34, 28, 24)
PAPER = (246, 240, 230)


def glsl_lines():
    return sum(1 for l in open(f"{HERE}/shaders/ink.glsl") if l.strip())


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lines_block(img, lines, y, a, dark_text=True, scrim=True):
    """centred lines [(text, font)] from y; a = opacity 0..1; a soft paper scrim behind for contrast"""
    if a <= 0:
        return img
    d = ImageDraw.Draw(img, "RGBA")
    ys, h = [], y
    for t, f in lines:
        bb = d.textbbox((0, 0), t, font=f)
        ys.append((t, f, h, bb[2] - bb[0], bb[3] - bb[1]))
        h += (bb[3] - bb[1]) + int(f.size * 0.42)
    if scrim:
        wmax = max(w for *_, w, _ in ys)
        x0, x1 = (W - wmax) / 2 - 34, (W + wmax) / 2 + 34
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(over)
        col = PAPER if dark_text else (12, 10, 10)
        od.rounded_rectangle((x0, y - 26, x1, h - int(lines[-1][1].size * 0.42) + 30), radius=26,
                             fill=(*col, int(205 * a)))
        img = Image.alpha_composite(img.convert("RGBA"), over)
        d = ImageDraw.Draw(img, "RGBA")
    for t, f, yy, w, _ in ys:
        col = INK if dark_text else PAPER
        d.text(((W - w) / 2, yy), t, font=f, fill=(*col, int(255 * a)))
    return img


CAPTIONS = [  # (film start s, end s, lines, y)
    (0.0, 2.6, [("Watch this ink.", 72), ("It's about to write something.", 54)], 300),
    (3.0, 4.8, [("simulated, not filmed", 60)], 1330),
    (22.7, 24.3, [("This is the code", 64), ("that moves the ink.", 64)], 300),
    (24.4, 26.4, [("Now flip one sign.", 64)], 300),
    (28.0, 30.0, [("now ink is lighter than water", 54)], 1360),
]


def overlay(img, t, n_lines):
    img = img.convert("RGBA")
    for t0, t1, lines, y in CAPTIONS:
        a = 1.0 if t0 == 0.0 and t < 2.0 else ease((t - t0) / 0.18) * (1 - ease((t - (t1 - 0.2)) / 0.2))
        if t0 <= t <= t1 and a > 0:
            fl = [(s, ImageFont.truetype(SERIF, sz)) for s, sz in lines]
            img = lines_block(img, fl, y, a)
    if t >= 47.5:                                               # end card: two lines over the darkened bloom
        k = ease((t - 47.5) / 0.8)
        a = np.asarray(img.convert("RGB")).astype(np.float32) * (1 - 0.80 * k)
        img = Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert("RGBA")
        fl = [(f"{n_lines} lines of GLSL", ImageFont.truetype(SERIF, 72)),
              ("move all of the ink in this video.", ImageFont.truetype(SERIF, 46)),
              ("(the code-forming shot runs in reverse)", ImageFont.truetype(SERIF, 36))]
        img = lines_block(img, fl, 760, ease((t - 48.0) / 0.6), dark_text=False, scrim=False)
        # v3: where the code lives (monospace, inside the right-hand safe zone)
        img = lines_block(img, [(REPO, ImageFont.truetype(MONO, 34))], 1075, ease((t - 48.6) / 0.6),
                          dark_text=False, scrim=False)
    return img.convert("RGB")


def frame_paths():
    out = []
    for name, a0, n, rev, t0 in SEGS:
        fs = sorted(glob.glob(f"{C}/{name}/*.png"))
        seg = fs[a0:a0 + n]
        assert len(seg) == n, (name, a0, n, len(seg))
        assert int(round(t0 * FPS)) == len(out), (name, t0, len(out))
        out += seg[::-1] if rev else seg
    assert len(out) == TOTAL
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    n_lines = glsl_lines()
    print("GLSL non-blank lines:", n_lines)
    frames = frame_paths()
    seq = f"{C}/seq"
    shutil.rmtree(seq, ignore_errors=True)
    os.makedirs(seq)
    first = None
    for i, p in enumerate(frames):
        t = i / FPS
        img = overlay(Image.open(p).convert("RGB"), t, n_lines)
        if i == 0:
            first = np.asarray(img).astype(np.float32)
        if i >= TOTAL - LOOP:                                   # dissolve into the opening frame: a seamless loop
            u = ease((i - (TOTAL - LOOP) + 1) / LOOP)
            img = Image.fromarray((np.asarray(img).astype(np.float32) * (1 - u) + first * u).astype(np.uint8))
        img.save(f"{seq}/{i:04d}.png", compress_level=1)
    subprocess.run([FF, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{seq}/%04d.png",
                    "-i", f"{C}/music.wav", "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "256k", "-t", f"{TOTAL / FPS}", "-movflags", "+faststart",
                    f"{OUT}/film.mp4"], check=True)


if __name__ == "__main__":
    main()
