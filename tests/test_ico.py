import os
import struct
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "assets", "brand", "src"))

from ico import PNG_SIGNATURE, build_ico, png_size  # noqa: E402


def chunk(tag, data):
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def fake_png(w, h, color_type=2):
    """A valid 8-bit RGB (color_type 2) or RGBA (6) PNG filled with one colour."""
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    px = b"\x0b\x11\x18" + (b"\xff" if color_type == 6 else b"")
    raw = b"".join(b"\x00" + px * w for _ in range(h))
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class IcoWriter(unittest.TestCase):
    def test_png_size(self):
        self.assertEqual(png_size(fake_png(16, 32)), (16, 32))

    def test_rejects_non_png(self):
        with self.assertRaises(ValueError):
            png_size(b"GIF89a" + b"\x00" * 30)
        with self.assertRaises(ValueError):
            build_ico([b"not a png"])

    def test_png_size_rejects_truncated_png(self):
        good = fake_png(16, 16)
        for n in (8, 12, 16, 20, 23):
            with self.assertRaises(ValueError):
                png_size(good[:n])
        with self.assertRaises(ValueError):
            build_ico([good[:23]])

    def test_bpp_follows_the_colour_type(self):
        for color_type, expected in ((2, 24), (6, 32)):
            data = build_ico([fake_png(16, 16, color_type)])
            self.assertEqual(struct.unpack("<H", data[6 + 6:6 + 8])[0], expected)

    def test_rejects_unsupported_colour_type(self):
        with self.assertRaises(ValueError):
            build_ico([fake_png(16, 16, 0)])

    def test_rejects_empty_and_oversized(self):
        with self.assertRaises(ValueError):
            build_ico([])
        with self.assertRaises(ValueError):
            build_ico([fake_png(300, 300)])

    def test_container_layout(self):
        pngs = [fake_png(16, 16), fake_png(32, 32), fake_png(48, 48)]
        data = build_ico(pngs)
        self.assertEqual(struct.unpack("<HHH", data[:6]), (0, 1, 3))
        for i, png in enumerate(pngs):
            w, h, colours, reserved, planes, bpp, size, offset = struct.unpack(
                "<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
            self.assertEqual((w, h), png_size(png))
            self.assertEqual((colours, reserved, planes, bpp), (0, 0, 1, 24))
            self.assertEqual(size, len(png))
            self.assertEqual(data[offset:offset + size], png)
        self.assertEqual(len(data), 6 + 48 + sum(len(p) for p in pngs))

    def test_256_is_stored_as_zero(self):
        data = build_ico([fake_png(256, 256)])
        self.assertEqual(data[6:8], b"\x00\x00")


class ShippedIcon(unittest.TestCase):
    def test_favicon_ico_holds_16_32_48(self):
        path = os.path.join(ROOT, "assets", "brand", "favicon.ico")
        with open(path, "rb") as f:
            data = f.read()
        count = struct.unpack("<HHH", data[:6])[2]
        sizes = []
        for i in range(count):
            w, h, _, _, _, _, size, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
            self.assertEqual(png_size(data[offset:offset + size]), (w, h))
            sizes.append(w)
        self.assertEqual(sizes, [16, 32, 48])


if __name__ == "__main__":
    unittest.main()
