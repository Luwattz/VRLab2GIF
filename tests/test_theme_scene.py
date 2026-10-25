"""Lifecycle/input regressions for Windows' composited theme body."""
import ctypes
import sys
import time
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

    def test_child_layers_pass_input_without_changing_root_style_or_focus(self):
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
            self.assertEqual(win32gui.GetParent(layer.hwnd), hwnd)
            self.assertEqual(win32gui.GetWindowLong(layer.hwnd, -16) & 0xc0000000, 0x40000000)
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

    def test_preparation_and_fade_layers_cover_bottom_inside_native_frame(self):
        import win32gui
        from vrlab2gif.theme_scene import _LayerFrame

        original_draw = _LayerFrame.draw
        rectangles = []

        def draw(layer, image, position):
            original_draw(layer, image, position)
            rectangles.append(win32gui.GetWindowRect(layer.hwnd))

        for compact in (False, True):
            if compact:
                width, height = self.root.minsize()
                self.root.geometry(f"{width}x{height}")
                self.root.update()
            client_bottom = self.root.winfo_rooty() + self.root.winfo_height()
            for mode in ("light", "dark"):
                with self.subTest(compact=compact, target=mode):
                    rectangles.clear()
                    with patch.object(_LayerFrame, "draw", new=draw):
                        self.start(mode)
                    # Include the initial shield used during target capture,
                    # not only the two final body layers.
                    self.assertEqual(len(rectangles), 3)
                    self.assertTrue(all(rect[3] == client_bottom for rect in rectangles), rectangles)
                    for amount in (.2, .5, .8):
                        self.fade.render(amount)
                        for layer in (self.fade.scene.base, self.fade.scene.overlay):
                            self.assertEqual(win32gui.GetWindowRect(layer.hwnd)[3], client_bottom)
                            self.assertEqual(win32gui.GetParent(layer.hwnd), int(self.root.wm_frame(), 0))
                    self.fade.finish()
                    self.root.update()

    def test_captured_destination_contains_target_body_colors_behind_layers(self):
        from vrlab2gif.theme_scene import capture_client
        captures = []

        def capture(root):
            picture = capture_client(root)
            captures.append(picture)
            return picture

        for mode, source_mode in (("light", "dark"), ("dark", "light")):
            captures.clear()
            with patch("vrlab2gif.theme_scene.capture_client", side_effect=capture):
                self.start(mode)
            self.assertEqual(len(captures), 2)
            # The side margin belongs to the body but is clear of controls.
            point = (0, self.root.winfo_height() // 2)
            for picture, expected in zip(captures, (source_mode, mode)):
                background = PALETTES[expected].background
                color = tuple(int(background[i:i+2], 16) for i in (1, 3, 5))
                self.assertEqual(picture.getpixel(point), color)
                card = self.app.settings_card
                surface_point = (card.winfo_rootx()-self.root.winfo_rootx()+card.winfo_width()//2,
                                 card.winfo_rooty()-self.root.winfo_rooty()+self.app.appearance.px(4))
                surface = PALETTES[expected].surface
                self.assertEqual(picture.getpixel(surface_point),
                                 tuple(int(surface[i:i+2], 16) for i in (1, 3, 5)))
            self.fade.finish()
            self.root.update()

    def test_title_and_body_share_one_frame_with_live_selector_cutouts(self):
        import win32gui
        self.start()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        bottom = y + self.root.winfo_height()
        for layer in (self.fade.scene.base, self.fade.scene.overlay):
            self.assertEqual(win32gui.GetWindowRect(layer.hwnd),
                             (x, y, x+self.root.winfo_width(), bottom))
            pixels = ctypes.string_at(layer.bits, layer.size[0]*layer.size[1]*4)
            for control in (self.app.theme_switch, self.app.navigation):
                left, top = control.winfo_rootx()-x, control.winfo_rooty()-y
                for dx, dy in ((0, 0), (control.winfo_width()//2, control.winfo_height()//2),
                               (control.winfo_width()-1, control.winfo_height()-1)):
                    offset = ((top+dy)*layer.size[0]+left+dx)*4
                    self.assertEqual(pixels[offset:offset+4], b"\0\0\0\0")
            # Outside those cutouts, title and body backgrounds are opaque
            # pixels in the same native bitmap, updated by one opacity call.
            for row in (self.app.heading.winfo_rooty()-y, self.root.winfo_height()//2):
                self.assertEqual(pixels[(row*layer.size[0])*4+3], 255)

    def test_displayed_background_is_uniform_before_tk_idle_paint(self):
        from PIL import ImageGrab
        self.root.attributes("-topmost", True)
        self.root.update()
        p = self.app.appearance.px
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        width, height = self.root.winfo_width(), self.root.winfo_height()
        points = ((p(8), self.app.heading.winfo_rooty()-y+p(4)),
                  (p(8), height//2), (width//2, height-2))
        for mode in ("light", "dark"):
            self.start(mode)
            self.root.update_idletasks()
            for amount in (.2, .5, .8):
                self.fade.render(amount)
                # Deliberately leave Tk's header paint queued. DWM must still
                # display matching title/body backgrounds in this frame.
                ctypes.windll.dwmapi.DwmFlush()
                picture = ImageGrab.grab(bbox=(x, y, x+width, y+height),
                                         include_layered_windows=True)
                colors = [picture.getpixel(point) for point in points]
                self.assertLessEqual(max(abs(a-b) for color in colors[1:]
                                         for a, b in zip(color, colors[0])), 2, colors)
                self.root.update_idletasks()
            self.fade.finish()
            self.root.update()

    def test_target_preparation_preserves_source_bottom_strip_and_native_corners(self):
        from PIL import ImageChops, ImageGrab
        import win32gui
        from vrlab2gif.theme_scene import capture_client

        self.root.attributes("-topmost", True)
        self.root.update()
        hwnd = int(self.root.wm_frame(), 0)
        bounds = win32gui.GetWindowRect(hwnd)
        # A stable backing surface makes the pixels outside native rounded
        # corners deterministic even if other applications repaint behind us.
        backdrop = win32gui.CreateWindowEx(0x08000080, "STATIC", "", 0x90000004,
            bounds[0]-20, bounds[1]-20, bounds[2]-bounds[0]+40, bounds[3]-bounds[1]+40,
            0, 0, 0, None)

        def screen():
            ctypes.windll.dwmapi.DwmFlush()
            return ImageGrab.grab(bbox=bounds, include_layered_windows=True)

        def settled_screen():
            # Windows animates a new window's border/shadow independently of
            # our theme. Wait for that native decoration to settle before
            # comparing its silhouette with the preparation shield.
            previous = screen()
            size = self.app.appearance.px(20)
            boxes = [(left, previous.height-size, left+size, previous.height)
                     for left in (0, previous.width-size)]
            stable = 0
            deadline = time.monotonic()+2
            while time.monotonic() < deadline:
                picture = screen()
                unchanged = all(ImageChops.difference(previous.crop(box), picture.crop(box)).getbbox() is None
                                for box in boxes)
                stable = stable+1 if unchanged else 0
                if stable >= 3:
                    return picture
                previous = picture
            self.fail("Native border/shadow did not settle before corner comparison")

        try:
            self.root.update()
            for target, source in (("light", "dark"), ("dark", "light")):
                before = settled_screen()
                during = []
                count = 0

                def capture(root):
                    nonlocal count
                    count += 1
                    image = capture_client(root)
                    if count == 2:
                        # The backing controls have already been painted in
                        # the target theme, before the fade has even started.
                        during.append(screen())
                    return image

                with patch("vrlab2gif.theme_scene.capture_client", side_effect=capture):
                    self.start(target)
                self.assertEqual(len(during), 1)
                image = during[0]
                x = self.root.winfo_rootx()-bounds[0]
                y = self.root.winfo_rooty()-bounds[1]
                color = PALETTES[source].background
                rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
                for distance in (1, 2, self.app.appearance.px(6)):
                    point = (x+self.root.winfo_width()//2, y+self.root.winfo_height()-distance)
                    self.assertEqual(image.getpixel(point), rgb)
                size = self.app.appearance.px(20)
                for left in (0, image.width-size):
                    box = (left, image.height-size, left+size, image.height)
                    difference = ImageChops.difference(before.crop(box), image.crop(box))
                    self.assertLessEqual(max(channel[1] for channel in difference.getextrema()), 2)
                self.fade.finish()
                self.root.update()
        finally:
            win32gui.DestroyWindow(backdrop)

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
