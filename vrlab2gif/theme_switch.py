"""Dark / Light segmented selector, matching ACT-WBEX-Updater's interaction."""
from __future__ import annotations

import math
import sys
import time
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageDraw

from .appearance import AppleAppearance, PALETTES
from .palette_image import PaletteImage


def system_motion_enabled() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                return bool(enabled.value)
        except (AttributeError, OSError):
            pass
    return True


class ThemeSwitch(tk.Canvas):
    """Fixed labels and an interruptible selection pill; no changes to app data."""

    def __init__(self, parent, appearance: AppleAppearance, variable: tk.BooleanVar,
                 command: Callable[..., None]) -> None:
        p = appearance.px
        self.width, self.height, self.inset = p(132), p(34), p(3)
        self.segment_width = (self.width - 2 * self.inset) / 2
        super().__init__(parent, width=self.width, height=self.height, highlightthickness=0,
                         borderwidth=0, takefocus=True, cursor="hand2")
        self.appearance, self.variable, self.command = appearance, variable, command
        self.motion_enabled = system_motion_enabled()
        self.position = self.target = float(not variable.get())
        self.velocity, self.last_time = 0.0, time.perf_counter()
        self.timer_id = None
        self.pressed_mode = None
        self.focused = False
        self._animate = True
        self.assets = {}
        self._sources = {}
        self.track = self.create_image(0, 0, anchor="nw")
        self.thumb = self.create_image(self.inset, self.inset, anchor="nw")
        self.labels = {
            mode: self.create_text(self.inset + self.segment_width * (index + 0.5),
                                   self.height / 2, text=mode.title(), font=appearance.hint_font)
            for index, mode in enumerate(("dark", "light"))
        }
        for mode, c in PALETTES.items():
            track = "#2a2a2f" if mode == "dark" else "#e8e8ed"
            selected = "#50505b" if mode == "dark" else "#ffffff"
            self._sources[mode] = (
                self._surface(self.width, self.height, p(11), track, c.border, background=c.background),
                self._surface(self.width, self.height, p(11), track, c.accent, background=c.background),
                self._surface(round(self.segment_width), self.height-2*self.inset,
                              p(8), selected, selected, transparent=True),
            )
        self.assets["_fade"] = tuple(PaletteImage(self, dark, light)
                                     for dark, light in zip(self._sources["dark"], self._sources["light"]))
        self._refresh()
        appearance.subscribe(self._refresh)
        self.trace_id = variable.trace_add("write", self._value_changed)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda event: self._focus(True))
        self.bind("<FocusOut>", lambda event: self._focus(False))
        for key, mode in (("Left", "dark"), ("Home", "dark"), ("Right", "light"), ("End", "light")):
            self.bind(f"<{key}>", lambda event, value=mode: self._key(value))
        self.bind("<space>", lambda event: self._key())
        self.bind("<Return>", lambda event: self._key())
        # Let the app's Ctrl+Enter shortcut propagate instead of toggling theme.
        self.bind("<Control-Return>", lambda event: None)
        self.bind("<Destroy>", self._destroy)

    def _surface(self, width, height, radius, fill, border, *, transparent=False, background=None):
        factor = 3
        image = Image.new("RGBA", (width * factor, height * factor),
                          (0, 0, 0, 0) if transparent else background)
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, width * factor - 1, height * factor - 1), radius=radius * factor,
            fill=fill, outline=border, width=factor,
        )
        return image.resize((width, height), Image.Resampling.LANCZOS)

    def _refresh(self):
        c = self.appearance.colors
        self.configure(background=c.background)
        for photo, dark, light in zip(self.assets["_fade"], self._sources["dark"], self._sources["light"]):
            photo.render(self.appearance.blend)
        self.itemconfigure(self.thumb, image=self.assets["_fade"][2])
        self._draw_state()
        self._draw_position()

    def _draw_state(self):
        c = self.appearance.colors
        self.itemconfigure(self.track, image=self.assets["_fade"][int(self.focused)])
        selected = self.pressed_mode or ("dark" if self.variable.get() else "light")
        for mode, label in self.labels.items():
            self.itemconfigure(label, fill=c.text if mode == selected else c.secondary)

    def _draw_position(self):
        self.coords(self.thumb, self.inset + self.position * self.segment_width, self.inset)

    def _focus(self, focused):
        self.focused = focused
        self._draw_state()

    def _press(self, event):
        self.focus_set()
        self.pressed_mode = "dark" if event.x < self.width / 2 else "light"
        self._retarget(float(self.pressed_mode == "light"))
        self._draw_state()
        return "break"

    def _release(self, event):
        if self.pressed_mode is not None:
            mode, self.pressed_mode = self.pressed_mode, None
            if 0 <= event.x < self.width and 0 <= event.y < self.height:
                self.select(mode)
            else:
                self._retarget(float(not self.variable.get()))
            self._draw_state()
        return "break"

    def _key(self, mode=None):
        self.select(mode or ("light" if self.variable.get() else "dark"), animate=False)
        return "break"

    def invoke(self):
        self.select("light" if self.variable.get() else "dark")

    def select(self, mode: str, animate=True):
        if mode not in ("dark", "light"):
            raise ValueError(f"Unknown appearance: {mode}")
        self._animate = animate
        try:
            if self.variable.get() != (mode == "dark"):
                self.variable.set(mode == "dark")
                self.command(animate=animate and self.motion_enabled)
            else:
                self._retarget(float(mode == "light"), animate)
        finally:
            self._animate = True

    def _value_changed(self, *unused):
        self._retarget(float(not self.variable.get()), self._animate)
        self._draw_state()

    def _retarget(self, target, animate=True):
        self.target, self.last_time = target, time.perf_counter()
        if not self.motion_enabled or not animate:
            if self.timer_id is not None:
                self.after_cancel(self.timer_id)
                self.timer_id = None
            self.position, self.velocity = target, 0.0
            self._draw_position()
        elif self.timer_id is None and (abs(self.position - target) > 0.001 or abs(self.velocity) > 0.01):
            self.timer_id = self.after(16, self._tick)

    def _tick(self):
        self.timer_id = None
        now = time.perf_counter()
        seconds = min(now - self.last_time, 0.05)
        self.last_time = now
        # Exact critically damped step; retargeting retains the current velocity.
        omega = 2 * math.pi / 0.3
        offset = self.position - self.target
        coefficient = self.velocity + omega * offset
        decay = math.exp(-omega * seconds)
        self.position = max(0.0, min(1.0, self.target + (offset + coefficient * seconds) * decay))
        self.velocity = (self.velocity - omega * coefficient * seconds) * decay
        if abs(self.position - self.target) < 0.003 and abs(self.velocity) < 0.06:
            self.position, self.velocity = self.target, 0.0
        else:
            self.timer_id = self.after(16, self._tick)
        self._draw_position()

    def _destroy(self, event):
        if event.widget is self:
            if self.timer_id is not None:
                self.after_cancel(self.timer_id)
                self.timer_id = None
            self.variable.trace_remove("write", self.trace_id)
            self.appearance._observers.remove(self._refresh)
