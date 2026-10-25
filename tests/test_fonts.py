"""Verify annotation portability when no system font can be used."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageFont

from vrlab2gif.core import bundled_font_path, create_gifs, load_font


class BundledFontTests(unittest.TestCase):
    def test_source_uses_bundled_arial_at_requested_size(self):
        font = load_font(37)
        self.assertEqual(Path(font.path).resolve(), bundled_font_path().resolve())
        self.assertEqual(font.getname(), ("Arial", "Regular"))
        self.assertEqual(font.size, 37)

    def test_frozen_bundle_renders_angle_gif_without_accessing_system_fonts(self):
        source_font = bundled_font_path()
        with tempfile.TemporaryDirectory(prefix=".test-fonts-", dir=Path.cwd()) as temporary:
            root = Path(temporary)
            (root / "fonts").mkdir()
            bundled = root / "fonts" / "arial.ttf"
            shutil.copyfile(source_font, bundled)
            input_dir = root / "input"
            input_dir.mkdir()
            with Image.new("RGB", (320, 100), "white") as image:
                image.save(input_dir / "view_Image_-30°_10°.png")
            actual_truetype = ImageFont.truetype
            loaded = []

            def embedded_only(path, *args, **kwargs):
                if Path(path).resolve() != bundled.resolve():
                    raise AssertionError(f"System font access is forbidden in this test: {path}")
                loaded.append(Path(path))
                return actual_truetype(path, *args, **kwargs)

            with patch.object(sys, "_MEIPASS", str(root), create=True), \
                    patch("vrlab2gif.core.ImageFont.truetype", side_effect=embedded_only):
                result = create_gifs(input_dir, root / "output", font_size=24)
            self.assertEqual(loaded, [bundled])
            with Image.open(result.output_paths[-1]) as image:
                self.assertEqual(image.size, (320, 100))
                # A white input acquires the black outline of the angle text.
                self.assertLess(min(image.convert("RGB").crop((10, 10, 260, 50)).getchannel("R").getdata()), 64)


if __name__ == "__main__":
    unittest.main()
