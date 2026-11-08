"""Compose the frames: raw 3D frames + captions/readout/speed labels, then the end card and the loop dissolve;
encode with the mastered audio.  python render/compose.py RAW_DIR OUT_MP4 [--scale 0.5]"""
import os, sys, subprocess
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as T

raw_dir, out_mp4 = sys.argv[1], sys.argv[2]
scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1.0
fr_dir = os.environ.get("FRAMES_DIR", raw_dir.rstrip("/") + "_frames")
os.makedirs(fr_dir, exist_ok=True)
w, h = int(T.W * scale), int(T.H * scale)
n3d = int(T.T_CARD * T.FPS)


def full(f):
    im = Image.open(os.path.join(raw_dir, f"{f:05d}.png")).convert("RGB")
    im = im.resize((T.W, T.H), Image.LANCZOS) if im.size != (T.W, T.H) else im
    return im


frame0 = T.overlay(full(0), 0)
last = full(n3d - 1)
for f in range(T.N_TOTAL):
    img = T.overlay(full(f), f) if f < n3d else T.end_card(last, frame0, f)
    if scale != 1.0:
        img = img.resize((w, h), Image.LANCZOS)
    img.save(os.path.join(fr_dir, f"{f:05d}.png"))
audio = os.path.join(T.ROOT, os.environ.get("AUDIO", "out/audio/audio.wav"))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(T.FPS), "-i", os.path.join(fr_dir, "%05d.png"),
                "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", out_mp4],
               check=True)
print("wrote", out_mp4, T.N_TOTAL, "frames")
