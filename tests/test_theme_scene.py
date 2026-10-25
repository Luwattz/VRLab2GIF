"""Lifecycle/input regressions for Windows' composited theme body."""
import ctypes
import sys
import unittest
from unittest.mock import patch

from tkinterdnd2 import TkinterDnD
from vrlab2gif.app import GifCreatorApp
from vrlab2gif.appearance import PALETTES, enable_dpi_awareness


@unittest.skipUnless(sys.platform == "win32", "Native Windows presentation")
class ThemeSceneTests(unittest.TestCase):
    def setUp(self):
        enable_dpi_awareness()
        self.root = TkinterDnD.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda kind, error, tb: self.errors.append(error)
        self.app = GifCreatorApp(self.root)
        self.root.update()
        self.fade = self.app.appearance.transition
        self.fade.motion_enabled = self.app.theme_switch.motion_enabled = True

    def tearDown(self):
        self.app.on_close()
        self.assertEqual(self.errors, [])

    def start(self, target="light"):
        self.app.theme_switch.select(target)
        self.fade.cancel()
        self.assertTrue(self.fade.scene.active, self.fade.scene.last_error)

    def test_owned_layers_pass_input_without_changing_root_style_or_focus(self):
        import win32gui
        app = self.app
        hwnd = int(self.root.wm_frame(), 0)
        original_style = win32gui.GetWindowLong(hwnd, -20)
        app.theme_switch.focus_force(); self.root.update()
        focus = self.root.focus_get()
        point = (app.start_button.winfo_rootx()+10, app.start_button.winfo_rooty()+10)
        baseline = win32gui.GetAncestor(win32gui.WindowFromPoint(point), 2)
        self.start()
        self.assertEqual(self.root.focus_get(), focus)
        self.assertEqual(win32gui.GetWindowLong(hwnd, -20), original_style)
        for layer in (self.fade.scene.overlay, self.fade.scene.base):
            self.assertEqual(win32gui.GetWindow(layer.hwnd, 4), hwnd)
            self.assertEqual(win32gui.GetWindowLong(layer.hwnd, -20) & 0x08000020, 0x08000020)
        hit = win32gui.WindowFromPoint(point)
        self.assertEqual(win32gui.GetAncestor(hit, 2), baseline)

    def test_body_input_finishes_presentation_before_native_entry_handles_key(self):
        app = self.app
        app.input_file_var.set("original")
        app.input_entry.focus_force(); self.root.update()
        self.start()
        self.fade.render(.4)
        app.input_entry.event_generate("<KeyPress-a>")
        self.root.update()
        self.assertFalse(self.fade.scene.active)
        self.assertIn("a", app.input_file_var.get())
        self.assertEqual(app.appearance.colors, PALETTES["light"])
        self.assertIsNone(self.fade.timer_id)

    def test_switching_pages_finishes_scene_and_keeps_filters_and_log(self):
        self.app.h_min_var.set("-30")
        self.app.log_message("retained")
        self.start()
        self.app.navigation.select("logs")
        self.root.update()
        self.assertFalse(self.fade.scene.active)
        self.assertEqual(self.app.page_var.get(), "logs")
        self.assertEqual(self.app.h_min_var.get(), "-30")
        self.assertIn("retained", self.app.log_text.get("1.0", "end"))

    def test_resize_and_unmap_finish_and_release_native_surfaces(self):
        import win32gui
        self.start()
        handles = [self.fade.scene.overlay.hwnd, self.fade.scene.base.hwnd]
        self.root.geometry(f"{self.root.winfo_width()-10}x{self.root.winfo_height()}")
        self.root.update()
        self.assertFalse(self.fade.scene.active)
        self.assertFalse(any(win32gui.IsWindow(hwnd) for hwnd in handles))
        self.start("dark")
        self.root.withdraw(); self.root.update()
        self.assertFalse(self.fade.scene.active)

    def test_capture_failure_falls_back_to_complete_theme_without_layer_or_timer(self):
        with patch("vrlab2gif.theme_scene.capture_client", side_effect=OSError("capture unavailable")):
            self.app.theme_switch.select("light")
        self.assertEqual(self.app.appearance.colors, PALETTES["light"])
        self.assertFalse(self.fade.scene.active)
        self.assertIsNone(self.fade.scene.overlay)
        self.assertIsNone(self.fade.scene.base)
        self.assertIsNone(self.fade.timer_id)
        self.assertIn("capture unavailable", self.fade.scene.last_error)

    def test_rapid_reversals_reuse_two_surfaces_and_free_them_at_endpoint(self):
        import win32gui
        self.start()
        handles = self.fade.scene.overlay.hwnd, self.fade.scene.base.hwnd
        self.fade.render(.55); self.fade.velocity = .3
        for target in ("dark", "light", "dark"):
            self.app.theme_switch.select(target)
            self.fade.cancel()
            self.assertEqual((self.fade.scene.overlay.hwnd, self.fade.scene.base.hwnd), handles)
            self.assertEqual(self.fade.alpha, .55)
            self.assertEqual(self.fade.velocity, .3)
        self.fade.finish()
        self.assertFalse(any(win32gui.IsWindow(hwnd) for hwnd in handles))
        self.assertEqual(self.app.appearance.colors, PALETTES["dark"])

    def test_compositor_failure_finishes_and_cleans_up(self):
        self.start()
        with patch.object(self.fade.scene.overlay, "opacity", side_effect=OSError("display reset")):
            self.fade.render(.4)
        self.assertFalse(self.fade.scene.active)
        self.assertIsNone(self.fade.scene.overlay)
        self.assertIsNone(self.fade.scene.base)
        self.assertEqual(self.app.appearance.colors, PALETTES["light"])
        self.assertIn("display reset", self.fade.scene.last_error)

    def test_native_handles_do_not_accumulate_over_repeated_transitions(self):
        from ctypes import wintypes
        user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        user.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        process = kernel.GetCurrentProcess()
        # Warm up font/brush resources before measuring retained handles.
        self.start(); self.fade.finish()
        counts = [user.GetGuiResources(process, kind) for kind in (0, 1)]
        for n in range(10):
            self.start("dark" if n % 2 == 0 else "light")
            self.fade.finish()
        after = [user.GetGuiResources(process, kind) for kind in (0, 1)]
        self.assertLessEqual(after[0]-counts[0], 2, (counts, after))
        self.assertLessEqual(after[1]-counts[1], 2, (counts, after))

    def test_destroy_releases_surfaces_and_animation_timer_resolution(self):
        import win32gui
        self.start()
        handles = self.fade.scene.overlay.hwnd, self.fade.scene.base.hwnd
        self.app.navigation.select("logs")
        self.app.theme_switch.select("dark")
        self.app.on_close()
        self.assertFalse(any(win32gui.IsWindow(hwnd) for hwnd in handles))
        self.assertFalse(any(control.timing.precise for control in
                             (self.fade, self.app.navigation, self.app.theme_switch)))


if __name__ == "__main__":
    unittest.main()
