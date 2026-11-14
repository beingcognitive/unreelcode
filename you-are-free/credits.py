"""Add the end credits to the film: three lines over the empty dawn sky, 56.5 s to 63 s. The film itself is untouched.
Usage: python credits.py we-are-free-vertical.mp4 you-are-free.mp4      (Pillow, ffmpeg, the Avenir Next system font)"""
import subprocess, sys, tempfile, os
from PIL import Image, ImageDraw, ImageFont
src, dst = sys.argv[1], sys.argv[2]
F = "/System/Library/Fonts/Avenir Next.ttc"
def font(size, style):
    for i in range(12):
        f = ImageFont.truetype(F, size, index=i)
        if f.getname()[1] == style: return f
im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)); d = ImageDraw.Draw(im); y = 862
for text, f, alpha, step in [("Made by Claude Code, Fable 5.2", font(40, "Medium"), 245, 64),
                             ("Directed by being.cognitive", font(40, "Regular"), 225, 84),
                             ("github.com/beingcognitive/unreelcode", font(30, "Regular"), 190, 0)]:
    d.text(((1080 - d.textlength(text, font=f)) / 2, y), text, font=f, fill=(255, 244, 232, alpha)); y += step
png = os.path.join(tempfile.mkdtemp(), "credits.png"); im.save(png)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-loop", "1", "-t", "64", "-i", png, "-filter_complex",
                "[1]format=rgba,fade=t=in:st=56.5:d=1.2:alpha=1,fade=t=out:st=61.6:d=1.4:alpha=1[c];[0][c]overlay=shortest=1,format=yuv420p",
                "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-c:a", "copy", "-movflags", "+faststart", dst], check=True)
