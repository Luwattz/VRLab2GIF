"""Exercise native tkdnd registration and the Windows OLE-to-Tk event bridge."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tkinterdnd2 import COPY, REFUSE_DROP, TkinterDnD

from vrlab2gif.app import GifCreatorApp


class FileDropTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-drop-", dir=Path.cwd())
        self.directory = Path(self.temporary.name)
        self.first = self.directory / "中文 空格 {视角}.OptisVR"
        self.second = self.directory / "other.SPEOS360"
        for source in (self.first, self.second):
            source.write_bytes(b"native fixture")
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda kind, error, traceback: self.errors.append(error)
        self.app = GifCreatorApp(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.app._processing = False
        self.app.on_close()
        self.temporary.cleanup()
        self.assertEqual(self.errors, [])

    def event(self, *paths):
        return SimpleNamespace(data=self.root.tk.call("format", "%s", tuple(map(str, paths))))

    def ole_enter(self, target, paths):
        return self.root.tk.call("tkdnd::olednd::HandleDragEnter", str(target),
                                 ("CF_HDROP",), ("copy",), (), 0, 0, (0,), tuple(map(str, paths)))

    def ole_drop(self, target, paths):
        return self.root.tk.call("tkdnd::olednd::HandleDrop", str(target), (), 0, 0,
                                 "CF_HDROP", tuple(map(str, paths)))

    def test_native_ole_bridge_accepts_unicode_spaces_and_braces(self):
        self.assertEqual(self.ole_enter(self.app.drop_surface, [self.first]), COPY)
        self.assertTrue(self.app._drop_hover)
        self.assertEqual(self.ole_drop(self.app.drop_surface, [self.first]), COPY)
        self.assertEqual(Path(self.app.input_file_var.get()), self.first)
        self.assertEqual(Path(self.app.output_dir_var.get()), self.directory / (self.first.stem + "_GIF"))
        self.assertFalse(self.app._drop_hover)
        self.assertFalse(self.app._processing, "Dropping selects a file without launching Ansys")

    def test_dropping_on_log_page_resolves_to_window_and_shows_selected_file(self):
        self.app.select_page("logs")
        self.assertEqual(self.ole_enter(self.app.log_text, [self.second]), COPY)
        self.assertEqual(self.ole_drop(self.app.log_text, [self.second]), COPY)
        self.assertEqual(Path(self.app.input_file_var.get()), self.second)
        self.assertEqual(self.app.page_var.get(), "settings")

    def test_invalid_drop_preserves_current_input_and_custom_output(self):
        self.app.select_input_file(str(self.first))
        self.app.output_dir_var.set(str(self.directory / "custom"))
        png = self.directory / "image.png"
        png.write_bytes(b"image")
        for paths in ([self.first, self.second], [self.directory], [png], [self.directory / "missing.OptisVR"]):
            with self.subTest(paths=paths):
                self.assertEqual(self.app._on_file_drop(self.event(*paths)), REFUSE_DROP)
                self.assertEqual(Path(self.app.input_file_var.get()), self.first)
                self.assertEqual(Path(self.app.output_dir_var.get()), self.directory / "custom")
                self.assertEqual(self.app._status_tone, "error")

    def test_malformed_tcl_payload_is_rejected(self):
        self.assertEqual(self.app._on_file_drop(SimpleNamespace(data="{broken")), REFUSE_DROP)
        self.assertEqual(self.app.input_file_var.get(), "")

    def test_busy_drop_and_drag_are_refused_without_changing_progress_or_input(self):
        self.app.select_input_file(str(self.first))
        self.app._set_processing(True)
        self.app.status_var.set("正在导出，保留此状态")
        self.app.progress_var.set(0.5)
        self.assertEqual(self.ole_enter(self.app.input_entry, [self.second]), REFUSE_DROP)
        self.assertEqual(self.ole_drop(self.app.input_entry, [self.second]), REFUSE_DROP)
        self.assertEqual(Path(self.app.input_file_var.get()), self.first)
        self.assertEqual(self.app.status_var.get(), "正在导出，保留此状态")
        self.assertEqual(self.app.progress_var.get(), 0.5)
        self.assertFalse(self.app._drop_hover)
        self.app._set_processing(False)

    def test_png_folder_cannot_start_a_worker(self):
        self.app.input_file_var.set(str(self.directory))
        with patch("vrlab2gif.app.messagebox.showerror") as error, \
                patch("vrlab2gif.app.create_native_gifs") as convert:
            self.app.start_processing()
        self.assertFalse(self.app._processing)
        self.assertIsNone(self.app._worker)
        convert.assert_not_called()
        error.assert_called_once()
        self.assertIn("不支持文件夹", error.call_args.args[1])
        self.assertFalse(hasattr(self.app, "input_folder_button"))

    def test_theme_switch_preserves_drag_feedback_and_leave_restores_surface(self):
        self.app._on_drag_enter(self.event(self.first))
        self.app.set_theme("light")
        c = self.app.appearance.colors
        self.assertEqual(self.app.drop_surface.itemcget(self.app._drop_border, "outline"), c.accent)
        self.app._on_drag_leave(self.event(self.first))
        self.assertEqual(self.app.drop_surface.itemcget(self.app._drop_border, "outline"), c.entry_border)


if __name__ == "__main__":
    unittest.main()
