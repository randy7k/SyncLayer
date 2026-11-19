"""Load the IBM Plex faces used by the brand assets."""

from pathlib import Path

from brandlib import Face


def load(fonts_dir):
    d = Path(fonts_dir)
    return {
        "sans600": Face(d / "IBMPlexSans-SemiBold.ttf"),
        "sans500": Face(d / "IBMPlexSans-Medium.ttf"),
        "sans400": Face(d / "IBMPlexSans-Regular.ttf"),
        "mono500": Face(d / "IBMPlexMono-Medium.ttf"),
        "mono400": Face(d / "IBMPlexMono-Regular.ttf"),
    }
