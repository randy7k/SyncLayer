"""Generate the SyncLayer symbol, wordmark and lockup SVGs.

    python -B assets/brand/src/build_brand.py --fonts <dir with IBMPlexSans-SemiBold.ttf>

Writes into assets/brand/. Wordmark text is converted to paths, so the SVGs
need no font. Requires fontTools and uharfbuzz.
"""

import argparse
from pathlib import Path

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


def text_ink(variant):
    pal, ink = VARIANTS[variant]
    return ink or PALETTES[pal]["text"]


def build(fonts_dir):
    sans = Face(Path(fonts_dir) / "IBMPlexSans-SemiBold.ttf")
    size = CAP_IN_MARK * sans.upem / sans.cap          # font size in u
    baseline = 4 + CAP_IN_MARK / 2
    written = []

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
        }
        # 16 px variant: pixel grid, 1 px gap, radius 0. Dark/light/mono only.
        files[f"symbol-16-{variant}.svg"] = svg_doc(
            16, 16, block_rects(BLOCKS_16, 0, ink=ink, palette=pal),
            "SyncLayer symbol", vb="0 0 16 16")

        for name, content in files.items():
            (OUT / name).write_text(content, encoding="utf-8", newline="\n")
            written.append(name)
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    a = ap.parse_args()
    for n in build(a.fonts):
        print(n)
