"""One interruptible color transition for client surfaces and native captions."""
from __future__ import annotations

from dataclasses import fields
import math
import time

from .appearance import PALETTES, Palette
from .theme_switch import system_motion_enabled
from .motion_timing import MotionTiming


def blend_color(dark: str, light: str, amount: float) -> str:
    return "#" + "".join(f"{round(int(dark[i:i+2], 16) * (1-amount) + int(light[i:i+2], 16) * amount):02x}"
                          for i in (1, 3, 5))


class ThemeTransition:
    def __init__(self, appearance):
        self.appearance, self.root = appearance, appearance.root
        self.alpha = self.target = self.velocity = 0.0
        self.timer_id = None
        self.last_time = time.perf_counter()
        self.motion_enabled = system_motion_enabled()
        self.scene = None
        self.timing = MotionTiming()
        self.root.bind("<Destroy>", self._destroy, add="+")

    def to(self, mode: str, animate=True):
        self.appearance.mode = mode
        self.target = float(mode == "light")
        self.last_time = time.perf_counter()
        if not animate or not self.motion_enabled:
            self.cancel()
            self.alpha, self.velocity = self.target, 0.0
            self.render(self.alpha, endpoint=True)
        else:
            if self.scene is not None and not self.scene.prepare(mode):
                self.cancel()
                self.alpha, self.velocity = self.target, 0.0
                self.render(self.alpha, endpoint=True)
                return
            # Reuse the current displayed brightness and velocity on reversal.
            self.render(self.alpha)
            # Preparation is outside animation time: the first visible frame
            # must not jump ahead by the time spent capturing the two themes.
            self.last_time = time.perf_counter()
            if self.timer_id is None and (abs(self.alpha-self.target) > .001 or abs(self.velocity) > .01):
                self.timing.start()
                self.timer_id = self.root.after(1, self._tick)

    def render(self, amount: float, *, endpoint=False):
        self.alpha = max(0.0, min(1.0, amount))
        colors = Palette(**{field.name: blend_color(getattr(PALETTES["dark"], field.name),
                                                    getattr(PALETTES["light"], field.name), self.alpha)
                            for field in fields(Palette)})
        if self.scene is not None and self.scene.active:
            if endpoint:
                self.appearance._present(colors, self.alpha, endpoint=True)
                self.root.update_idletasks()
                self.scene.stop()
            else:
                self.appearance.colors, self.appearance.blend = colors, self.alpha
                try:
                    self.scene.render(self.alpha)
                except OSError as exc:
                    self.scene.last_error = str(exc)
                    self.cancel()
                    self.alpha, self.velocity = self.target, 0.0
                    self.render(self.alpha, endpoint=True)
        else:
            self.appearance._present(colors, self.alpha, endpoint=endpoint)

    def _tick(self):
        self.timer_id = None
        now = time.perf_counter()
        seconds, omega = min(now-self.last_time, .05), 2*math.pi/.4
        self.last_time = now
        offset = self.alpha-self.target
        coefficient = self.velocity+omega*offset
        decay = math.exp(-omega*seconds)
        amount = self.target+(offset+coefficient*seconds)*decay
        self.velocity = (self.velocity-omega*coefficient*seconds)*decay
        if abs(amount-self.target) < .003 and abs(self.velocity) < .06:
            self.alpha, self.velocity = self.target, 0.0
            self.timing.stop()
            self.render(self.alpha, endpoint=True)
        else:
            self.render(amount)
            if self.alpha == self.target and self.velocity == 0:
                return  # A compositor failure already completed the theme.
            # Include paint cost in the frame budget rather than adding it to
            # a fixed delay (which halves frame rate on high-DPI displays).
            self.timer_id = self.root.after(self.timing.delay(now), self._tick)

    def finish(self):
        if self.scene is not None and self.scene.active:
            self.cancel()
            self.alpha, self.velocity = self.target, 0.0
            self.render(self.alpha, endpoint=True)

    def cancel(self):
        self.timing.stop()
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def _destroy(self, event):
        if event.widget is self.root:
            self.cancel()
            if self.scene is not None:
                self.scene.close()
