"""Recover measured angle labels without treating COM indices as degrees."""
from __future__ import annotations

import math
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from PIL import Image

from vrlab2gif.core import AngleFilters
from vrlab2gif.native import convert_exported_views
from vrlab2gif.observer import (AngleMetadataUnavailable, read_observer_axes,
                               restore_export_angles)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".test-observer-", dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.source = self.root / "AR 视角.speos360"
        self.frames = self.root / "frames"
        self.frames.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, *, horizontal=(-0.3, 0.3), vertical=(-0.2, 0.2), count=4,
                order=(0, 1, 2, 3), bottom="true", extra="", packed_override=None):
        def values(sequence):
            return "".join(f"<Value>{x}</Value>" for x in sequence)
        xml = (f'<?xml version="1.0"?>{extra}<Header_OptisVR>'
               f'<PictureFormat>0</PictureFormat><NumberOfPicture>{count}</NumberOfPicture>'
               '<SimulationObserver/><PictureIndexerHeader><version>1.000000</version>'
               '<IndexerType>1</IndexerType><ZenithMode>1</ZenithMode>'
               f'<PhiList>{values(math.radians(x) for x in horizontal)}</PhiList>'
               f'<ThetaList>{values(math.radians(x) for x in vertical)}</ThetaList>'
               f'<PictureOrder>{values(order)}</PictureOrder>'
               f'<ThetaAnglesStoredFromBottomToTop>{bottom}</ThetaAnglesStoredFromBottomToTop>'
               '</PictureIndexerHeader></Header_OptisVR>').encode()
        packed = zlib.compress(xml) if packed_override is None else packed_override
        self.source.write_bytes(b"OPTIS - OPTIS_VR file v" + struct.pack("<fI", 1, 21)
                                + b"MultiPictures OptisVR"
                                + struct.pack("<fIIII", 2, 0, len(xml), len(xml), len(packed)) + packed)

    def pictures(self):
        for h in range(2):
            for v in range(2):
                with Image.new("RGB", (140, 80), (h * 150, v * 150, 0)) as image:
                    image.save(self.frames / f"{self.source.stem}_Image_{h}_{v}.png")

    def test_radians_restore_signed_degree_labels_and_enable_filtered_gifs(self):
        self.fixture()
        self.pictures()
        original = self.source.read_bytes()
        self.assertTrue(restore_export_angles(self.source, self.frames))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual({p.name for p in self.frames.iterdir()}, {
            f"{self.source.stem}_Image_{h:.2f}°_{v:.2f}°.png" for h in (-0.3, 0.3) for v in (-0.2, 0.2)})
        # The top-left annotation must now be drawn rather than index fallback.
        result = convert_exported_views(self.frames, self.root / "gifs", 300, 24,
                                        AngleFilters(h_min=0, v_min=0))
        self.assertEqual(result.matched_count, 1)
        self.assertEqual({p.name for p in result.output_paths},
                         {"vertical_angle_0.2.gif", "collection_all_angles.gif"})
        with Image.open(result.output_paths[-1]) as image:
            rgb = image.convert("RGB")
            self.assertTrue(any(r > 230 and g > 230 and b > 230
                                for r, g, b in rgb.crop((10, 10, 130, 45)).getdata()))

    def test_incomplete_export_refuses_entire_mapping_before_any_rename(self):
        self.fixture()
        self.pictures()
        next(self.frames.iterdir()).unlink()
        names = {p.name for p in self.frames.iterdir()}
        messages = []
        self.assertFalse(restore_export_angles(self.source, self.frames, messages.append))
        self.assertEqual({p.name for p in self.frames.iterdir()}, names)
        self.assertIn("数量", messages[-1])

    def test_unknown_layout_reordering_and_fine_grids_are_never_guessed(self):
        for kwargs in ({"order": (3, 2, 1, 0)}, {"count": 5}, {"bottom": "false"},
                       {"horizontal": (0, 0.001)}, {"horizontal": (0.3, -0.3)},
                       {"horizontal": (float("nan"), 0)}):
            with self.subTest(kwargs=kwargs):
                self.fixture(**kwargs)
                with self.assertRaises(AngleMetadataUnavailable):
                    read_observer_axes(self.source)

    def test_truncated_oversized_and_entity_headers_are_rejected(self):
        self.fixture()
        valid = self.source.read_bytes()
        for data in (valid[:40], valid[:-5], valid[:60] + struct.pack("<I", 100_000_000) + valid[64:]):
            with self.subTest(size=len(data)):
                self.source.write_bytes(data)
                with self.assertRaises(AngleMetadataUnavailable):
                    read_observer_axes(self.source)
        self.fixture(extra='<!DOCTYPE Header_OptisVR [<!ENTITY x "unsafe">]>')
        with self.assertRaises(AngleMetadataUnavailable):
            read_observer_axes(self.source)
        self.fixture(packed_override=zlib.compress(b"x" * 1_000_000))
        with self.assertRaises(AngleMetadataUnavailable):
            read_observer_axes(self.source)

    def test_already_labeled_exports_do_not_require_header_parsing(self):
        self.source.write_bytes(b"a newer format")
        (self.frames / "manual_Image_-0.30°_0.20°.png").write_bytes(b"unused")
        self.assertTrue(restore_export_angles(self.source, self.frames))

    def test_real_official_samples_when_available(self):
        samples = Path(__file__).resolve().parents[1] / "samples" / "ansys-vrlab"
        ar = samples / "additional" / "AR_Observer_520nm.speos360"
        old = samples / "test_07_VRLab_export.OptisVR"
        if not (ar.is_file() and old.is_file()):
            self.skipTest("Downloaded official fixtures not present")
        axes = read_observer_axes(ar)
        self.assertEqual(axes.horizontal, (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3))
        self.assertEqual(axes.vertical, (-0.2, -0.1, 0, 0.1, 0.2))
        self.assertEqual(read_observer_axes(old).horizontal, (-100, -95, -90))


if __name__ == "__main__":
    unittest.main()
