"""Generate the round-3 SyncLayer asset: the one-page brand sheet (dark and light).

    python -B assets/brand/src/build_round3.py --fonts <dir with IBM Plex .ttf>

Writes brand-sheet-{dark,light}.svg (1600x1131). All text is converted to paths. Colours
come from PALETTES in brandlib.py; the usage rules mirror docs/brand/visual-identity.md.
"""

import argparse
from pathlib import Path

from brandlib import BLOCKS, BLOCKS_16, PALETTES, RADIUS, block_rects, fmt, svg_doc, text
from build_round2 import bg, lockup
from fonts_util import load

OUT = Path(__file__).resolve().parent.parent

W, H, M, GAP = 1600, 1131, 64, 32
TAGLINE = "One layer. Many specialists."
TOKENS = ["bg", "surface", "surface-2", "text", "text-2", "text-3",
          "accent", "border", "ok", "warn", "error", "info"]

# label, rule (English copy; keep in step with the usage rules in visual-identity.md)
RULES = [
    ("Clear space", "Keep 1 u free on every side of the symbol."),
    ("Minimum size", "16 px. Use symbol-16 between 16 and 24 px."),
    ("Monochrome", "A one-ink version is required. The gaps hold the shape."),
    ("Flat", "No gradients, shadows or outlines."),
    ("Pattern", "Never repeat the symbol as a pattern."),
    ("Imagery", "Do not pair it with brains, robots, circuits or sparkles."),
    ("Accent", "Under 5 % of a composition; the symbol is the exception."),
]

# face key, size, sample, tag
SPECIMEN = [
    ("sans600", 32, "One layer. Many specialists.", "Plex Sans 600 · 32"),
    ("sans600", 24, "Nine specialist agents", "Plex Sans 600 · 24"),
    ("sans400", 20, "Orchestration rules and a guard hook", "Plex Sans 400 · 20"),
    ("sans400", 16, "One session orchestrates; agents never delegate.", "Plex Sans 400 · 16"),
    ("sans500", 14, "Role label", "Plex Sans 500 · 14"),
    ("mono500", 16, "auditor", "Plex Mono 500 · 16"),
    ("mono400", 14, "python -B -m unittest discover -s tests", "Plex Mono 400 · 14"),
]
SPEC_PITCH = [46, 40, 36, 32, 32, 34]   # baseline step after each row but the last


def panel(pal, ident, x, y, w, h):
    return (f'<rect id="{ident}" x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" '
            f'rx="6" fill="{pal["surface"]}" stroke="{pal["border"]}"/>')


def sheet(F, theme):
    pal = PALETTES[theme]
    els = [bg(pal, W, H)]

    def put(face, s, size, x, y, fill, **kw):
        el, w = text(F[face], s, size, x, y, fill, **kw)
        els.append(el)
        return w

    put("sans600", "SyncLayer brand sheet", 32, M, 96, pal["text"], ident="title", max_width=700)
    put("sans400", TAGLINE, 20, W - M, 94, pal["text-2"], anchor="end", ident="tagline",
        max_width=500)

    # ---- row 1: symbol, lockup, small sizes and monochrome
    py, ph = 140, 300
    pw = (W - 2 * M - 2 * GAP) // 3
    xs = [M + i * (pw + GAP) for i in range(3)]
    for ident, x in zip(("panel-symbol", "panel-lockup", "panel-small"), xs):
        els.append(panel(pal, ident, x, py, pw, ph))

    # symbol with its clear space: u = 18 px, guide at 1 u around the mark
    u = 18
    mx, my = xs[0] + (pw - 8 * u) / 2, py + 76
    put("mono400", "Symbol", 14, xs[0] + 24, py + 38, pal["text-3"], max_width=pw - 48)
    els.append(f'<rect id="clear-space" x="{fmt(mx - u + .5)}" y="{fmt(my - u + .5)}" '
               f'width="{10 * u - 1}" height="{10 * u - 1}" fill="none" stroke="{pal["border"]}" '
               f'stroke-dasharray="4 4"/>')
    els += block_rects(BLOCKS, RADIUS, ox=mx, oy=my, scale=u, palette=pal,
                        prefix="sym-")
    put("mono400", "Clear space 1 u · gap 0.4 u · radius 0.25 u", 14, xs[0] + pw / 2, py + ph - 24,
        pal["text-3"], anchor="middle", max_width=pw - 48)

    # horizontal lockup, scaled to the panel width
    _, lw1 = lockup(F, pal, 0, 0, 1)
    ls = (pw - 96) / lw1
    lk, _ = lockup(F, pal, xs[1] + (pw - lw1 * ls) / 2, py + ph / 2 - 4 * ls - 4, ls,
                  prefix="lk-")
    put("mono400", "Lockup", 14, xs[1] + 24, py + 38, pal["text-3"], max_width=pw - 48)
    els += lk
    put("mono400", "Plex Sans 600 · one weight", 14, xs[1] + pw / 2, py + ph - 24, pal["text-3"],
        anchor="middle", max_width=pw - 48)

    # 16, 24 and 32 px in one ink: symbol-16 geometry up to 24 px, original at 32 px
    put("mono400", "Small sizes and monochrome", 14, xs[2] + 24, py + 38, pal["text-3"],
        max_width=pw - 48)
    base = py + 176
    for cx, size, label in ((xs[2] + pw * 0.2, 16, "16 px"), (xs[2] + pw * 0.5, 24, "24 px"),
                            (xs[2] + pw * 0.8, 32, "32 px")):
        # whole pixels for the 16 px sample (24 px may sit on a half pixel at most)
        ox, oy = round(cx - size / 2), base - size
        pre = f"s{size}-"
        if size <= 24:
            els += block_rects(BLOCKS_16, 0, ox=ox, oy=oy, scale=size / 16, ink=pal["text"],
                               prefix=pre)
        else:
            els += block_rects(BLOCKS, RADIUS, ox=ox, oy=oy, scale=size / 8, ink=pal["text"],
                               prefix=pre)
        put("mono400", label, 14, cx, base + 32, pal["text-3"], anchor="middle", max_width=80)
    put("mono400", "One ink · the gaps keep the shape", 14, xs[2] + pw / 2, py + ph - 24,
        pal["text-3"], anchor="middle", max_width=pw - 48)

    # ---- row 2: palette
    qy, qh = py + ph + GAP, 192
    els.append(panel(pal, "panel-palette", M, qy, W - 2 * M, qh))
    put("mono400", f"Palette · {theme} · CSS custom properties --sl-<token>", 14, M + 24, qy + 38,
        pal["text-3"], max_width=W - 2 * M - 48)
    sw, sg = 111, 8
    for i, tok in enumerate(TOKENS):
        x = M + 24 + 2 + i * (sw + sg)
        els.append(f'<rect id="swatch-{tok}" x="{x + .5}" y="{qy + 62.5}" width="{sw - 1}" height="63" '
                   f'rx="4" fill="{pal[tok]}" stroke="{pal["border"]}"/>')
        put("mono400", tok, 14, x, qy + 150, pal["text"], max_width=sw)
        put("mono400", pal[tok], 14, x, qy + 172, pal["text-2"], max_width=sw)

    # ---- row 3: type specimen and usage rules
    ty = qy + qh + GAP
    th = H - 71 - ty
    tw = (W - 2 * M - GAP) // 2
    els.append(panel(pal, "panel-type", M, ty, tw, th))
    els.append(panel(pal, "panel-rules", M + tw + GAP, ty, tw, th))
    put("mono400", "Typography", 14, M + 24, ty + 38, pal["text-3"], max_width=tw - 48)
    y = ty + 90
    for i, (face, size, sample, tag) in enumerate(SPECIMEN):
        put(face, sample, size, M + 24, y, pal["text"], max_width=tw - 48 - 170)
        put("mono400", tag, 14, M + tw - 24, y, pal["text-3"], anchor="end", max_width=160)
        if i < len(SPEC_PITCH):
            y += SPEC_PITCH[i]
    rx0 = M + tw + GAP + 24
    put("mono400", "Usage rules", 14, rx0, ty + 38, pal["text-3"], max_width=tw - 48)
    y = ty + 90
    for label, rule in RULES:
        put("mono400", label, 14, rx0, y, pal["text-3"], max_width=116)
        put("sans400", rule, 16, rx0 + 132, y, pal["text"], max_width=tw - 48 - 132)
        y += 34

    put("mono400", "IBM Plex (OFL) · 8 u grid · 8 px spacing", 14, M, H - 40, pal["text-3"],
        max_width=600)

    palette_desc = ", ".join(f"{t} {pal[t]}" for t in TOKENS)
    rules_desc = " ".join(f"{label}: {rule}" for label, rule in RULES)
    desc = ("SyncLayer brand sheet, " + theme + " theme. Shows the four-block symbol with its clear "
            "space, the horizontal lockup, the symbol at 16, 24 and 32 px in one ink, the color "
            f"palette ({palette_desc}), a type specimen in IBM Plex Sans 600, 400 and 500 and "
            "IBM Plex Mono 500 and 400 at 32, 24, 20, 16 and 14 px, and the usage rules. "
            + rules_desc)
    return svg_doc(W, H, els, "SyncLayer brand sheet", desc=desc)


def build(fonts_dir):
    F = load(fonts_dir)
    files = {f"brand-sheet-{t}.svg": sheet(F, t) for t in ("dark", "light")}
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8", newline="\n")
    return list(files)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    for n in build(ap.parse_args().fonts):
        print(n)
