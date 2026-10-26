"""Exercise native tkdnd registration and the Windows OLE-to-Tk event bridge."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tkinterdnd2 import COPY, REFUSE_DROP, TkinterDnD

from vrlab2gif.app import GifCreatorApp
from vrlab2gif.native import VRLabRegistrationError


class FileDropTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-drop-", dir=Path.cwd())
        self.directory = Path(self.temporary.name)
        self.first = self.directory / "中文 空格 {视角}.OptisVR"
        self.second = self.directory / "other.SPEOS360"
        for source in (self.first, self.second):
            source.write_bytes(b"native fixture")
        self.png_dir = self.directory / "PNG 导出 {视角}.v1"
        self.png_dir.mkdir()
        self.other_png_dir = self.directory / "other PNG folder"
        self.other_png_dir.mkdir()
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.registration_patch = patch("vrlab2gif.app.check_native_registration", return_value=None)
        self.registration_check = self.registration_patch.start()
        self.addCleanup(self.registration_patch.stop)
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

    def test_native_ole_bridge_accepts_png_folder_with_unicode_spaces_and_braces(self):
        self.app.select_page("logs")
        self.assertEqual(self.ole_enter(self.app.input_entry, [self.png_dir]), COPY)
        self.assertTrue(self.app._drop_hover)
        self.assertEqual(self.ole_drop(self.app.input_entry, [self.png_dir]), COPY)
        self.assertEqual(Path(self.app.input_file_var.get()), self.png_dir)
        self.assertEqual(Path(self.app.output_dir_var.get()),
                         self.directory / (self.png_dir.name + "_GIF"))
        self.assertEqual(self.app.page_var.get(), "settings")
        self.assertFalse(self.app._drop_hover)
        self.assertFalse(self.app._processing, "Dropping a folder must only select it")

    def test_native_drop_without_com_retains_input_and_shows_registration_options(self):
        self.registration_check.side_effect = VRLabRegistrationError()
        with patch("vrlab2gif.app.messagebox.showwarning") as warning, \
                patch("vrlab2gif.app.create_native_gifs") as native:
            self.assertEqual(self.ole_enter(self.app.drop_surface, [self.first]), COPY)
            self.assertEqual(self.ole_drop(self.app.drop_surface, [self.first]), COPY)
        self.assertEqual(Path(self.app.input_file_var.get()), self.first)
        self.assertTrue(self.app.registration_notice.winfo_manager())
        self.assertFalse(self.app._processing)
        self.assertIsNone(self.app._worker)
        native.assert_not_called()
        warning.assert_not_called()

    def test_invalid_drop_preserves_current_input_and_custom_output(self):
        self.app.select_input_file(str(self.first))
        self.app.output_dir_var.set(str(self.directory / "custom"))
        png = self.directory / "image.png"
        png.write_bytes(b"image")
        for paths in ([self.first, self.second], [self.first, self.png_dir],
                      [self.png_dir, self.other_png_dir], [png],
                      [self.directory / "missing.OptisVR"], [self.directory / "missing folder"]):
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

    def test_png_folder_selection_is_blocked_while_processing(self):
        self.app.select_input_file(str(self.first))
        self.app._set_processing(True)
        with patch("vrlab2gif.app.filedialog.askdirectory") as choose:
            self.app.ask_input_dir()
        choose.assert_not_called()
        self.assertEqual(self.ole_enter(self.app.input_entry, [self.png_dir]), REFUSE_DROP)
        self.assertEqual(self.ole_drop(self.app.input_entry, [self.png_dir]), REFUSE_DROP)
        self.assertEqual(Path(self.app.input_file_var.get()), self.first)
        self.assertTrue(self.app._processing)
        self.app._set_processing(False)

    def test_theme_switch_preserves_drag_feedback_and_leave_restores_surface(self):
        self.app._on_drag_enter(self.event(self.first))
        self.app.set_theme("light")
        c = self.app.appearance.colors
        self.assertEqual(self.app.drop_surface.itemcget(self.app._drop_border, "outline"), c.accent)
        self.app._on_drag_leave(self.event(self.first))
        self.assertEqual(self.app.drop_surface.itemcget(self.app._drop_border, "outline"), c.surface)


if __name__ == "__main__":
    unittest.main()
