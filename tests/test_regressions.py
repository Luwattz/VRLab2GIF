"""Regression checks for decoded pictures and preserving existing results."""

from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

from PIL import Image, ImageChops

from vrlab2gif.core import ConversionCancelled, create_gifs


class ConversionRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        # An explicit project-local parent also works in restricted Windows sandboxes.
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-regression-", dir=Path.cwd())
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.input_dir = self.directory / "input"
        self.output_dir = self.directory / "output"
        self.input_dir.mkdir()

    def _picture(self, index: int, vertical: int = 0) -> Path:
        path = self.input_dir / f"{index}_Image_{index}\N{DEGREE SIGN}_{vertical}\N{DEGREE SIGN}.png"
        with Image.new("RGBA", (300, 160), (0, 0, 0, 0)) as image:
            image.paste(("red", "green", "blue")[index % 3], (100 + 20 * index, 80, 110 + 20 * index, 90))
            image.save(path)
        return path

    def test_every_decoded_frame_keeps_transparent_background_black(self) -> None:
        """Different local palettes must not turn disposal regions white."""
        for index in range(3):
            self._picture(index)

        result = create_gifs(self.input_dir, self.output_dir, font_size=16)

        self.assertEqual(len(result.output_paths), 2)
        for path in result.output_paths:
            with self.subTest(output=path.name), Image.open(path) as animation:
                self.assertEqual(animation.n_frames, 3)
                self.assertEqual(animation.info["loop"], 0)
                for index in range(3):
                    animation.seek(index)
                    with animation.convert("RGB") as decoded, Image.new("RGB", (300, 160), "black") as expected:
                        expected.paste(("red", "green", "blue")[index], (100 + 20 * index, 80, 110 + 20 * index, 90))
                        # The caption occupies the top of the picture. Every pixel below
                        # it has a known expected color independent of font rendering.
                        with decoded.crop((0, 50, 300, 160)) as actual_region, expected.crop((0, 50, 300, 160)) as expected_region:
                            with ImageChops.difference(actual_region, expected_region) as difference:
                                self.assertIsNone(difference.getbbox(), f"Incorrect pixels in {path.name}, frame {index}")

    def test_valid_crc_but_undecodable_png_does_not_replace_any_old_result(self) -> None:
        """Container verification alone cannot establish that pixels decode."""
        good = self._picture(0, vertical=1)
        broken = self._picture(1, vertical=0)
        raw = good.read_bytes()
        rewritten = bytearray(raw[:8])
        position = 8
        while position < len(raw):
            length = struct.unpack(">I", raw[position:position + 4])[0]
            kind = raw[position + 4:position + 8]
            data = raw[position + 8:position + 8 + length]
            if kind == b"IDAT":
                data = b"invalid zlib stream with a correct PNG chunk CRC"
            rewritten.extend(struct.pack(">I", len(data)))
            rewritten.extend(kind + data)
            rewritten.extend(struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
            position += length + 12
        broken.write_bytes(rewritten)
        with Image.open(broken) as image:
            image.verify()  # Demonstrate the input passes PNG structural checks.

        self.output_dir.mkdir()
        originals = {
            "vertical_angle_1.0.gif": b"existing completed group result",
            "collection_all_angles.gif": b"existing completed collection result",
        }
        for name, data in originals.items():
            (self.output_dir / name).write_bytes(data)

        with self.assertRaises(ValueError):
            create_gifs(self.input_dir, self.output_dir)

        self.assertEqual({path.name for path in self.output_dir.iterdir()}, set(originals))
        for name, data in originals.items():
            self.assertEqual((self.output_dir / name).read_bytes(), data)

    def test_cancel_during_save_preserves_old_output_and_removes_temporary(self) -> None:
        self._picture(0)
        self.output_dir.mkdir()
        old_result = self.output_dir / "vertical_angle_0.0.gif"
        old_bytes = b"previous completed animation"
        old_result.write_bytes(old_bytes)
        cancelled = threading.Event()
        original_save = Image.Image.save

        def save_then_cancel(image: Image.Image, path: str | Path, *args: object, **kwargs: object) -> None:
            original_save(image, path, *args, **kwargs)
            cancelled.set()

        with patch.object(Image.Image, "save", save_then_cancel):
            with self.assertRaises(ConversionCancelled) as caught:
                create_gifs(self.input_dir, self.output_dir, cancel_event=cancelled)

        self.assertEqual(caught.exception.output_paths, ())
        self.assertEqual(old_result.read_bytes(), old_bytes)
        self.assertEqual({path.name for path in self.output_dir.iterdir()}, {old_result.name})

    def test_failed_save_preserves_old_output_and_removes_partial_temporary(self) -> None:
        self._picture(0)
        self.output_dir.mkdir()
        old_result = self.output_dir / "vertical_angle_0.0.gif"
        old_bytes = b"previous completed animation"
        old_result.write_bytes(old_bytes)

        def incomplete_save(image: Image.Image, path: str | Path, *args: object, **kwargs: object) -> None:
            Path(path).write_bytes(b"partial animation")
            raise OSError("Simulated write failure")

        with patch.object(Image.Image, "save", incomplete_save):
            with self.assertRaises(OSError):
                create_gifs(self.input_dir, self.output_dir)

        self.assertEqual(old_result.read_bytes(), old_bytes)
        self.assertEqual({path.name for path in self.output_dir.iterdir()}, {old_result.name})


if __name__ == "__main__":
    unittest.main()
