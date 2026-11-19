"""Generate the round-2 SyncLayer assets: README banner, social preview,
agent catalog, orchestration star and slide template.

    python -B assets/brand/src/build_round2.py --fonts <dir with IBM Plex .ttf>

All text is converted to paths. Agent data (role, model, tools, writes) mirrors
agents/*.md and the catalog in rules/agentes.md; update both together.
"""

import argparse
import math
from pathlib import Path

from brandlib import (BLOCKS, PALETTES, RADIUS, block_rects, fmt, svg_doc, text)
from fonts_util import load

OUT = Path(__file__).resolve().parent.parent

# name, role (English copy), model, tools, writes (None = no Edit/Write), guarded Bash
# Classified by tools, not by guarantee: the guard is a heuristic, not a sandbox.
AGENTS = [
    ("oracle", "Maps an unfamiliar repo or area", "haiku", "Read, Grep, Glob", None, False),
    ("scout", "Checks official docs and libraries", "sonnet", "WebSearch, WebFetch, Read, Grep, Glob", None, False),
    ("atlas", "Plans and designs the change", "claude-fable-5-2", "Read, Grep, Glob, Write", "the plan file", False),
    ("forge", "Implements one unit of work", "sonnet", "Read, Edit, Write, Grep, Glob, Bash", "code and its tests", False),
    ("sentinel", "Runs and extends the tests", "sonnet", "Read, Grep, Glob, Bash, Edit, Write", "tests only", True),
    ("auditor", "Reviews the diff, independently", "opus", "Read, Grep, Glob, Bash", None, True),
    ("shield", "Reviews the diff for security", "opus", "Read, Grep, Glob, Bash", None, True),
    ("debugger", "Finds the root cause of a failure", "opus", "Read, Grep, Glob, Bash", None, True),
    ("scribe", "Keeps the project docs current", "sonnet", "Read, Grep, Glob, Edit, Write", "documentation only", False),
]

TAGLINE = "One layer. Many specialists."
SUBLINE = "Nine agents · orchestration rules · guard hook · Claude Code"


def mark(pal, x, y, scale):
    return block_rects(BLOCKS, RADIUS, ox=x, oy=y, scale=scale, palette=pal)


def lockup(F, pal, x, y, scale):
    """Horizontal lockup, top-left at (x, y); scale = px per u. Returns (elements, width)."""
    sans = F["sans600"]
    size = 3.6 * sans.upem / sans.cap
    baseline = 4 + 3.6 / 2
    els = mark(pal, x, y, scale)
    el, w = text(sans, "SyncLayer", size * scale, x + (8 + 2.4) * scale,
                 y + baseline * scale, pal["text"], ident="wordmark")
    return els + [el], (8 + 2.4) * scale + w


def bg(pal, w, h):
    return f'<rect id="background" width="{w}" height="{h}" fill="{pal["bg"]}"/>'


def status_color(pal, writes):
    return pal["warn"] if writes else pal["info"]


def status_label(writes, guarded):
    if writes:
        return "writes tests · guarded Bash" if guarded else f"writes: {writes}"
    return "no Edit/Write · guarded Bash" if guarded else "no Edit/Write"


def status_shape(pal, writes, x, y, d):
    """Status marker with top-left (x, y) and side d: circle = no Edit/Write,
    square = writes. Shape and colour both carry the class."""
    c = status_color(pal, writes)
    if writes:
        return f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{d}" height="{d}" rx="{d / 5}" fill="{c}"/>'
    return f'<circle cx="{fmt(x + d / 2)}" cy="{fmt(y + d / 2)}" r="{d / 2}" fill="{c}"/>'


def agent_desc(name, role, model, tools, writes, guarded):
    return f"{name}: {role}. Model {model}. Tools: {tools}. {status_label(writes, guarded)}."


HEURISTIC = "The guard is a heuristic, not a sandbox."


# ---------------------------------------------------------------- banner
def banner(F, theme):
    pal = PALETTES[theme]
    W, H = 1280, 320
    els = [bg(pal, W, H)]
    lk, _ = lockup(F, pal, 80, 56, 12)
    els += lk
    e, _ = text(F["sans400"], TAGLINE, 32, 80, 218, pal["text-2"], ident="tagline")
    els.append(e)
    e, _ = text(F["mono400"], SUBLINE, 16, 80, 262, pal["text-3"], ident="subline", max_width=W - 160)
    els.append(e)
    return svg_doc(W, H, els, "SyncLayer: " + TAGLINE,
                   desc="SyncLayer banner: the block symbol, the wordmark, the tagline and what the repository contains.")


# ---------------------------------------------------------------- social
def social(F, theme="dark"):
    pal = PALETTES[theme]
    W, H, SAFE = 1280, 640, 40
    els = [bg(pal, W, H)]
    lk, w = lockup(F, pal, 80, 150, 22)
    assert 80 + w <= W - SAFE, "lockup leaves the safe zone"
    els += lk
    e, tw = text(F["sans400"], TAGLINE, 44, 80, 420, pal["text-2"], ident="tagline")
    els.append(e)
    e, _ = text(F["mono400"], SUBLINE, 20, 80, 488, pal["text-3"], ident="subline",
                max_width=W - SAFE - 80)
    els.append(e)
    return svg_doc(W, H, els, "SyncLayer social preview",
                   desc="SyncLayer social preview: the block symbol, the wordmark and the tagline.")


# ---------------------------------------------------------------- catalog
def catalog(F, theme):
    pal = PALETTES[theme]
    cw, ch, gap, m = 440, 176, 24, 40
    W = m * 2 + 3 * cw + 2 * gap
    H = m * 2 + 3 * ch + 2 * gap
    els = [bg(pal, W, H)]
    for i, (name, role, model, tools, writes, guarded) in enumerate(AGENTS):
        x = m + (i % 3) * (cw + gap)
        y = m + (i // 3) * (ch + gap)
        els.append(f'<rect id="card-{name}" x="{x + .5}" y="{y + .5}" width="{cw - 1}" '
                   f'height="{ch - 1}" rx="6" fill="{pal["surface"]}" stroke="{pal["border"]}"/>')
        ix = x + 24
        inner = cw - 48
        e, _ = text(F["mono500"], name, 22, ix, y + 40, pal["text"], max_width=inner)
        els.append(e)
        els.append(status_shape(pal, writes, ix, y + 56, 10))
        e, _ = text(F["mono400"], status_label(writes, guarded), 14, ix + 18, y + 66, pal["text-2"],
                    max_width=inner - 18)
        els.append(e)
        e, _ = text(F["sans400"], role, 16, ix, y + 96, pal["text"], max_width=inner)
        els.append(e)
        e, lw = text(F["mono400"], "model", 14, ix, y + 126, pal["text-3"])
        els.append(e)
        e, _ = text(F["mono500"], model, 14, ix + lw + 14, y + 126, pal["text-2"], max_width=inner)
        els.append(e)
        e, lw = text(F["mono400"], "tools", 14, ix, y + 150, pal["text-3"])
        els.append(e)
        e, _ = text(F["mono400"], tools, 14, ix + lw + 14, y + 150, pal["text-2"],
                    max_width=inner - lw - 14)
        els.append(e)
    e, _ = text(F["mono400"], HEURISTIC, 14, W - m, H - 16, pal["text-3"], anchor="end")
    els.append(e)
    return svg_doc(W, H, els, "SyncLayer agent catalog: nine specialist agents",
                   desc=" ".join(agent_desc(*a) for a in AGENTS) + " " + HEURISTIC)


# ---------------------------------------------------------------- star
def star(F, theme):
    pal = PALETTES[theme]
    W, H = 1280, 720
    cx, cy, rx, ry = 640, 350, 450, 245
    nw, nh = 176, 44
    els = [bg(pal, W, H)]
    pts = []
    for i, a in enumerate(AGENTS):
        ang = math.radians(-90 + i * 360 / len(AGENTS))
        pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    lines = []
    for (px, py) in pts:
        lines.append(f'<line x1="{cx}" y1="{cy}" x2="{fmt(px)}" y2="{fmt(py)}" '
                     f'stroke="{pal["border"]}" stroke-width="1.5"/>')
    els.append('<g id="connections">' + "".join(lines) + "</g>")
    # main session: the single accent element
    sw, sh = 260, 84
    els.append(f'<rect id="main-session" x="{cx - sw / 2}" y="{cy - sh / 2}" width="{sw}" height="{sh}" '
               f'rx="6" fill="{pal["surface"]}" stroke="{pal["accent"]}" stroke-width="2"/>')
    e, _ = text(F["mono500"], "main session", 22, cx, cy - 2, pal["text"], anchor="middle", max_width=sw - 24)
    els.append(e)
    e, _ = text(F["mono400"], "orchestrates · asks the user", 14, cx, cy + 24, pal["text-2"],
                anchor="middle", max_width=sw - 16)
    els.append(e)
    for (name, role, model, tools, writes, guarded), (px, py) in zip(AGENTS, pts):
        x, y = px - nw / 2, py - nh / 2
        els.append(f'<rect id="agent-{name}" x="{fmt(x)}" y="{fmt(y)}" width="{nw}" height="{nh}" rx="6" '
                   f'fill="{pal["surface"]}" stroke="{pal["border"]}"/>')
        els.append(status_shape(pal, writes, x + 16, py - 5, 10))
        e, _ = text(F["mono500"], name, 18, x + 36, py + 6, pal["text"], max_width=nw - 48)
        els.append(e)
    # legend + caption
    ly = H - 52
    els.append(status_shape(pal, None, 60, ly - 10, 10))
    e, w1 = text(F["mono400"], "no Edit/Write", 14, 78, ly, pal["text-2"])
    els.append(e)
    lx = 78 + w1 + 32
    els.append(status_shape(pal, True, lx, ly - 10, 10))
    e, _ = text(F["mono400"], "writes (plan, code, tests or docs)", 14, lx + 18, ly, pal["text-2"])
    els.append(e)
    e, _ = text(F["mono400"], "Agents never delegate to each other.", 14, W - 60, ly, pal["text-3"],
                anchor="end")
    els.append(e)
    e, _ = text(F["mono400"], HEURISTIC, 14, W - 60, ly + 24, pal["text-3"], anchor="end")
    els.append(e)
    return svg_doc(W, H, els, "SyncLayer orchestration: one session, nine agents",
                   desc="The main session is connected to each of the nine agents. "
                        "There are no connections between agents. Circles mark agents without "
                        "Edit or Write, squares mark agents that write. " + HEURISTIC)


# ---------------------------------------------------------------- slides
SW, SH = 1920, 1080


def slide_title(F):
    pal = PALETTES["dark"]
    els = [bg(pal, SW, SH)]
    lk, _ = lockup(F, pal, 160, 120, 16)
    els += lk
    e, _ = text(F["sans600"], TAGLINE, 104, 160, 600, pal["text"], ident="title", max_width=SW - 320)
    els.append(e)
    e, _ = text(F["sans400"], "Presentation title or subtitle goes here", 40, 160, 690,
                pal["text-2"], ident="subtitle")
    els.append(e)
    e, _ = text(F["mono400"], "Speaker · Date", 24, 160, SH - 120, pal["text-3"], ident="footer")
    els.append(e)
    return svg_doc(SW, SH, els, "SyncLayer slide: title",
                   desc="Title slide template with the SyncLayer lockup, a title, a subtitle and a footer line.")


def slide_message(F):
    pal = PALETTES["dark"]
    els = [bg(pal, SW, SH)]
    els.append(f'<rect id="rule" x="160" y="330" width="12" height="260" fill="{pal["text-3"]}"/>')
    for i, line in enumerate(["One session orchestrates.", "Agents never delegate", "to each other."]):
        e, _ = text(F["sans600"], line, 88, 220, 410 + i * 110, pal["text"], max_width=SW - 380)
        els.append(e)
    e, _ = text(F["sans400"], "The guard is a heuristic, not a sandbox.", 36, 220, 770,
                pal["text-2"], ident="support")
    els.append(e)
    mk = mark(pal, SW - 160 - 56, SH - 120 - 56, 7)
    els += mk
    return svg_doc(SW, SH, els, "SyncLayer slide: message",
                   desc="Message slide: one session orchestrates, agents never delegate to each other, the guard is a heuristic.")


def slide_roster(F):
    pal = PALETTES["dark"]
    els = [bg(pal, SW, SH)]
    e, _ = text(F["sans600"], "Nine specialists", 72, 160, 200, pal["text"], ident="title")
    els.append(e)
    colw, gap, rowh, x0, y0 = 506, 41, 220, 160, 300
    for i, (name, role, model, tools, writes, guarded) in enumerate(AGENTS):
        x = x0 + (i % 3) * (colw + gap)
        y = y0 + (i // 3) * rowh
        els.append(f'<rect x="{x}" y="{y}" width="{colw}" height="{rowh - 30}" rx="8" '
                   f'fill="{pal["surface"]}" stroke="{pal["border"]}" stroke-width="1.5"/>')
        els.append(status_shape(pal, writes, x + 32, y + 38, 16))
        e, _ = text(F["mono500"], name, 36, x + 64, y + 58, pal["text"], max_width=colw - 96)
        els.append(e)
        e, _ = text(F["sans400"], role, 26, x + 32, y + 112, pal["text-2"], max_width=colw - 64)
        els.append(e)
        e, _ = text(F["mono400"], status_label(writes, guarded), 20, x + 32, y + 156, pal["text-3"],
                    max_width=colw - 64)
        els.append(e)
    e, _ = text(F["mono400"], HEURISTIC, 22, SW - 160, SH - 60, pal["text-3"], anchor="end")
    els.append(e)
    return svg_doc(SW, SH, els, "SyncLayer slide: the nine agents",
                   desc=" ".join(agent_desc(*a) for a in AGENTS) + " " + HEURISTIC)


def build(fonts_dir):
    F = load(fonts_dir)
    files = {"social-preview.svg": social(F, "dark"),
             "slide-1-title.svg": slide_title(F),
             "slide-2-message.svg": slide_message(F),
             "slide-3-roster.svg": slide_roster(F)}
    for t in ("dark", "light"):
        files[f"banner-{t}.svg"] = banner(F, t)
        files[f"agent-catalog-{t}.svg"] = catalog(F, t)
        files[f"architecture-star-{t}.svg"] = star(F, t)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8", newline="\n")
    return list(files)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    for n in build(ap.parse_args().fonts):
        print(n)
