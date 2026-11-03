"""text.py -- typeset the FORCES block of the shader that is actually compiled, as ink.

Returns a (H, W, 4) density array (GL row order: row 0 = bottom) with one pigment per
syntax class: 0 code, 1 keywords/types, 2 numbers, 3 comments + line numbers.
"""
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Menlo.ttc"
KW = {"const", "float", "void", "vec2", "vec4", "return"}
DENS = (2.2, 2.2, 2.2, 1.5)


def excerpt(source):
    """lines from '// forces on the water' to the closing brace of main(), with file line numbers"""
    lines = source.split("\n")
    a = next(i for i, l in enumerate(lines) if l.startswith("// forces on the water"))
    b = next(i for i in range(a, len(lines)) if lines[i] == "}")
    return [(i + 1, lines[i]) for i in range(a, b + 1)]


def classify(line):
    """per-character syntax class"""
    cls = [0] * len(line)
    c = line.find("//")
    if c >= 0:
        for i in range(c, len(line)):
            cls[i] = 3
        code = line[:c]
    else:
        code = line
    for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*|\d+\.\d*(?:e-?\d+)?|\d+", code):
        w = m.group(0)
        k = 1 if w in KW else 2 if w[0].isdigit() else 0
        for i in range(m.start(), m.end()):
            cls[i] = k
    return cls


class Layout:
    def __init__(self, W, H, view_h, size=39, lh=62, gutter=3, shift=-20):
        self.W, self.H, self.view_h = W, H, view_h
        self.font = ImageFont.truetype(FONT, size, index=1)  # Menlo Bold
        self.size, self.lh = size, lh
        self.cw = self.font.getlength("M")
        self.gutter, self.shift = gutter, shift

    def render(self, rows, char_alpha=None):
        """rows: [(lineno, text)]. char_alpha: optional {(row, col): alpha} overrides (for the edit)."""
        W, H = self.W, self.H
        n = len(rows)
        maxc = max(len(t) for _, t in rows) + self.gutter
        x0 = int((W - maxc * self.cw) / 2) + self.shift
        self.x0, self.maxc = x0, maxc
        top = 0  # visible window = top view_h rows of the tank (image row 0 = top)
        y0 = top + int((self.view_h - n * self.lh) / 2)
        self.y0 = y0
        layers = [Image.new("L", (W, H), 0) for _ in range(4)]
        draws = [ImageDraw.Draw(l) for l in layers]
        self.boxes = {}
        for r, (no, text) in enumerate(rows):
            y = y0 + r * self.lh
            draws[3].text((x0, y), f"{no:>2}", font=self.font, fill=150)
            cls = classify(text)
            for c, ch in enumerate(text):
                x = x0 + (c + self.gutter) * self.cw
                self.boxes[(r, c)] = (x, y)
                if ch == " ":
                    continue
                a = 1.0 if char_alpha is None else char_alpha.get((r, c), 1.0)
                if a <= 0:
                    continue
                draws[cls[c]].text((x, y), ch, font=self.font, fill=int(255 * a))
        from scipy.ndimage import gaussian_filter      # v2: soften the 1-px stroke edges (ink, not print)
        arr = np.stack([gaussian_filter(np.asarray(l, np.float32) / 255.0, 0.8) for l in layers], -1)
        arr *= np.array(DENS, np.float32)
        return arr[::-1].copy()  # GL rows

    def glyph(self, ch, cls, r, c, H=None):
        """density image of a single character at (row, col)"""
        img = Image.new("L", (self.W, self.H), 0)
        x, y = self.boxes[(r, c)]
        ImageDraw.Draw(img).text((x, y), ch, font=self.font, fill=255)
        out = np.zeros((self.H, self.W, 4), np.float32)
        out[..., cls] = np.asarray(img, np.float32)[::-1] / 255.0 * DENS[cls]
        return out
