from pathlib import Path
import tempfile
import unittest
from tkinterdnd2 import TkinterDnD

from vrlab2gif.appearance import AppleAppearance
from vrlab2gif.ppt_dialog import PptExportDialog, suggested_ppt_path


class PptDialogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-ppt-dialog-", dir=Path.cwd())
        self.directory = Path(self.temporary.name)
        self.gif = self.directory / "collection_all_views.gif"
        self.gif.write_bytes(b"selection fixture")
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.appearance = AppleAppearance(self.root)
        self.dialog = PptExportDialog(self.root, self.appearance, (self.gif,), self.directory / "report.pptx")

    def tearDown(self):
        if self.dialog.winfo_exists():
            self.dialog.destroy()
        self.root.destroy()
        self.temporary.cleanup()

    def test_default_options_and_restore_and_confirm(self):
        self.dialog.title_var.set("自定义标题")
        self.dialog.open_var.set(True)
        self.dialog.restore_defaults()
        self.assertEqual(self.dialog.title_var.get(), "视角合成结果")
        self.assertEqual(self.dialog.footer_var.get(), "Intelligent Efficiency Team")
        self.assertFalse(self.dialog.open_var.get())
        self.dialog.collections_var.set(True)
        self.dialog.confirm()
        request = self.dialog.result
        self.assertIsNotNone(request)
        self.assertEqual(request.paths, (self.gif,))
        self.assertTrue(request.options.collections_only)
        self.assertFalse(request.output_path.exists(), "Confirming must not write the presentation on the Tk thread")

    def test_invalid_title_or_path_stays_in_settings(self):
        self.dialog.title_var.set("")
        self.dialog.confirm()
        self.assertTrue(self.dialog.winfo_exists())
        self.assertIsNone(self.dialog.result)
        self.assertIn("标题", self.dialog.error_var.get())
        self.dialog.restore_defaults()
        self.dialog.path_var.set("report.ppt")
        self.dialog.confirm()
        self.assertIn("pptx", self.dialog.error_var.get())

    def test_default_filename_avoids_existing_reports(self):
        first = self.directory / "source_report.pptx"
        first.write_bytes(b"old")
        candidate = suggested_ppt_path(self.directory, "source")
        self.assertNotEqual(candidate, first)
        self.assertEqual(candidate.name, "source_report_02.pptx")


if __name__ == "__main__":
    unittest.main()
