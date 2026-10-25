"""Exercise the conversion API using real PNG and GIF files."""

import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image, ImageSequence

from vrlab2gif.core import (
    AngleFilters,
    ConversionCancelled,
    create_gifs,
    parse_filename,
)


class FilenameAndFilterTests(unittest.TestCase):
    def test_parse_integer_decimal_negative_and_uppercase_png(self):
        examples = {
            "1_Image_0°_10°.png": (0.0, 10.0),
            "002_Image_-12.50°_-3.25°.png": (-12.5, -3.25),
            "experiment_Image_42.0°_0.00°.PNG": (42.0, 0.0),
        }
        for filename, expected in examples.items():
            with self.subTest(filename=filename):
                self.assertEqual(parse_filename(filename), expected)

    def test_unrelated_or_malformed_names_are_skipped(self):
        for filename in (
            "image.png",
            "1_Image_0_10.png",
            "1_Image_nan°_10°.png",
            "1_Image_0°_inf°.png",
            "1_Image_0°_10°.jpg",
            "1_Image_0°_10°.png.backup",
        ):
            with self.subTest(filename=filename):
                self.assertIsNone(parse_filename(filename))

    def test_filters_accept_open_and_equal_bounds(self):
        AngleFilters()
        AngleFilters(h_min=-10.5, h_max=-10.5, v_min=0, v_max=0)
        AngleFilters(h_max=30, v_min=-20)

    def test_filters_reject_nonfinite_and_reversed_bounds(self):
        for field in ("h_min", "h_max", "v_min", "v_max"):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        AngleFilters(**{field: value})
        for bounds in ({"h_min": 1, "h_max": 0}, {"v_min": 5, "v_max": -5}):
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    AngleFilters(**bounds)


class GifConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix=".test-core-", dir=Path(__file__).resolve().parent
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.input_dir = self.root / "输入图片"
        self.input_dir.mkdir()
        self.output_dir = self.input_dir / "output"

    def make_png(self, name, color, *, size=(160, 100), mode="RGB"):
        destination = self.input_dir / name
        with Image.new(mode, size, color) as image:
            image.save(destination)
        return destination

    def gif_frames(self, path):
        with Image.open(path) as gif:
            self.assertEqual(gif.format, "GIF")
            loop = gif.info.get("loop")
            frames = [
                (frame.convert("RGB").getpixel((140, 80)), frame.info.get("duration"))
                for frame in ImageSequence.Iterator(gif)
            ]
        return loop, frames

    def test_grouping_order_collection_metadata_and_result_counts(self):
        # The filename order differs from both the horizontal and vertical order.
        self.make_png("1_Image_20°_0.00°.PNG", "blue")
        self.make_png("2_Image_10°_10.0°.png", "yellow")
        self.make_png("3_Image_-10°_0.0°.png", "red")
        self.make_png("4_Image_0°_10°.png", "green")
        self.make_png("unrelated.png", "white")
        (self.input_dir / "notes.txt").write_text("not an image", encoding="utf-8")

        result = create_gifs(self.input_dir, self.output_dir, delay_ms=317)

        self.assertEqual(result.scanned_count, 5)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.filtered_count, 0)
        self.assertEqual(result.matched_count, 4)
        self.assertEqual(result.duration_ms, 310)
        self.assertIsInstance(result.output_paths, tuple)
        self.assertEqual(
            {path.name for path in result.output_paths},
            {"vertical_angle_0.0.gif", "vertical_angle_10.0.gif", "collection_all_angles.gif"},
        )
        for path in result.output_paths:
            self.assertEqual(path.parent, self.output_dir)
            self.assertTrue(path.is_file())

        expected = {
            "vertical_angle_0.0.gif": [(255, 0, 0), (0, 0, 255)],
            "vertical_angle_10.0.gif": [(0, 128, 0), (255, 255, 0)],
            "collection_all_angles.gif": [
                (0, 128, 0), (255, 255, 0), (255, 0, 0), (0, 0, 255)
            ],
        }
        for name, colors in expected.items():
            with self.subTest(name=name):
                loop, frames = self.gif_frames(self.output_dir / name)
                self.assertEqual(loop, 0)
                self.assertEqual([color for color, _ in frames], colors)
                self.assertEqual([duration for _, duration in frames], [310] * len(colors))

    def test_inclusive_angle_filters_and_counting(self):
        for index, (horizontal, vertical) in enumerate(
            [(-10, -5), (10, 5), (-11, 0), (11, 0), (0, -6), (0, 6)]
        ):
            self.make_png(f"{index}_Image_{horizontal}°_{vertical}°.png", "red")

        result = create_gifs(
            self.input_dir,
            self.output_dir,
            filters=AngleFilters(h_min=-10, h_max=10, v_min=-5, v_max=5),
        )

        self.assertEqual(result.scanned_count, 6)
        self.assertEqual(result.filtered_count, 4)
        self.assertEqual(result.matched_count, 2)
        self.assertEqual(result.skipped_count, 0)
        _, frames = self.gif_frames(self.output_dir / "collection_all_angles.gif")
        self.assertEqual(len(frames), 2)

    def test_transparency_is_composited_on_black_and_annotation_is_visible(self):
        self.make_png("1_Image_0°_0°.png", (0, 0, 0, 0), mode="RGBA")
        create_gifs(self.input_dir, self.output_dir)
        with Image.open(self.output_dir / "vertical_angle_0.0.gif") as gif:
            rgb = gif.convert("RGB")
            self.assertEqual(rgb.getpixel((140, 80)), (0, 0, 0))
            annotation_pixels = list(rgb.crop((10, 10, 150, 60)).getdata())
            self.assertTrue(any(min(pixel) > 200 for pixel in annotation_pixels))

    def test_partially_transparent_pixels_are_blended_with_black(self):
        self.make_png("1_Image_0°_0°.png", (100, 150, 200, 128), mode="RGBA")
        create_gifs(self.input_dir, self.output_dir)
        _, frames = self.gif_frames(self.output_dir / "vertical_angle_0.0.gif")
        self.assertEqual(frames[0][0], (50, 75, 100))

    def test_transparent_animation_retains_black_background_and_clears_old_content(self):
        for name, color, box in (
            ("1_Image_0°_0°.png", (255, 0, 0, 255), (20, 70, 40, 90)),
            ("2_Image_10°_0°.png", (0, 0, 255, 255), (70, 70, 90, 90)),
        ):
            with Image.new("RGBA", (160, 100), (0, 0, 0, 0)) as image:
                image.paste(color, box)
                image.save(self.input_dir / name)

        create_gifs(self.input_dir, self.output_dir)

        for name in ("vertical_angle_0.0.gif", "collection_all_angles.gif"):
            with self.subTest(name=name):
                with Image.open(self.output_dir / name) as gif:
                    frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(gif)]
                self.assertEqual(len(frames), 2)
                for frame in frames:
                    self.assertEqual(frame.getpixel((0, 0)), (0, 0, 0))
                    self.assertEqual(frame.getpixel((140, 80)), (0, 0, 0))
                self.assertEqual(frames[0].getpixel((25, 75)), (255, 0, 0))
                self.assertEqual(frames[0].getpixel((75, 75)), (0, 0, 0))
                self.assertEqual(frames[1].getpixel((25, 75)), (0, 0, 0))
                self.assertEqual(frames[1].getpixel((75, 75)), (0, 0, 255))
                for frame in frames:
                    frame.close()

    def test_no_png_raises_without_creating_output(self):
        with self.assertRaises(ValueError):
            create_gifs(self.input_dir, self.output_dir)
        self.assertFalse(self.output_dir.exists())

    def test_no_matching_image_raises_without_creating_output(self):
        self.make_png("1_Image_10°_0°.png", "red")
        with self.assertRaises(ValueError):
            create_gifs(
                self.input_dir, self.output_dir, filters=AngleFilters(h_max=0)
            )
        self.assertFalse(self.output_dir.exists())

    def test_only_malformed_filenames_raises_without_creating_output(self):
        self.make_png("unrelated.png", "red")
        with self.assertRaises(ValueError):
            create_gifs(self.input_dir, self.output_dir)
        self.assertFalse(self.output_dir.exists())

    def test_corrupt_image_error_identifies_the_source_filename(self):
        damaged_name = "1_Image_0°_0°.png"
        (self.input_dir / damaged_name).write_bytes(b"not a PNG")
        with self.assertRaises(Exception) as caught:
            create_gifs(self.input_dir, self.output_dir)
        self.assertIn(damaged_name, str(caught.exception))
        self.assertFalse(self.output_dir.exists())

    def test_different_sizes_are_rejected_before_any_output_is_changed(self):
        self.make_png("1_Image_0°_0°.png", "red")
        self.make_png("2_Image_0°_10°.png", "blue", size=(200, 100))
        self.output_dir.mkdir()
        existing = self.output_dir / "vertical_angle_0.0.gif"
        existing.write_bytes(b"previous output")

        with self.assertRaises(ValueError):
            create_gifs(self.input_dir, self.output_dir)

        self.assertEqual(existing.read_bytes(), b"previous output")
        self.assertEqual(set(self.output_dir.iterdir()), {existing})

    def test_empty_paths_are_rejected(self):
        self.make_png("1_Image_0°_0°.png", "red")
        for source, output in (("", self.output_dir), (self.input_dir, "")):
            with self.subTest(source=source, output=output):
                with self.assertRaises(ValueError):
                    create_gifs(source, output)

    def test_invalid_delay_and_font_size_are_rejected_before_output_creation(self):
        self.make_png("1_Image_0°_0°.png", "red")
        for kwargs in (
            {"delay_ms": 0},
            {"delay_ms": 9},
            {"delay_ms": 655351},
            {"font_size": 0},
            {"font_size": -1},
            {"font_size": 513},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    create_gifs(self.input_dir, self.output_dir, **kwargs)
                self.assertFalse(self.output_dir.exists())

    def test_gif_duration_limits_are_representable(self):
        self.make_png("1_Image_0°_0°.png", "red")
        for duration in (10, 655350):
            with self.subTest(duration=duration):
                result = create_gifs(self.input_dir, self.output_dir, delay_ms=duration)
                self.assertEqual(result.duration_ms, duration)
                _, frames = self.gif_frames(self.output_dir / "vertical_angle_0.0.gif")
                self.assertEqual(frames[0][1], duration)

    def test_pre_cancelled_conversion_does_not_create_output(self):
        self.make_png("1_Image_0°_0°.png", "red")
        cancel_event = threading.Event()
        cancel_event.set()

        with self.assertRaises(ConversionCancelled) as caught:
            create_gifs(self.input_dir, self.output_dir, cancel_event=cancel_event)

        self.assertEqual(caught.exception.output_paths, ())
        self.assertFalse(self.output_dir.exists())

    def test_cancellation_reports_only_completed_readable_gifs(self):
        self.make_png("1_Image_0°_0°.png", "red")
        self.make_png("2_Image_0°_10°.png", "blue")
        cancel_event = threading.Event()

        def cancel_after_completed_output(message):
            if message.startswith("[成功]"):
                cancel_event.set()

        with self.assertRaises(ConversionCancelled) as caught:
            create_gifs(
                self.input_dir,
                self.output_dir,
                cancel_event=cancel_event,
                log=cancel_after_completed_output,
            )

        completed = caught.exception.output_paths
        self.assertIsInstance(completed, tuple)
        self.assertEqual(len(completed), 1)
        self.assertEqual(set(self.output_dir.iterdir()), set(completed))
        with Image.open(completed[0]) as gif:
            gif.load()
            self.assertEqual(gif.format, "GIF")

    def test_cancel_during_save_discards_new_file_and_preserves_existing_output(self):
        self.make_png("1_Image_0°_0°.png", "red")
        self.output_dir.mkdir()
        previous = self.output_dir / "vertical_angle_0.0.gif"
        previous.write_bytes(b"previous output")
        cancel_event = threading.Event()
        original_save = Image.Image.save

        def save_then_cancel(image, *args, **kwargs):
            original_save(image, *args, **kwargs)
            cancel_event.set()

        with patch.object(Image.Image, "save", new=save_then_cancel):
            with self.assertRaises(ConversionCancelled) as caught:
                create_gifs(self.input_dir, self.output_dir, cancel_event=cancel_event)

        self.assertEqual(caught.exception.output_paths, ())
        self.assertEqual(previous.read_bytes(), b"previous output")
        self.assertEqual(set(self.output_dir.iterdir()), {previous})

    def test_failed_save_preserves_previous_output_and_cleans_partial_file(self):
        self.make_png("1_Image_0°_0°.png", "red")
        self.output_dir.mkdir()
        previous = {
            self.output_dir / "vertical_angle_0.0.gif": b"previous individual GIF",
            self.output_dir / "collection_all_angles.gif": b"previous collection GIF",
        }
        for path, content in previous.items():
            path.write_bytes(content)

        def partial_save_then_fail(image, destination, *args, **kwargs):
            if hasattr(destination, "write"):
                destination.write(b"incomplete GIF")
            else:
                Path(destination).write_bytes(b"incomplete GIF")
            raise OSError("simulated disk write failure")

        with patch.object(Image.Image, "save", new=partial_save_then_fail):
            with self.assertRaises(Exception):
                create_gifs(self.input_dir, self.output_dir)

        self.assertEqual(set(self.output_dir.iterdir()), set(previous))
        for path, content in previous.items():
            self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
