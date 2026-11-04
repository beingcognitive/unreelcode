"""python run_plate.py sim            -> checkpoints at every shot start (cache/ck_*.pt)
   python run_plate.py shot NAME [--step N] [--still t]  -> cache/seg_NAME.mp4"""
import sys, os, time, subprocess, numpy as np, torch
import plate as P, render_plate as R, shots as S
N = 1000000
def ck(t): return f'cache/ck_{t:06.2f}.pt'
if sys.argv[1] == 'sim':
    s = P.Sand(N); T0 = time.time()
    for t in sorted({sh[1] for sh in S.SHOTS}):
        s.run(t); torch.save(s.state(), ck(t)); print('ck', t, round(time.time() - T0, 1), flush=True)
    sys.exit()
name = sys.argv[2]
sh = [x for x in S.SHOTS if x[0] == name][0]; _, t0, t1, light, fn = sh
s = P.Sand(N); s.load(torch.load(ck(t0), weights_only=False))
r = R.Renderer(N)
import overlay
if '--still' in sys.argv:
    ts = float(sys.argv[sys.argv.index('--still') + 1]); s.run(ts)
    from PIL import Image
    img = r.frame(s, S.cam_at(fn, t0, t1, ts), 0, light, R.heap_grid(s))
    Image.fromarray(overlay.apply(img, ts, name)).save(f'dev/still_{name}_{ts:.2f}.png'); sys.exit()
nf = int(round((t1 - t0) * R.FPS))
ff = subprocess.Popen([R.FF, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{R.W}x{R.H}',
                       '-r', str(R.FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', '12',
                       '-pix_fmt', 'yuv420p', f'cache/seg_{name}.mp4'], stdin=subprocess.PIPE)
T0 = time.time()
for i in range(nf):
    t = t0 + i / R.FPS
    s.run(t)
    img = r.frame(s, S.cam_at(fn, t0, t1, t), int(t * 30), light, R.heap_grid(s))
    ff.stdin.write(overlay.apply(img, t, name).tobytes())
    if i % 30 == 0: print(name, i, nf, round(time.time() - T0, 1), flush=True)
ff.stdin.close(); ff.wait(); print('done', name, round(time.time() - T0, 1))
