"""Assemble the film: cached frames + overlays + the loop dissolve, then mux with the mastered audio.
    python assemble.py            -> out/film.mp4
    python assemble.py still T    -> cache/still_T.png (one frame with overlays, for checking)"""
import sys, subprocess, shutil, numpy as np
from pathlib import Path
from PIL import Image
import timeline as T, overlay as O

ROOT = Path(__file__).parent
FR = ROOT / "cache" / f"frames{T.SUFFIX}"
LOOP = 0.5                                     # v3: the end card dissolves into the pool lines of frame 0


OUTFILE = ROOT / "out" / (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "still" else "film.mp4")


def frame(i):
    ft = i / T.FPS
    img = O.apply(np.asarray(Image.open(FR / f"{i:04d}.png").convert("RGB")), ft)
    k0 = T.NF - int(LOOP * T.FPS)
    if i >= k0:
        a = T.ease((i - k0 + 1) / (T.NF - k0))
        f0 = O.apply(np.asarray(Image.open(FR / "0000.png").convert("RGB")), 0.0)
        img = (img * (1 - a) + f0 * a).round().astype(np.uint8)
    return img


def main():
    ff = shutil.which("ffmpeg")
    tmp = ROOT / "cache" / "video.mp4"
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
                          "-r", str(T.FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                          "-maxrate", "20M", "-bufsize", "40M", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for i in range(T.NF):
        p.stdin.write(frame(i).tobytes())
        if i % 120 == 0: print("frame", i, flush=True)
    p.stdin.close(); p.wait()
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(tmp), "-i", str(ROOT / "cache" / f"audio{T.SUFFIX}.wav"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest",
                    "-movflags", "+faststart", str(OUTFILE)], check=True)
    print("->", OUTFILE)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "still":
        t = float(sys.argv[2]); Image.fromarray(frame(int(round(t * T.FPS)))).save(ROOT / "cache" / f"still_{t:05.2f}.png")
    else:
        main()
