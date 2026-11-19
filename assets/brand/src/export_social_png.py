"""Export assets/brand/social-preview.png (1280x640) from social-preview.svg with headless Edge.

    python -B assets/brand/src/export_social_png.py [--edge <msedge.exe>] [--out <file.png>]

Standard library only. Regenerate the PNG whenever social-preview.svg changes.
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

BRAND = Path(__file__).resolve().parent.parent
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
HTML = ('<body style="margin:0"><img src="{src}" '
        'style="width:1280px;height:640px;display:block">')


def find_edge(given):
    found = given or shutil.which("msedge") or next((p for p in EDGE_PATHS if Path(p).exists()), None)
    if not found:
        raise SystemExit("msedge not found; pass --edge <path to msedge.exe>")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge")
    ap.add_argument("--out", default=str(BRAND / "social-preview.png"))
    args = ap.parse_args()
    svg = BRAND / "social-preview.svg"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "social.html"
        page.write_text(HTML.format(src=svg.as_uri()), encoding="utf-8")
        shot = Path(tmp) / "social.png"
        subprocess.run(
            [find_edge(args.edge), "--headless", "--disable-gpu", "--force-device-scale-factor=1",
             "--hide-scrollbars", "--window-size=1280,640", f"--screenshot={shot}",
             f"--user-data-dir={Path(tmp) / 'profile'}", page.as_uri()],
            check=True, capture_output=True, timeout=120)
        if not shot.exists():
            raise SystemExit("msedge produced no screenshot")
        shutil.copyfile(shot, args.out)
    print(args.out)


if __name__ == "__main__":
    main()
