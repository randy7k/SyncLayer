"""Shared helpers for the SyncLayer brand asset generator.

Needs fontTools and uharfbuzz (not stdlib; the repository itself stays
stdlib-only, this generator is a build tool). Fonts: IBM Plex (OFL).
"""

from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# Palettes from docs/brand/visual-identity.md.
PALETTES = {
    "dark": {
        "bg": "#0B1118", "surface": "#151F2A", "surface-2": "#1C2936",
        "text": "#E6EDF3", "text-2": "#A9B6C2", "text-3": "#7D8B99",
        "accent": "#63D6C4", "border": "#2A3A4A",
        "ok": "#4ADE80", "warn": "#F5B84B", "error": "#FF7A7A", "info": "#7DB4FF",
    },
    "light": {
        "bg": "#F6F8FA", "surface": "#FFFFFF", "surface-2": "#EAEFF3",
        "text": "#0B1118", "text-2": "#44525F", "text-3": "#5B6874",
        "accent": "#0B7A6B", "border": "#D0D9E1",
        "ok": "#1A7F37", "warn": "#8A5A00", "error": "#C0362C", "info": "#1F5FBF",
    },
}

# Mark geometry on an 8 x 8 u grid (gap 0.4 u, radius 0.25 u).
RADIUS = 0.25
BLOCKS = [
    # id, x, y, w, h, colour token
    ("block-top-left", 0, 0, 5.1, 3, "text"),
    ("block-sync", 5.5, 0, 2.5, 3, "accent"),
    ("block-bottom-left", 0, 3.4, 2.5, 4.6, "text-3"),
    ("block-bottom-right", 2.9, 3.4, 5.1, 4.6, "text"),
]

# Small-size variant: 16 x 16 pixel grid, gap 1 px, radius 0 (see docs/brand).
BLOCKS_16 = [
    ("block-top-left", 0, 0, 10, 6, "text"),
    ("block-sync", 11, 0, 5, 6, "accent"),
    ("block-bottom-left", 0, 7, 5, 9, "text-3"),
    ("block-bottom-right", 6, 7, 10, 9, "text"),
]


def fmt(n):
    s = f"{n:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def block_rects(blocks, radius, ox=0.0, oy=0.0, scale=1.0, ink=None, palette=None, prefix=""):
    """SVG <rect> lines. ink: one colour for all (monochrome), else palette tokens.

    prefix goes before each id, to keep ids unique when a file holds several marks."""
    out = []
    for bid, x, y, w, h, token in blocks:
        fill = ink if ink else palette[token]
        r = f' rx="{fmt(radius * scale)}"' if radius else ""
        out.append(
            f'<rect id="{prefix}{bid}" x="{fmt(ox + x * scale)}" y="{fmt(oy + y * scale)}" '
            f'width="{fmt(w * scale)}" height="{fmt(h * scale)}"{r} fill="{fill}"/>'
        )
    return out


class Face:
    """A font file with shaping (kerning) and outline extraction."""

    def __init__(self, path):
        self.path = Path(path)
        self.tt = TTFont(str(self.path))
        self.gs = self.tt.getGlyphSet()
        self.upem = self.tt["head"].unitsPerEm
        os2 = self.tt["OS/2"]
        self.cap = os2.sCapHeight
        self.xh = os2.sxHeight
        blob = hb.Blob.from_file_path(str(self.path))
        self.hbfont = hb.Font(hb.Face(blob))

    def path_d(self, text, size, x=0.0, baseline=0.0):
        """Return (path 'd' string, advance width) for text at size, baseline at y."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hbfont, buf, {"kern": True, "liga": False})
        k = size / self.upem
        order = self.tt.getGlyphOrder()
        pen = SVGPathPen(self.gs, ntos=lambda v: fmt(v))
        cx = 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            name = order[info.codepoint]
            tp = TransformPen(
                pen, (k, 0, 0, -k, x + (cx + pos.x_offset) * k, baseline - pos.y_offset * k)
            )
            self.gs[name].draw(tp)
            cx += pos.x_advance
        return pen.getCommands(), cx * k


def svg_doc(width, height, body, title, vb=None, desc=None):
    vb = vb or f"0 0 {fmt(width)} {fmt(height)}"
    d = f"<desc>{desc}</desc>" if desc else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
        f'width="{fmt(width)}" height="{fmt(height)}" role="img" aria-labelledby="t">'
        f'<title id="t">{title}</title>{d}\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def text(face, s, size, x, y, fill, anchor="start", ident=None, max_width=None):
    """Text as a <path>. Returns (svg element, width). anchor: start | middle | end."""
    _, w = face.path_d(s, size)
    if max_width is not None and w > max_width:
        raise ValueError(f"text too wide ({w:.1f} > {max_width}): {s!r}")
    x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
    d, _ = face.path_d(s, size, x=x0, baseline=y)
    i = f' id="{ident}"' if ident else ""
    return f'<path{i} d="{d}" fill="{fill}"/>', w
