"""Export the favicon PNGs and favicon.ico from the brand SVGs with headless Edge.

    python -B assets/brand/src/export_favicons.py [--edge <msedge.exe>]

Writes into assets/brand/: favicon-16.png, favicon-32.png, favicon-48.png,
apple-touch-icon.png (180x180) and favicon.ico (PNG 16, 32 and 48 embedded).
Standard library only. Regenerate whenever symbol-16-dark.svg or symbol-dark.svg change.

The PNGs use the dark palette on an opaque bg tile: a transparent symbol is lost on
one of the two tab themes (dark ink on a dark tab, light ink on a light tab), while the
tile keeps the 1 px gaps visible on both. favicon.svg handles both themes by itself.
Design: 16 px is the bare symbol-16-dark.svg at 1x, so the mark fills the canvas and there
is no room for a margin. 32 px is symbol-16 at 1x (16 px) and 48 px is symbol-16 at 2x
(32 px), both centred with 8 px of bg margin per side, so every gap is a whole number of
pixels (1 and 2 px). Limitation: on a light tab the 16 px icon has no tile margin, and its
light blocks lose contrast against white; only 32 and 48 px read as a dark tile.

All captures render in a temporary folder and are copied to assets/brand/ only when every
one succeeded, so a failed run leaves the previous files untouched.
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from ico import build_ico
from export_social_png import find_edge

BRAND = Path(__file__).resolve().parent.parent
BG = "#0B1118"   # PALETTES["dark"]["bg"]

# name, canvas px, SVG, SVG px on the canvas (centred; clear space = (canvas - svg) / 2)
ICONS = [
    ("favicon-16.png", 16, "symbol-16-dark.svg", 16),
    ("favicon-32.png", 32, "symbol-16-dark.svg", 16),
    ("favicon-48.png", 48, "symbol-16-dark.svg", 32),
    # u = 16 px: the 8 u mark is 128 px and leaves 26 px (1.6 u) of clear space.
    ("apple-touch-icon.png", 180, "symbol-dark.svg", 128),
]
HTML = ('<body style="margin:0;background:{bg}"><div style="width:{canvas}px;height:{canvas}px;'
        'display:flex;align-items:center;justify-content:center">'
        '<img src="{src}" style="width:{size}px;height:{size}px;display:block"></div>')


TIMEOUT = 30   # seconds per capture


def render(edge, tmp, name, canvas, svg, size):
    page = Path(tmp) / (name + ".html")
    page.write_text(HTML.format(bg=BG, canvas=canvas, size=size, src=(BRAND / svg).as_uri()),
                    encoding="utf-8")
    shot = Path(tmp) / name
    for attempt in (1, 2):
        # a fresh profile per capture and per attempt: a shared one may hang Edge
        cmd = [edge, "--headless", "--disable-gpu", "--force-device-scale-factor=1",
               "--hide-scrollbars", "--default-background-color=00000000",
               f"--window-size={canvas},{canvas}", f"--screenshot={shot}",
               f"--user-data-dir={Path(tmp) / f'profile-{name}-{attempt}'}", page.as_uri()]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=TIMEOUT)
            break
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise SystemExit(f"msedge timed out twice for {name}")
    if not shot.exists():
        raise SystemExit(f"msedge produced no screenshot for {name}")
    return shot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge")
    args = ap.parse_args()
    edge = find_edge(args.edge)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        shots = [(name, render(edge, tmp, name, canvas, svg, size))
                 for name, canvas, svg, size in ICONS]
        ico = build_ico([shot.read_bytes() for name, shot in shots if name != "apple-touch-icon.png"])
        # ICO first: a failure after this point cannot leave new PNGs next to an old ICO.
        (BRAND / "favicon.ico").write_bytes(ico)
        print(BRAND / "favicon.ico")
        for name, shot in shots:
            shutil.copyfile(shot, BRAND / name)
            print(BRAND / name)


if __name__ == "__main__":
    main()
