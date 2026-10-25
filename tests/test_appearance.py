"""Check usability across window sizes and the custom native control skins."""

from __future__ import annotations

import tkinter as tk
from tkinterdnd2 import TkinterDnD
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vrlab2gif.app import GifCreatorApp
from vrlab2gif.appearance import enable_dpi_awareness
from vrlab2gif import __version__


class AppearanceUsabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        enable_dpi_awareness()
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.app: GifCreatorApp | None = None
        self.callback_errors: list[BaseException] = []
        self.root.report_callback_exception = lambda kind, error, traceback: self.callback_errors.append(error)

    def tearDown(self) -> None:
        if self.app is not None:
            self.app.on_close()
        else:
            self.root.destroy()
        self.assertEqual(self.callback_errors, [])

    def _show(self, *, scaling: float = 4 / 3, compact: bool = False) -> GifCreatorApp:
        self.root.tk.call("tk", "scaling", scaling)
        self.app = GifCreatorApp(self.root)
        if compact:
            minimum_width, minimum_height = self.root.minsize()
            self.root.geometry(f"{minimum_width}x{minimum_height}+20+20")
        self.root.deiconify()
        self.root.update()
        return self.app

    def _assert_actions_are_visible(self, app: GifCreatorApp) -> None:
        top = self.root.winfo_rooty()
        bottom = top + self.root.winfo_height()
        buttons = [app.start_button, app.open_output_button, app.ppt_button, *app.page_buttons.values()]
        if app.cancel_button.winfo_ismapped():
            buttons.append(app.cancel_button)
        for button in buttons:
            self.assertGreaterEqual(button.winfo_rooty(), top)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
            self.assertGreater(button.winfo_width(), 20)

    def test_default_window_is_compact_and_shows_common_controls(self) -> None:
        app = self._show()
        self.assertIn(__version__, self.root.title())
        self.assertIn(__version__, app.version_label.cget("text"))
        p = app.appearance.px
        self.assertLessEqual(self.root.winfo_width(), p(700))
        self.assertLessEqual(self.root.winfo_height(), p(450))
        self.assertLessEqual(self.root.winfo_width(), app.work_area[2] * 0.60 + 1)
        self.assertLessEqual(self.root.winfo_height(), app.work_area[3] * 0.68 + 1)
        self._assert_actions_are_visible(app)
        self.assertFalse(app.scroll_area._scrolling)
        self.assertFalse(app.filters_frame.winfo_viewable())
        self.assertFalse(app.logs_card.winfo_viewable())
        self.assertFalse(app.cancel_button.winfo_ismapped())
        viewport_bottom = app.scroll_area.canvas.winfo_rooty() + app.scroll_area.canvas.winfo_height()
        for entry in (app.input_entry, app.output_entry, app.delay_entry, app.font_size_entry):
            self.assertGreaterEqual(entry.winfo_rooty(), app.scroll_area.canvas.winfo_rooty())
            self.assertLessEqual(entry.winfo_rooty() + entry.winfo_height(), viewport_bottom)
            self.assertGreaterEqual(entry.winfo_rootx(), entry.master.winfo_rootx())
            self.assertLessEqual(
                entry.winfo_rootx() + entry.winfo_width(),
                entry.master.winfo_rootx() + entry.master.winfo_width(),
            )

    def test_large_text_compact_window_keeps_actions_and_focused_fields_visible(self) -> None:
        app = self._show(scaling=8 / 3, compact=True)
        app.select_page("filters")
        self.root.update()
        self.assertTrue(app.scroll_area._scrolling)
        self.assertTrue(app._parameters_stacked)
        self._assert_actions_are_visible(app)
        app.select_page("logs")
        app.log_text.focus_force()
        self.root.update()
        self.assertTrue(app.logs_card.winfo_viewable())
        app.select_page("settings")
        app.input_entry.focus_force()
        self.root.update()
        canvas = app.scroll_area.canvas
        self.assertGreaterEqual(app.input_entry.winfo_rooty(), canvas.winfo_rooty())
        self.assertLessEqual(
            app.input_entry.winfo_rooty() + app.input_entry.winfo_height(),
            canvas.winfo_rooty() + canvas.winfo_height(),
        )
        app._set_processing(True)
        self.root.update()
        self.assertTrue(app.cancel_button.winfo_ismapped())
        self._assert_actions_are_visible(app)
        app._set_processing(False)

    def test_pages_are_exclusive_and_preserve_filters_logs_and_size(self) -> None:
        app = self._show()
        original_size = (self.root.winfo_width(), self.root.winfo_height())
        app.h_min_var.set("-30")
        app.h_max_var.set("30")
        app.page_buttons["filters"].invoke()
        self.root.update()
        self.assertEqual(app.page_var.get(), "filters")
        self.assertFalse(app.settings_card.winfo_viewable())
        self.assertFalse(app.logs_card.winfo_viewable())
        viewport = app.scroll_area.canvas
        self.assertGreaterEqual(app.filters_frame.winfo_rooty(), viewport.winfo_rooty())
        self.assertLessEqual(
            app.filters_frame.winfo_rooty() + app.filters_frame.winfo_height(),
            viewport.winfo_rooty() + viewport.winfo_height(),
        )
        app.log_message("可展开查看的记录")
        app.page_buttons["logs"].invoke()
        self.root.update()
        self.assertEqual(app.page_var.get(), "logs")
        self.assertFalse(app.filters_frame.winfo_viewable())
        self.assertIn("可展开查看的记录", app.log_text.get("1.0", "end"))
        self.assertGreaterEqual(app.logs_card.winfo_rooty(), viewport.winfo_rooty())
        self._assert_actions_are_visible(app)
        app.page_buttons["settings"].invoke()
        self.root.update()
        self.assertEqual(app.h_min_var.get(), "-30")
        self.assertIn("H 已限制", app.filter_summary_var.get())
        self.assertIn("已设", app.filter_tab_var.get())
        self.assertFalse(app.filters_frame.winfo_viewable())
        self.assertFalse(app.logs_card.winfo_viewable())
        self.assertTrue(app.settings_card.winfo_viewable())
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), original_size)
        app.clear_filters()
        self.assertEqual(app.filter_summary_var.get(), "不限角度")
        self.assertEqual(app.filter_tab_var.get(), "角度筛选")
        app.h_min_var.set("30")
        app.h_max_var.set("-30")
        self.assertIn("检查", app.filter_tab_var.get())

    def test_keyboard_cycles_pages_and_moves_focus_out_of_hidden_content(self) -> None:
        app = self._show()
        app.input_entry.focus_force()
        self.root.update()
        app.input_entry.event_generate("<Control-Tab>")
        self.root.update()
        self.assertEqual(app.page_var.get(), "filters")
        self.assertEqual(self.root.focus_get(), app.page_buttons["filters"])
        app._cycle_page(1)
        self.root.update()
        self.assertEqual(app.page_var.get(), "logs")
        app._cycle_page(1)
        self.assertEqual(app.page_var.get(), "settings")
        self.root.event_generate("<Control-Shift-Tab>")
        self.root.update()
        self.assertEqual(app.page_var.get(), "logs")

    def test_default_output_follows_input_and_preserves_a_custom_destination(self) -> None:
        app = self._show()
        first = Path.cwd() / "input-a.OptisVR"
        second = Path.cwd() / "input-b.speos360"
        custom = Path.cwd() / "my-gifs"
        app.input_file_var.set(str(first))
        self.assertEqual(Path(app.output_dir_var.get()), first.parent / "input-a_GIF")
        app.input_file_var.set(str(second))
        self.assertEqual(Path(app.output_dir_var.get()), second.parent / "input-b_GIF")
        app.output_dir_var.set(str(custom))
        app.input_file_var.set(str(first))
        self.assertEqual(Path(app.output_dir_var.get()), custom)

    def test_skinned_entries_and_buttons_keep_native_keyboard_behavior(self) -> None:
        app = self._show()
        app.input_entry.focus_force()
        self.root.update()
        app.input_entry.event_generate("<KeyPress-a>")
        app.input_entry.event_generate("<KeyRelease-a>")
        self.root.update()
        self.assertEqual(app.input_file_var.get(), "a")

        calls: list[str] = []
        app.start_button.configure(command=lambda: calls.append("start"))
        app.start_button.focus_force()
        self.root.update()
        for event in ("<KeyPress-space>", "<KeyRelease-space>"):
            app.start_button.event_generate(event)
            self.root.update()
        self.assertEqual(calls, ["start"])
        app.start_button.configure(state="disabled")
        app.start_button.invoke()
        self.assertEqual(calls, ["start"])

    def test_dark_default_and_switch_preserve_data_feedback_and_window_size(self) -> None:
        app = self._show()
        self.assertEqual(app.appearance.mode, "dark")
        self.assertTrue(app.dark_mode_var.get())
        self.assertEqual(app.theme_label_var.get(), "Dark")
        self.assertGreater(app.theme_switch.winfo_rootx(), app.input_entry.winfo_rootx())
        size = (self.root.winfo_width(), self.root.winfo_height())
        app.input_file_var.set(str(Path.cwd() / "input-for-theme-test.OptisVR"))
        app.delay_var.set("420")
        app.h_min_var.set("30")
        app.h_max_var.set("-30")
        app.status_var.set("需要检查筛选范围")
        app._set_status_tone("error")
        app.log_message("[成功] 保留这条日志")
        app.log_message("错误：保留错误标注")
        app.progress_bar.configure(maximum=100)
        app.progress_var.set(37)
        snapshot = (app.input_file_var.get(), app.output_dir_var.get(), app.delay_var.get(), app.h_min_var.get(), app.log_text.get("1.0", "end"))

        for expected in ("light", "dark"):
            app.theme_switch.invoke()
            self.root.update()
            palette = app.appearance.colors
            self.assertEqual(app.appearance.mode, expected)
            self.assertEqual(app.theme_label_var.get(), expected.title())
            self.assertEqual(app.dark_mode_var.get(), expected == "dark")
            self.assertEqual(self.root.cget("background"), palette.background)
            self.assertEqual(app.settings_card.canvas.cget("background"), palette.background)
            self.assertEqual(app.scroll_area.canvas.cget("background"), palette.background)
            self.assertEqual(app.log_text.cget("background"), palette.surface)
            self.assertEqual(str(app.status_label.cget("foreground")), palette.error)
            self.assertEqual(str(app.filter_summary_label.cget("foreground")), palette.error)
            self.assertEqual(app.log_text.tag_cget("error", "foreground"), palette.error)
            self.assertEqual(app.progress_var.get(), 37)
            self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), size)
            self.assertEqual((app.input_file_var.get(), app.output_dir_var.get(), app.delay_var.get(), app.h_min_var.get(), app.log_text.get("1.0", "end")), snapshot)

        # A repeated switch must reuse the two skins rather than leak Tk images.
        image_count = len(app.appearance.images)
        for _ in range(8):
            app.theme_switch.invoke()
        self.root.update()
        self.assertEqual(len(app.appearance.images), image_count)
        self._assert_actions_are_visible(app)

    def test_theme_switch_works_from_the_keyboard(self) -> None:
        app = self._show()
        app.theme_switch.focus_force()
        self.root.update()
        for event in ("<KeyPress-space>", "<KeyRelease-space>"):
            app.theme_switch.event_generate(event)
            self.root.update()
        self.assertEqual(app.appearance.mode, "light")
        self.assertFalse(app.dark_mode_var.get())
        self.assertIsNone(app._worker)
        starts = []
        self.root.bind("<Control-Return>", lambda event: starts.append("start"))
        app.theme_switch.event_generate("<Control-KeyPress-Return>")
        self.root.update()
        self.assertEqual(starts, ["start"])
        self.assertEqual(app.appearance.mode, "light", "Ctrl+Enter must not change the theme")

    def test_theme_segments_support_direct_choice_and_cancelled_press(self) -> None:
        app = self._show()
        switch = app.theme_switch
        switch.motion_enabled = False
        self.assertEqual({switch.itemcget(label, "text") for label in switch.labels.values()}, {"Dark", "Light"})
        switch._press(SimpleNamespace(x=switch.width - 8, y=8))
        self.assertEqual(switch.target, 1)
        self.assertEqual(app.appearance.mode, "dark", "Press feedback must not commit the theme")
        switch._release(SimpleNamespace(x=-8, y=8))
        self.assertEqual(switch.position, 0)
        self.assertEqual(app.appearance.mode, "dark")
        switch._press(SimpleNamespace(x=switch.width - 8, y=8))
        switch._release(SimpleNamespace(x=switch.width - 8, y=8))
        self.assertEqual(app.appearance.mode, "light")
        self.assertEqual(switch.position, 1)
        switch._key("dark")
        self.assertEqual(app.appearance.mode, "dark")
        self.assertEqual(switch.position, 0)
        self.assertIsNone(switch.timer_id)

    def test_theme_selection_animation_keeps_velocity_on_reversal_and_reuses_assets(self) -> None:
        app = self._show()
        switch = app.theme_switch
        switch.motion_enabled = True
        switch.select("light")
        self.assertIsNotNone(switch.timer_id)
        switch.after_cancel(switch.timer_id)
        switch.timer_id = None
        with patch("vrlab2gif.theme_switch.time.perf_counter", return_value=switch.last_time + .04):
            switch._tick()
        before = switch.position, switch.velocity
        self.assertGreater(before[0], 0)
        self.assertLess(before[0], 1)
        self.assertGreater(before[1], 0)
        switch.select("dark")
        self.assertEqual((switch.position, switch.velocity), before)
        self.assertEqual(switch.target, 0)
        assets = dict(switch.assets)
        images = {str(image) for palette in switch.assets.values() for image in palette}
        for mode in ("light", "dark", "light", "dark"):
            switch.select(mode, animate=False)
        self.assertEqual(switch.assets, assets)
        self.assertEqual({str(image) for palette in switch.assets.values() for image in palette}, images)
        self.assertTrue(images.issubset(set(self.root.tk.call("image", "names"))))
        self.assertEqual(switch.position, 0)
        self.assertIsNone(switch.timer_id)

    def test_reduced_motion_and_destroy_remove_pending_theme_callbacks(self) -> None:
        with patch("vrlab2gif.theme_switch.system_motion_enabled", return_value=False):
            app = self._show()
        switch = app.theme_switch
        switch.select("light")
        self.assertEqual(switch.position, 1)
        self.assertIsNone(switch.timer_id)
        switch.motion_enabled = True
        switch.select("dark")
        timer_id = switch.timer_id
        self.assertIsNotNone(timer_id)
        switch.destroy()
        self.assertIsNone(switch.timer_id)
        self.assertNotIn(timer_id, self.root.tk.call("after", "info"))


if __name__ == "__main__":
    unittest.main()
