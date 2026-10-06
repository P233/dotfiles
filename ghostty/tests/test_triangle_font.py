import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTFont


SCRIPT = Path(__file__).resolve().parents[1] / "install-triangle-font.py"
SPEC = importlib.util.spec_from_file_location("triangle_font", SCRIPT)
triangle_font = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(triangle_font)


class TriangleFontTests(unittest.TestCase):
    def test_serialized_font_has_only_the_four_native_arrow_codepoints(self):
        font = TTFont(io.BytesIO(triangle_font.font_bytes()), checkChecksums=2)
        self.assertEqual(set(font.getBestCmap()), {0x2190, 0x2191, 0x2192, 0x2193})
        self.assertEqual(len(font.getGlyphOrder()), 5)
        self.assertEqual(font["name"].getDebugName(1), "Tmux Solid Triangles")
        self.assertEqual(font["post"].isFixedPitch, 1)

    def test_triangles_fit_the_pragmata_cell_and_point_in_the_correct_direction(self):
        font = TTFont(io.BytesIO(triangle_font.font_bytes()))
        self.assertEqual(font["head"].unitsPerEm, 2048)
        for codepoint, name in font.getBestCmap().items():
            glyph = font["glyf"][name]
            coordinates, ends, flags = glyph.getCoordinates(font["glyf"])
            points = list(coordinates)
            self.assertEqual(list(ends), [2])
            self.assertTrue(all(flag & 1 for flag in flags))
            self.assertEqual(font["hmtx"][name][0], 1024)
            self.assertTrue(all(0 <= x <= 1024 and -362 <= y <= 1884 for x, y in points))
            if codepoint in (0x2190, 0x2192):
                base = next(x for x, _ in points if sum(px == x for px, _ in points) == 2)
                tip = next(x for x, _ in points if x != base)
                self.assertEqual(tip < base, codepoint == 0x2190)
            else:
                base = next(y for _, y in points if sum(py == y for _, py in points) == 2)
                tip = next(y for _, y in points if y != base)
                self.assertEqual(tip > base, codepoint == 0x2191)

    def test_reinstall_keeps_unchanged_font_bytes_and_modification_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Fonts/triangles.ttf"
            triangle_font.install_font(path)
            before = path.read_bytes(), path.stat().st_mtime_ns
            triangle_font.install_font(path)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_failed_replacement_preserves_existing_font_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "triangles.ttf"
            path.write_bytes(b"existing font")
            with patch.object(triangle_font.os, "replace", side_effect=OSError("write failed")):
                with self.assertRaisesRegex(OSError, "write failed"):
                    triangle_font.install_font(path)
            self.assertEqual(path.read_bytes(), b"existing font")
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
