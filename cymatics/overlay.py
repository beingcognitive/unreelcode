"""2D overlays (v3.1, vertical 1080x1920): captions, the live-edited score (shot c1) and the end card (shot f1).
The code shown is the real text of score.py; the edits are the same string replacements timeline.py executes
for the audio and the sand.  Times passed in are simulation times; captions and the end card are placed in film
time (shots.film_t: the film opens at sim 22/30 s and bar 10 is cut)."""
import numpy as np, os, glob
from PIL import Image, ImageDraw, ImageFont
import timeline as T, shots as S

HERE = os.path.dirname(os.path.abspath(__file__))
SERIF = '/System/Library/Fonts/Supplemental/Georgia Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'
W, H = 1080, 1920
REPO = 'github.com/beingcognitive/unreelcode'
PAPER = (246, 240, 230)
SCRIM = (12, 10, 9)

def font(path, size, index=0): return ImageFont.truetype(path, size, index=index)
fcode = font(MONO, 56); fcodeb = font(MONO, 56, 1); flab = font(MONO, 30)   # 56 px: cap height 41 px
LINES = T.SRC.splitlines()
ROW = T.EDIT_LINE
NAMES = ['E5'] + T.EDITS

def ease(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)

def modes(k):
    return [(a, b) for a in range(16) for b in range(a + 1) if a * a + b * b == k]

def code_lines():
    """non-blank lines of the film's code (every .py here plus assemble.sh), counted from the files."""
    fs = sorted(glob.glob(os.path.join(HERE, '*.py'))) + [os.path.join(HERE, 'assemble.sh')]
    return sum(1 for f in fs for l in open(f) if l.strip())

# ---------------------------------------------------------------- captions (film time)
CAPTIONS = [  # (start, end, [(text, size)], y)
    (0.0, 2.6, [('Sound on.', 76), ('This sand is listening.', 58)], 300),
    (3.0, 4.9, [('simulated, not filmed', 68)], 1330),
    (22.35, 24.6, [('The same song,', 60), ('now in water.', 60)], 300),
    # v3.2: above the plate, in the code panel's place, before the code appears (never on the sand)
    (32.3, 33.85, [('This is the score.', 62), ('Watch me edit it.', 62)], 300),
]

def block(img, lines, y, a, scrim=True):
    """centred lines on a soft dark scrim; a = opacity"""
    if a <= 0: return img
    base = img.convert('RGBA'); ov = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    rows, h = [], y
    for s, sz in lines:
        f = font(SERIF, sz); bb = d.textbbox((0, 0), s, font=f)
        rows.append((s, f, h, bb[2] - bb[0], bb[1])); h += (bb[3] - bb[1]) + int(sz * 0.42)
    if scrim:
        wmax = max(r[3] for r in rows)
        d.rounded_rectangle(((W - wmax) / 2 - 36, y - 28, (W + wmax) / 2 + 36, h - int(lines[-1][1] * 0.42) + 32),
                            radius=28, fill=SCRIM + (int(185 * a),))
    for s, f, yy, w, top in rows:
        d.text(((W - w) / 2, yy - top), s, font=f, fill=PAPER + (int(255 * a),))
    return Image.alpha_composite(base, ov)

def captions(img, ft):
    for t0, t1, lines, y in CAPTIONS:
        if t0 <= ft <= t1:
            a = 1.0 if (t0 == 0.0 and ft < 2.2) else ease((ft - t0) / 0.2) * (1 - ease((ft - (t1 - 0.25)) / 0.25))
            img = block(img, lines, y, a)
    return img

# ---------------------------------------------------------------- the live score (shot c1)
DEL, GAP, TYPE, FLASH = 0.12, 0.08, 0.12, 0.45   # s per deleted char, pause, s per typed char, highlight flash
PANEL_IN = 36.95                                  # sim time the code panel appears (after the caption)

def edit_timing(i):
    """(start of deletion, start of typing, bar line) for edit i. The last character lands exactly on the bar line,
    the frame the new note sounds, the readout switches and the sand starts to re-form (v3.2: no value early)."""
    old, new = NAMES[i], NAMES[i + 1]
    tb = T.tbar(16 + i)
    tt = tb - TYPE * (len(new) - 1)
    return tt - GAP - DEL * len(old), tt, tb

def edit_state(t):
    """(token text, cursor shown, flash 0..1, editing) at sim time t. Each edit deletes the old token one character
    at a time and types the new one; the finished token is exactly what timeline.py executes."""
    w, cur, fl = NAMES[0], False, 0.0
    for i in range(len(NAMES) - 1):
        old, new = NAMES[i], NAMES[i + 1]
        td, tt, tb = edit_timing(i)
        if t < td - 0.3: return w, cur, fl, False
        if t < td: return old, True, 0.0, False
        if t < td + DEL * len(old): return old[:len(old) - (int((t - td) / DEL) + 1)], True, 0.0, True
        if t < tb:
            n = 0 if t < tt else min(len(new) - 1, int((t - tt) / TYPE) + 1)
            return new[:n], True, 0.0, True
        w, cur, fl = new, t < tb + 0.5, max(0.0, 1 - (t - tb) / FLASH)
    return w, cur, fl, False

def _idx(prefix):
    return next(i for i, l in enumerate(LINES) if l.startswith(prefix))

def shown_rows():
    """only what matters at feed size: the PLATE lines around the edited one (None marks skipped lines).
    Every shown line is a real, untruncated line of score.py; the file keeps its header."""
    r15 = next(i for i, l in enumerate(LINES) if ROW in l)
    return [_idx('PLATE = ['), None, r15 - 1, r15, r15 + 1]

def readout(t):
    """the sounding version: switches on the bar line, together with the note and the sand"""
    ver = 0
    for j in range(4):
        if t >= T.tbar(15 + j): ver = j
    k = [e for e in T.VERSIONS[ver]['PLATE'] if e[0] == 15][0][2]
    return ver, k

def code_panel(img, t):
    a = ease((t - PANEL_IN) / 0.3) * ease((45.4 - t) / 0.4)
    if a <= 0: return img
    base = img.convert('RGBA')
    sh = np.zeros((H, W, 4), np.uint8)                                    # darken the top so the code reads
    grad = np.clip((690 - np.arange(H)) / 90, 0, 1) * 0.92
    sh[..., 3] = (grad[:, None] * 255 * a).astype(np.uint8)
    ov = Image.alpha_composite(Image.new('RGBA', base.size, (0, 0, 0, 0)), Image.fromarray(sh))
    d = ImageDraw.Draw(ov)
    A = int(255 * a)
    x0, y, lh = 70, 232, 60
    word, cursor, flash, editing = edit_state(t)
    for li in shown_rows():
        if li is None:
            d.text((x0 + 4 * 33.7, y - 14), '...', font=fcode, fill=(110, 108, 102, A)); y += lh; continue
        s = LINES[li]
        assert len(s) <= 40, s
        if ROW in s:
            pre = s[:s.index('E5')]; post = s[s.index('E5') + 2:]
            d.rounded_rectangle((x0 - 14, y - 4, x0 + 860, y + lh - 2), radius=10, fill=(255, 196, 120, int(40 * a)))
            wx = x0 + d.textlength(pre, font=fcode); ww = d.textlength(word, font=fcode)
            if flash > 0:
                d.rounded_rectangle((wx - 6, y - 2, wx + max(ww, 20) + 6, y + lh - 4), radius=8,
                                    fill=(255, 190, 100, int(200 * flash * a)))
            d.text((x0, y), pre, font=fcode, fill=(240, 228, 205, A))
            if word: d.text((wx, y), word, font=fcodeb, fill=(255, 214, 150, A) if flash < 0.5 else (40, 24, 8, A))
            d.text((wx + ww, y), post, font=fcode, fill=(240, 228, 205, A))
            if cursor and (editing or int(t * 4) % 2 == 0):
                d.rectangle((wx + ww + 2, y + 4, wx + ww + 6, y + lh - 6), fill=(255, 226, 180, A))
        else:
            d.text((x0, y), s, font=fcode, fill=(214, 208, 196, A))
            if li == shown_rows()[0]:
                d.text((700, y + 16), 'score.py', font=flab, fill=(140, 136, 128, A))
        y += lh
    # the readout: switches on the bar line with the note and the sand, glows for half a second, and is dimmed while
    # the code is being edited (between the first deleted character and the bar line the two disagree)
    ver, k = readout(t)
    ms = ' + '.join(f'({p}, {q})' for p, q in modes(k))
    glow = max(0.0, 1 - (t - T.tbar(15 + ver)) / 0.5) if ver > 0 else 0.0
    col = tuple(int(c + (255 - c) * glow * 0.8) for c in (255, 205, 140))
    RA = int(A * (0.3 if editing else 1.0))
    y += 16
    d.text((x0, y), f'{NAMES[ver]} = k {k}  →  {T.freq(k):.1f} Hz', font=fcodeb, fill=col + (RA,)); y += lh
    d.text((x0, y), f'mode {ms}', font=fcodeb, fill=col + (RA,))
    return Image.alpha_composite(base, ov)

# ---------------------------------------------------------------- end card (film time)
END0 = S.film_t(55.6)                           # film time the end card starts
TEXT_OUT = S.DUR - 0.5 - 0.1                    # the text is gone before the loop dissolve starts
def end_card(img, ft):
    a = ease((ft - END0) / 0.8)
    if a <= 0: return img
    f = np.asarray(img.convert('RGB')).astype(np.float32) * (1 - 0.5 * a)       # v3.2: the plate stays at 50 %
    base = Image.fromarray(f.astype(np.uint8)).convert('RGBA')
    ov = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    out = 1 - ease((ft - (TEXT_OUT - 0.45)) / 0.45)
    a1 = ease((ft - END0 - 0.2) / 0.6) * out; a2 = ease((ft - END0 - 0.6) / 0.6) * out
    a3 = ease((ft - END0 - 1.0) / 0.6) * out
    ft1, ft2, fu = font(SERIF, 80), font(SERIF, 42), font(MONO, 40)
    # a subtle dark scrim behind the block, centred on the frame; every line fits inside the right safe zone by size
    d.rounded_rectangle((120, 600, 960, 1150), radius=36, fill=SCRIM + (int(140 * a1),))
    def ctr(y, s, fnt, col, aa):
        w = d.textlength(s, font=fnt)
        assert (W - w) / 2 + w <= 940, (s, w)
        d.text(((W - w) / 2, y), s, font=fnt, fill=col + (int(255 * aa),))
    ctr(640, 'You were seeing', ft1, PAPER, a1)
    ctr(745, 'the song.', ft1, PAPER, a1)
    ctr(905, STATS, ft2, (232, 220, 198), a2)
    ctr(1005, REPO_1, fu, (240, 232, 214), a3)       # the URL on two lines: Menlo 40 is too wide for one
    ctr(1057, REPO_2, fu, (240, 232, 214), a3)
    return Image.alpha_composite(base, ov)

STATS = f'1,000,000 grains · one {len(LINES)}-line score'     # N in run_plate.py; score.py's line count
REPO_1, REPO_2 = REPO[:REPO.rindex('/')], REPO[REPO.rindex('/'):]

def apply(img, t, shot):
    """img: HxWx3 uint8 at sim time t -> HxWx3 uint8"""
    ft = S.film_t(t)
    im = Image.fromarray(img)
    if shot == 'c1': im = code_panel(im, t)
    im = captions(im, ft)
    if shot == 'f1': im = end_card(im, ft)
    return np.array(im.convert('RGB'))
