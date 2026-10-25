"""Verify native presentation structure, animation bytes and safe publication."""
from io import BytesIO
from pathlib import Path
import posixpath
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from PIL import Image

from vrlab2gif.core import ConversionCancelled
from vrlab2gif.ppt import (A, P, R, REL, PptOptions, export_gifs_to_pptx,
                          HEADER_Y, BOTTOM_INSET, HEIGHT, LEFT, TITLE_WIDTH)


class PptExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-ppt-", dir=Path.cwd())
        self.root = Path(self.temporary.name)
        self.group = self.gif("vertical_angle_10.0.gif", (320, 180))
        self.collection = self.gif("collection_all_angles.gif", (100, 200))
        self.output = self.root / "报告.pptx"

    def tearDown(self):
        self.temporary.cleanup()

    def gif(self, name, size):
        path = self.root / name
        with Image.new("RGB", size, "red") as first, Image.new("RGB", size, "blue") as second:
            first.save(path, save_all=True, append_images=[second], duration=[50, 70], loop=0)
        return path

    def test_complete_package_preserves_original_gif_animation_and_reference_style(self):
        options = PptOptions(title="测试 <>&", footer="研发 & 测试")
        result = export_gifs_to_pptx((self.group, self.collection), self.output, options)
        self.assertEqual(result.slide_count, 2)
        self.assertEqual(result.gif_paths, (self.collection, self.group))
        ns = {"p": P, "a": A}
        with ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            for name in archive.namelist():
                if name.endswith((".xml", ".rels")):
                    xml = ET.fromstring(archive.read(name))
                    if name.endswith(".rels"):
                        base = str(Path(name).as_posix().rsplit("/_rels/", 1)[0]) if "/_rels/" in name else ""
                        for rel in xml.findall(f"{{{REL}}}Relationship"):
                            target = posixpath.normpath(posixpath.join(base, rel.attrib["Target"]))
                            self.assertIn(target, archive.namelist())
            presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
            size = presentation.find("p:sldSz", ns)
            self.assertEqual((size.get("cx"), size.get("cy")), ("12192000", "6858000"))
            master = ET.fromstring(archive.read("ppt/slideMasters/slideMaster1.xml"))
            self.assertEqual(master.find(".//a:fld", ns).get("type"), "slidenum")
            self.assertIn("研发 & 测试", [t.text for t in master.findall(".//a:t", ns)])
            for i, source in enumerate((self.collection, self.group), 1):
                embedded = archive.read(f"ppt/media/image{i}.gif")
                self.assertEqual(embedded, source.read_bytes())
                with Image.open(BytesIO(embedded)) as image:
                    self.assertEqual(image.n_frames, 2)
                    image.seek(1)
                    self.assertEqual(image.info["duration"], 70)
                slide = ET.fromstring(archive.read(f"ppt/slides/slide{i}.xml"))
                props = slide.find(".//p:sp/p:txBody/a:p/a:r/a:rPr", ns)
                self.assertEqual(props.get("sz"), "2400")
                self.assertEqual(props.find("a:solidFill/a:srgbClr", ns).get("val"), "FFA84F")
                self.assertEqual(props.find("a:ea", ns).get("typeface"), "Microsoft YaHei")
                title = slide.find(".//p:sp/p:txBody/a:p/a:r/a:t", ns).text
                self.assertTrue(title.startswith("测试 <>&"))
                self.assertIn("全角度合集" if i == 1 else "垂直角度", title)
                tr = slide.find(".//p:pic/p:spPr/a:xfrm", ns)
                x, y = [int(tr.find("a:off", ns).get(key))/12700 for key in ("x", "y")]
                w, h = [int(tr.find("a:ext", ns).get(key))/12700 for key in ("cx", "cy")]
                self.assertGreaterEqual(x, LEFT-0.001)
                self.assertGreaterEqual(y, HEADER_Y+8-0.001)
                self.assertLessEqual(y+h, HEIGHT-BOTTOM_INSET-8+0.001)
                with Image.open(source) as image:
                    self.assertAlmostEqual(w/h, image.width/image.height, places=5)

    def test_collection_only_omits_group_pages(self):
        result = export_gifs_to_pptx((self.group, self.collection), self.output, PptOptions(collections_only=True))
        self.assertEqual(result.slide_count, 1)
        self.assertEqual(result.gif_paths, (self.collection,))
        with ZipFile(self.output) as archive:
            self.assertEqual(archive.read("ppt/media/image1.gif"), self.collection.read_bytes())

    def test_invalid_later_gif_does_not_replace_existing_report(self):
        self.output.write_bytes(b"old presentation")
        self.collection.write_bytes(b"broken GIF")
        with self.assertRaisesRegex(ValueError, "无法读取 GIF"):
            export_gifs_to_pptx((self.group, self.collection), self.output)
        self.assertEqual(self.output.read_bytes(), b"old presentation")
        self.assertFalse(list(self.root.glob(".vrlab2gif-ppt-*")))

    def test_cancellation_during_export_keeps_old_report_and_gifs(self):
        self.output.write_bytes(b"old presentation")
        old_gif = self.group.read_bytes()
        cancel = Event()
        with self.assertRaises(ConversionCancelled):
            export_gifs_to_pptx((self.group, self.collection), self.output, cancel_event=cancel,
                                progress=lambda done, total, label: cancel.set() if done == 1 else None)
        self.assertEqual(self.output.read_bytes(), b"old presentation")
        self.assertEqual(self.group.read_bytes(), old_gif)
        self.assertFalse(list(self.root.glob(".vrlab2gif-ppt-*")))

    def test_io_failure_keeps_old_report_and_removes_partial_package(self):
        self.output.write_bytes(b"old presentation")
        with patch.object(ZipFile, "writestr", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                export_gifs_to_pptx((self.group,), self.output)
        self.assertEqual(self.output.read_bytes(), b"old presentation")
        self.assertFalse(list(self.root.glob(".vrlab2gif-ppt-*")))

    def test_invalid_settings_and_unfittable_title_are_rejected(self):
        for value in ("", "a\ntext", "a\x00text"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PptOptions(title=value)
        with self.assertRaisesRegex(ValueError, "标题太长"):
            export_gifs_to_pptx((self.group,), self.output, PptOptions(title="测试"*100))
        with self.assertRaisesRegex(ValueError, "没有可导出"):
            export_gifs_to_pptx((self.group,), self.output, PptOptions(collections_only=True))
        with self.assertRaisesRegex(ValueError, "pptx"):
            export_gifs_to_pptx((self.group,), self.output.with_suffix(".ppt"))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
