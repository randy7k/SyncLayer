"""Write a Windows .ico container with embedded PNG images (standard library only).

Each image is a complete PNG file as bytes; width and height are read from its IHDR.
A size of 256 is stored as 0, as the ICO format requires; larger sizes are rejected. Bits per pixel come
from the IHDR colour type (2 = RGB, 24; 6 = RGBA, 32).
"""

import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data):
    """(width, height) from a PNG's IHDR chunk."""
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    if len(data) < 24:
        raise ValueError("truncated PNG")
    return struct.unpack(">II", data[16:24])


def png_bpp(data):
    """Bits per pixel from the IHDR colour type: 2 (RGB) -> 24, 6 (RGBA) -> 32."""
    png_size(data)
    if len(data) < 26:
        raise ValueError("truncated PNG")
    try:
        return {2: 24, 6: 32}[data[25]]
    except KeyError:
        raise ValueError(f"unsupported PNG colour type {data[25]}") from None


def build_ico(pngs):
    """Bytes of an ICO file holding the given PNG images, in the order given."""
    if not pngs:
        raise ValueError("no images")
    if len(pngs) > 0xFFFF:
        raise ValueError("too many images")
    out = [struct.pack("<HHH", 0, 1, len(pngs))]
    offset = 6 + 16 * len(pngs)
    for data in pngs:
        w, h = png_size(data)
        if not (0 < w <= 256 and 0 < h <= 256):
            raise ValueError(f"ICO images must be 1 to 256 px, got {w}x{h}")
        # width, height, palette colours, reserved, planes, bits per pixel, size, offset
        out.append(struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, png_bpp(data), len(data), offset))
        offset += len(data)
    out.extend(pngs)
    return b"".join(out)
