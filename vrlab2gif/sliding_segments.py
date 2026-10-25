"""Page navigation with one sliding selection, matching the theme selector."""
from __future__ import annotations

import math
import time
import tkinter as tk

from PIL import Image, ImageDraw

from .palette_image import PaletteImage
from .motion_timing import MotionTiming


def _rounded(width, height, radius, fill, border, background=None):
    image = Image.new("RGBA", (width*3, height*3), background or (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, width*3-1, height*3-1), radius=radius*3,
                                           fill=fill, outline=border, width=3)
    return image.resize((width, height), Image.Resampling.LANCZOS)


class PageSegment(tk.Canvas):
    """Keyboard-focusable hit area; shares the parent's moving thumb image."""
    def __init__(self, parent, key, label):
        super().__init__(parent, width=1, height=1, highlightthickness=0, borderwidth=0,
                         takefocus=True, cursor="hand2")
        self.owner, self.key = parent, key
        self.background_image = self.create_image(0, 0, anchor="nw")
        self.image = self.create_image(0, 0, anchor="nw")
        self.label = self.create_text(0, 0, text=label.get() if isinstance(label, tk.StringVar) else label,
                                      font="TkDefaultFont")
        self.label_variable = label if isinstance(label, tk.StringVar) else None
        self.trace_id = (label.trace_add("write", lambda *args: self.itemconfigure(self.label, text=label.get()))
                         if self.label_variable is not None else None)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda event: parent._focus(key))
        self.bind("<FocusOut>", lambda event: parent._focus(None))
        self.bind("<space>", lambda event: self._key(key))
        self.bind("<Return>", lambda event: self._key(key))
        self.bind("<Control-Return>", lambda event: None)
        for event, offset in (("Left", -1), ("Right", 1)):
            self.bind(f"<{event}>", lambda event, step=offset: self._key(
                parent.keys[(parent.keys.index(key)+step) % len(parent.keys)]))
        self.bind("<Home>", lambda event: self._key(parent.keys[0]))
        self.bind("<End>", lambda event: self._key(parent.keys[-1]))
        self.bind("<Destroy>", self._destroy)

    def _key(self, key):
        self.owner.select(key, animate=False)
        self.owner.buttons[key].focus_set()
        return "break"

    def _press(self, event):
        self.focus_set()
        self.owner.pressed_key = self.key
        self.owner._retarget(self.owner.keys.index(self.key))
        self.owner._draw_state()
        return "break"

    def _release(self, event):
        key, self.owner.pressed_key = self.owner.pressed_key, None
        if key is not None:
            x = event.x+self.winfo_x()
            y = event.y+self.winfo_y()
            if 0 <= x < self.owner._size[0] and 0 <= y < self.owner._size[1]:
                self.owner.select(key)
            else:
                self.owner._retarget(self.owner.keys.index(self.owner.variable.get()))
            self.owner._draw_state()
        return "break"

    def invoke(self):
        self.owner.select(self.key)

    def instate(self, states):
        selected = self.owner.variable.get() == self.key
        actual = {"selected"} if selected else set()
        return all((state[1:] not in actual) if state.startswith("!") else state in actual for state in states)

    def _destroy(self, event):
        if event.widget is self and self.trace_id is not None:
            self.label_variable.trace_remove("write", self.trace_id)


class SlidingSegments(tk.Canvas):
    def __init__(self, parent, appearance, variable, choices, command):
        from .theme_switch import system_motion_enabled
        super().__init__(parent, width=appearance.px(440), height=appearance.px(36),
                         highlightthickness=0, borderwidth=0, takefocus=False)
        self.appearance, self.variable, self.command = appearance, variable, command
        self.keys = [key for key, _ in choices]
        self.motion_enabled = system_motion_enabled()
        self.position = self.target = float(self.keys.index(variable.get()))
        self.velocity, self.last_time = 0.0, time.perf_counter()
        self.timer_id = None
        self.timing = MotionTiming()
        self.pressed_key = self.focused_key = None
        self._animate = True
        self._size = None
        self.track = self.create_image(0, 0, anchor="nw")
        self.buttons = {key: PageSegment(self, key, label) for key, label in choices}
        self._windows = {key: self.create_window(0, 0, anchor="nw", window=button)
                         for key, button in self.buttons.items()}
        self.trace_id = variable.trace_add("write", self._changed)
        self.bind("<Configure>", lambda event: self._layout())
        self.bind("<Destroy>", self._destroy)
        appearance.subscribe(self._recolor)
        self.configure(background=appearance.colors.background)

    def _layout(self, *, repaint=False):
        from .appearance import PALETTES
        p = self.appearance.px
        width, height = self.winfo_width(), self.winfo_height()
        if min(width, height) < 4:
            return
        if self._size != (width, height):
            self._size = width, height
            self.inset = p(3)
            self.segment_width = (width-2*self.inset)/len(self.keys)
            tracks, thumbs = [], []
            for mode, c in PALETTES.items():
                track = "#2a2a2f" if mode == "dark" else "#e8e8ed"
                selected = "#50505b" if mode == "dark" else "#ffffff"
                tracks.append(tuple(_rounded(width, height, p(11), track, border, c.background)
                                    for border in (c.border, c.accent)))
                thumbs.append(_rounded(round(self.segment_width), height-2*self.inset,
                                       p(8), selected, selected))
            self._tracks = tuple(PaletteImage(self, dark, light) for dark, light in zip(*tracks))
            self._thumb = PaletteImage(self, *thumbs)
            for index, key in enumerate(self.keys):
                left = self.inset+round(index*self.segment_width)
                right = self.inset+round((index+1)*self.segment_width)
                self.coords(self._windows[key], left, self.inset)
                self.itemconfigure(self._windows[key], width=right-left, height=height-2*self.inset)
                button = self.buttons[key]
                button.offset = left-self.inset
                button.coords(button.background_image, -left, -self.inset)
                self.buttons[key].coords(button.label, (right-left)/2, (height-2*self.inset)/2)
            repaint = True
        if repaint:
            self._paint_colors()
        self._draw_state()
        self._draw_position()

    def _paint_colors(self):
        for image in (*self._tracks, self._thumb):
            image.render(self.appearance.blend)
        for button in self.buttons.values():
            button.configure(background=self.appearance.colors.background)
            button.itemconfigure(button.image, image=self._thumb)

    def _recolor(self):
        self.configure(background=self.appearance.colors.background)
        self._layout(repaint=True)

    def _draw_state(self):
        if self._size is None or not self.winfo_exists():
            return
        self.itemconfigure(self.track, image=self._tracks[int(self.focused_key is not None)])
        selected = self.pressed_key or self.variable.get()
        for key, button in self.buttons.items():
            if button.winfo_exists():
                button.itemconfigure(button.background_image, image=self._tracks[int(self.focused_key is not None)])
                button.itemconfigure(button.label, fill=self.appearance.colors.text if key == selected
                                     else self.appearance.colors.secondary)

    def _draw_position(self):
        if self._size is not None and self.winfo_exists():
            for button in self.buttons.values():
                button.coords(button.image, self.position*self.segment_width-button.offset, 0)

    def _focus(self, key):
        self.focused_key = key
        self._draw_state()

    def select(self, key, *, animate=True):
        if key not in self.buttons:
            raise ValueError(f"Unknown page: {key}")
        self._animate = animate
        try:
            self.command(key)
        finally:
            self._animate = True

    def _changed(self, *unused):
        self._retarget(self.keys.index(self.variable.get()), animate=self._animate)
        self._draw_state()

    def _retarget(self, target, *, animate=True):
        self.target, self.last_time = float(target), time.perf_counter()
        if not animate or not self.motion_enabled:
            self.timing.stop()
            if self.timer_id is not None:
                self.after_cancel(self.timer_id)
                self.timer_id = None
            self.position, self.velocity = self.target, 0.0
            self._draw_position()
        elif self.timer_id is None and (abs(self.position-self.target) > .001 or abs(self.velocity) > .01):
            self.timing.start()
            self.timer_id = self.after(1, self._tick)

    def _tick(self):
        self.timer_id = None
        now = time.perf_counter()
        seconds, omega = min(now-self.last_time, .05), 2*math.pi/.3
        self.last_time = now
        offset = self.position-self.target
        coefficient = self.velocity+omega*offset
        decay = math.exp(-omega*seconds)
        self.position = max(0.0, min(len(self.keys)-1, self.target+(offset+coefficient*seconds)*decay))
        self.velocity = (self.velocity-omega*coefficient*seconds)*decay
        if abs(self.position-self.target) < .003 and abs(self.velocity) < .06:
            self.position, self.velocity = self.target, 0.0
            self.timing.stop()
        else:
            self.timer_id = self.after(self.timing.delay(now), self._tick)
        self._draw_position()

    def _destroy(self, event):
        if event.widget is self:
            self.timing.stop()
            if self.timer_id is not None:
                self.after_cancel(self.timer_id)
                self.timer_id = None
            self.variable.trace_remove("write", self.trace_id)
            self.appearance._observers.remove(self._recolor)
