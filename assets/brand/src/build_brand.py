"""Generate the SyncLayer symbol, wordmark and lockup SVGs (horizontal and stacked).

    python -B assets/brand/src/build_brand.py --fonts <dir with IBMPlexSans-SemiBold.ttf>

Writes into assets/brand/. Wordmark text is converted to paths, so the SVGs
need no font. Requires fontTools and uharfbuzz.
"""

import argparse
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen

from brandlib import (BLOCKS, BLOCKS_16, PALETTES, RADIUS, Face, block_rects,
                      fmt, svg_doc)

OUT = Path(__file__).resolve().parent.parent

# variant name -> (palette name, single ink or None for palette colours)
VARIANTS = {
    "dark": ("dark", None),
    "light": ("light", None),
    "mono": ("light", "#0B1118"),
    "mono-reverse": ("dark", "#FFFFFF"),
}

GAP_TO_TEXT = 2.4      # u, between mark and wordmark
CAP_IN_MARK = 3.6      # u, wordmark cap height inside the 8 u mark
STACK_CAP = 3.0        # u, wordmark cap height in the stacked lockup
STACK_GAP = 2.4        # u, between the mark and the top of the wordmark capitals


def text_ink(variant):
    pal, ink = VARIANTS[variant]
    return ink or PALETTES[pal]["text"]


def favicon():
    """favicon.svg: 16 px geometry, one file; light colours by default, dark colours
    under prefers-color-scheme: dark. Flat fills only. The fill attributes are the
    light fallback for renderers that ignore the style element."""
    light, dark = PALETTES["light"], PALETTES["dark"]
    rects = [
        f'<rect id="{bid}" class="c-{tok}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{light[tok]}"/>'
        for bid, x, y, w, h, tok in BLOCKS_16
    ]
    tokens = sorted({b[5] for b in BLOCKS_16})
    css = "".join(f".c-{t}{{fill:{dark[t]}}}" for t in tokens)
    style = f"<style>@media (prefers-color-scheme: dark){{{css}}}</style>"
    return svg_doc(16, 16, [style] + rects, "SyncLayer", vb="0 0 16 16")


def build(fonts_dir):
    sans = Face(Path(fonts_dir) / "IBMPlexSans-SemiBold.ttf")
    size = CAP_IN_MARK * sans.upem / sans.cap          # font size in u
    baseline = 4 + CAP_IN_MARK / 2
    written = []

    # Stacked lockup: mark on top, wordmark centred below. The viewBox is the ink
    # (mark plus wordmark with the descender of "y"); clear space lies outside it.
    stack_size = STACK_CAP * sans.upem / sans.cap
    _, stack_adv = sans.path_d("SyncLayer", stack_size)
    bp = BoundsPen(sans.gs)
    sans.gs["y"].draw(bp)
    descender = -bp.bounds[1] * stack_size / sans.upem
    stack_base = 8 + STACK_GAP + STACK_CAP
    stack_w = max(8.0, stack_adv)
    stack_h = stack_base + descender
    stack_d, _ = sans.path_d("SyncLayer", stack_size, x=(stack_w - stack_adv) / 2,
                             baseline=stack_base)

    for variant, (pal_name, ink) in VARIANTS.items():
        pal = PALETTES[pal_name]
        s = 8  # px per u in the width/height attributes

        mark = block_rects(BLOCKS, RADIUS, ink=ink, palette=pal)
        d, adv = sans.path_d("SyncLayer", size, x=8 + GAP_TO_TEXT, baseline=baseline)
        word_fill = text_ink(variant)

        files = {
            f"symbol-{variant}.svg": svg_doc(
                8 * s, 8 * s, mark, "SyncLayer symbol", vb="0 0 8 8"),
            f"wordmark-{variant}.svg": svg_doc(
                adv * s, 8 * s,
                [f'<path id="wordmark" d="{sans.path_d("SyncLayer", size, x=0, baseline=baseline)[0]}" fill="{word_fill}"/>'],
                "SyncLayer", vb=f"0 0 {fmt(adv)} 8"),
            f"lockup-horizontal-{variant}.svg": svg_doc(
                (8 + GAP_TO_TEXT + adv) * s, 8 * s,
                mark + [f'<path id="wordmark" d="{d}" fill="{word_fill}"/>'],
                "SyncLayer", vb=f"0 0 {fmt(8 + GAP_TO_TEXT + adv)} 8"),
            f"lockup-stacked-{variant}.svg": svg_doc(
                stack_w * s, stack_h * s,
                block_rects(BLOCKS, RADIUS, ox=(stack_w - 8) / 2, ink=ink, palette=pal)
                + [f'<path id="wordmark" d="{stack_d}" fill="{word_fill}"/>'],
                "SyncLayer", vb=f"0 0 {fmt(stack_w)} {fmt(stack_h)}"),
        }
        # 16 px variant: pixel grid, 1 px gap, radius 0. Dark, light, mono and mono-reverse.
        files[f"symbol-16-{variant}.svg"] = svg_doc(
            16, 16, block_rects(BLOCKS_16, 0, ink=ink, palette=pal),
            "SyncLayer symbol", vb="0 0 16 16")

        for name, content in files.items():
            (OUT / name).write_text(content, encoding="utf-8", newline="\n")
            written.append(name)

    (OUT / "favicon.svg").write_text(favicon(), encoding="utf-8", newline="\n")
    written.append("favicon.svg")
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    a = ap.parse_args()
    for n in build(a.fonts):
        print(n)
