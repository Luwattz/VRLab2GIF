"""Exercise the real Tk event loop, worker completion, and safe closing."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image
from tkinterdnd2 import TkinterDnD

from vrlab2gif.app import GifCreatorApp
from vrlab2gif.core import ConversionResult
from vrlab2gif.native import convert_exported_views
from vrlab2gif.ppt_dialog import PptExportRequest
from vrlab2gif.ppt import PptOptions
from zipfile import ZipFile


class DesktopIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-app-", dir=Path.cwd())
        self.directory = Path(self.temporary.name)
        self.input_dir = self.directory / "input"
        self.output_dir = self.directory / "output"
        self.input_dir.mkdir()
        self.source = self.directory / "sample.OptisVR"
        self.source.write_bytes(b"native fixture")
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.callback_errors: list[BaseException] = []
        self.root.report_callback_exception = lambda kind, error, traceback: self.callback_errors.append(error)
        self.app = GifCreatorApp(self.root)
        self.app.input_file_var.set(str(self.source))
        self.app.output_dir_var.set(str(self.output_dir))
        self.dialogs: list[tuple[str, int]] = []
        self.dialog_patches = []
        for name in ("showinfo", "showerror", "showwarning"):
            dialog_patch = patch(
                f"vrlab2gif.app.messagebox.{name}",
                side_effect=lambda *args, _kind=name, **kwargs: self.dialogs.append((_kind, threading.get_ident())),
            )
            dialog_patch.start()
            self.dialog_patches.append(dialog_patch)
        self.release_save = threading.Event()
        self.release_save.set()
        # Stub only the external Ansys export; exercise the real GIF encoder,
        # queue, Tk event loop, failure recovery and safe-close behavior.
        self.native_patch = patch("vrlab2gif.app.create_native_gifs", side_effect=self._exported_conversion)
        self.native_patch.start()

    def _exported_conversion(self, source, output, **kwargs):
        return convert_exported_views(self.input_dir, output, kwargs["delay_ms"], kwargs["font_size"],
                                      kwargs["filters"], kwargs["log"], kwargs["progress"], kwargs["cancel_event"])

    def tearDown(self) -> None:
        self.release_save.set()
        self.app._cancel_event.set()
        if self.app._worker is not None:
            self.app._worker.join(timeout=10)
        if self._window_exists():
            self.app._destroy()
        for dialog_patch in reversed(self.dialog_patches):
            dialog_patch.stop()
        self.native_patch.stop()
        self.temporary.cleanup()

    def _window_exists(self) -> bool:
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def _pump_until(self, condition, timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            self.root.update()
            self.assertLess(time.monotonic(), deadline, "Tk/worker did not finish before the deadline")
            time.sleep(0.005)
        self.assertEqual(self.callback_errors, [])

    def _picture(self, index: int) -> Path:
        path = self.input_dir / f"{index}_Image_{index}\N{DEGREE SIGN}_0\N{DEGREE SIGN}.png"
        with Image.new("RGB", (300, 160), ("red", "blue")[index % 2]) as image:
            image.save(path)
        return path

    def test_real_conversion_finishes_and_reenables_the_interface(self) -> None:
        self._picture(0)
        self._picture(1)
        self.app.start_processing()

        self.assertTrue(self.app._processing)
        self.assertEqual(str(self.app.start_button.cget("state")), "disabled")
        self._pump_until(lambda: not self.app._processing)
        self.assertIsNone(self.app._worker)
        self.assertEqual(str(self.app.start_button.cget("state")), "normal")
        self.assertEqual(str(self.app.cancel_button.cget("state")), "disabled")
        self.assertEqual(self.dialogs, [], "Routine completion should be shown inline")
        self.assertIn("生成完成", self.app.status_var.get())
        for name in ("vertical_angle_0.0.gif", "collection_all_angles.gif"):
            with Image.open(self.output_dir / name) as image:
                self.assertEqual(image.n_frames, 2)
        self.assertFalse(any(thread.name == "VRLab2GIF-converter" for thread in threading.enumerate()))

    def test_completed_gifs_export_to_ppt_in_worker_and_reveal_ppt_location(self):
        self.assertTrue(self.app.ppt_button.instate(["disabled"]))
        self._picture(0)
        self._picture(1)
        self.app.start_processing()
        self._pump_until(lambda: not self.app._processing)
        self.assertFalse(self.app.ppt_button.instate(["disabled"]))
        request = PptExportRequest(self.app._completed_gifs, self.directory / "presentations" / "report.pptx", PptOptions())
        self.app.start_ppt_export(request)
        self.assertTrue(self.app._processing)
        self.app.select_page("logs")
        self._pump_until(lambda: not self.app._processing)
        self.assertIn("PPT 导出完成：2 页", self.app.status_var.get())
        with ZipFile(request.output_path) as archive:
            collection = next(p for p in self.app._completed_gifs if p.stem == "collection_all_angles")
            self.assertEqual(archive.read("ppt/media/image1.gif"), collection.read_bytes())
        self.assertEqual(Path(self.app.output_dir_var.get()), self.output_dir)
        with patch("vrlab2gif.app.os.startfile") as open_file:
            self.app.open_output_dir()
        open_file.assert_called_once_with(str(request.output_path.parent.resolve()))
        self.assertEqual(self.dialogs, [])

    def test_native_file_selection_defaults_output_and_runs_backend_off_tk_thread(self) -> None:
        source = self.directory / "official.OptisVR"
        source.write_bytes(b"native fixture")
        self.app.output_dir_var.set("")
        with patch("vrlab2gif.app.filedialog.askopenfilename", return_value=str(source)):
            self.app.ask_input_file()
        self.assertEqual(Path(self.app.output_dir_var.get()), self.directory / "official_GIF")
        threads = []

        def convert(*args, **kwargs):
            threads.append(threading.get_ident())
            kwargs["log"]("VRLab 已导出 3 个视角。")
            kwargs["progress"](3, 3, "collection_all_views.gif")
            return ConversionResult(3, 0, 0, 3, (self.output_dir / "collection_all_views.gif",), 300)

        with patch("vrlab2gif.app.create_native_gifs", side_effect=convert) as native:
            self.app.start_processing()
            self.assertEqual(str(self.app.input_browse_button.cget("state")), "disabled")
            self._pump_until(lambda: not self.app._processing)
        native.assert_called_once()
        self.assertNotEqual(threads, [threading.get_ident()])
        self.assertEqual(str(self.app.input_browse_button.cget("state")), "normal")
        self.assertIn("3 张图片，1 个 GIF", self.app.status_var.get())
        self.assertEqual(self.dialogs, [])

    def test_worker_error_returns_to_ready_and_a_second_run_can_succeed(self) -> None:
        path = self.input_dir / "0_Image_0\N{DEGREE SIGN}_0\N{DEGREE SIGN}.png"
        path.write_bytes(b"not an image")
        self.app.start_processing()
        self._pump_until(lambda: not self.app._processing)
        self.assertIsNone(self.app._worker)
        self.assertEqual([kind for kind, thread in self.dialogs], ["showerror"])
        self.assertEqual(self.app.page_var.get(), "logs")

        self._picture(0)
        self.app.start_processing()
        self._pump_until(lambda: not self.app._processing)

        self.assertIsNone(self.app._worker)
        self.assertEqual([kind for kind, thread in self.dialogs], ["showerror"])
        self.assertTrue((self.output_dir / "collection_all_angles.gif").is_file())
        self.assertTrue(all(thread == threading.get_ident() for kind, thread in self.dialogs))

    def test_closing_during_gif_save_waits_for_worker_and_preserves_old_result(self) -> None:
        self._picture(0)
        self.output_dir.mkdir()
        old_result = self.output_dir / "vertical_angle_0.0.gif"
        old_bytes = b"previous completed animation"
        old_result.write_bytes(old_bytes)
        save_entered = threading.Event()
        self.release_save.clear()
        original_save = Image.Image.save

        def blocked_save(image: Image.Image, path: str | Path, *args: object, **kwargs: object) -> None:
            save_entered.set()
            if not self.release_save.wait(timeout=10):
                raise TimeoutError("Test did not release the simulated save")
            original_save(image, path, *args, **kwargs)

        with patch.object(Image.Image, "save", blocked_save):
            try:
                self.app.start_processing()
                self._pump_until(save_entered.is_set)
                worker = self.app._worker
                self.assertIsNotNone(worker)
                self.assertFalse(worker.daemon)

                self.app.theme_switch.invoke()
                self.app.select_page("logs")
                self.root.update()
                self.assertTrue(self.app.logs_card.winfo_ismapped())
                self.assertTrue(all(not button.instate(["disabled"]) for button in self.app.page_buttons.values()))
                self.assertEqual(self.app.appearance.mode, "light")
                self.assertEqual(str(self.app.input_entry.cget("state")), "disabled")
                self.assertEqual(str(self.app.start_button.cget("state")), "disabled")
                self.assertIs(self.app._worker, worker)
                self.assertTrue(worker.is_alive())

                self.app.on_close()
                self.root.update()

                self.assertTrue(self._window_exists(), "Window must remain alive while writing finishes")
                self.assertTrue(worker.is_alive())
                self.release_save.set()
                self._pump_until(lambda: not self._window_exists())
                self.assertFalse(worker.is_alive())
                self.assertIsNone(self.app._worker)
            finally:
                self.release_save.set()

        self.assertEqual(self.dialogs, [], "Closing should finish without confirmation dialogs")
        self.assertEqual(old_result.read_bytes(), old_bytes)
        self.assertEqual({path.name for path in self.output_dir.iterdir()}, {old_result.name})
        self.assertFalse(any(thread.name == "VRLab2GIF-converter" for thread in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
