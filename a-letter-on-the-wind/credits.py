"""Replace the last five seconds with the title-free render and add the end credits (navy text with a soft white halo).
Usage: python credits.py <film.mp4> <tail_frames_dir> <out.mp4>
tail_frames_dir holds f00960.png ... f01079.png from `make_anime_coast_vertical.py -- --range 960 1080 <dir>`.
Needs Pillow, ffmpeg and the Avenir Next system font."""
import subprocess, sys, tempfile, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
src, tail, dst = sys.argv[1:4]
F = "/System/Library/Fonts/Avenir Next.ttc"
def font(size, style):
    for i in range(12):
        f = ImageFont.truetype(F, size, index=i)
        if f.getname()[1] == style: return f
lines = [("Made by Claude Code, Fable 5.2", font(42, "Demi Bold"), 66), ("Directed by being.cognitive", font(42, "Medium"), 86),
         ("github.com/beingcognitive/unreelcode", font(31, "Medium"), 0)]
text = Image.new("L", (1080, 1920), 0); d = ImageDraw.Draw(text); y = 1096
for s, f, step in lines:
    d.text(((1080 - d.textlength(s, font=f)) / 2, y), s, font=f, fill=255); y += step
halo = text.filter(ImageFilter.GaussianBlur(9)).point(lambda v: min(255, int(v * 2.6)))
im = Image.new("RGBA", (1080, 1920), (255, 255, 250, 0)); im.putalpha(halo.point(lambda v: int(v * 0.85)))
im = Image.alpha_composite(im, Image.merge("RGBA", (*Image.new("RGB", (1080, 1920), (16, 40, 104)).split(), text)))
png = os.path.join(tempfile.mkdtemp(), "credits.png"); im.save(png)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-framerate", "24", "-start_number", "960", "-i", os.path.join(tail, "f%05d.png"),
                "-loop", "1", "-t", "45", "-i", png, "-filter_complex",
                "[0:v]trim=end_frame=960,setpts=PTS-STARTPTS[a];[1:v]format=yuv420p,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1[v];"
                "[2]format=rgba,fade=t=in:st=40.4:d=1.1:alpha=1,fade=t=out:st=43.4:d=0.9:alpha=1[c];[v][c]overlay=shortest=1,format=yuv420p[o]",
                "-map", "[o]", "-map", "0:a", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-r", "24", "-c:a", "copy", "-movflags", "+faststart", dst], check=True)
