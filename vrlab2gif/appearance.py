"""Apple-inspired surfaces around native, keyboard-operable Tk controls.

Rounded graphics are drawn locally using system fonts. Dark and Light palettes
cover every surface; the theme selector lives in theme_switch.py.
"""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import font as tkfont, ttk

from PIL import Image, ImageDraw, ImageTk


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    text: str
    secondary: str
    border: str
    shadow: str
    accent: str
    primary: str
    primary_hover: str
    primary_pressed: str
    button: str
    button_hover: str
    button_pressed: str
    entry: str
    entry_border: str
    disabled_surface: str
    disabled_text: str
    selection: str
    trough: str
    scrollbar: str
    scrollbar_hover: str
    success: str
    error: str


PALETTES = {
    "dark": Palette(
        background="#161618", surface="#242427", text="#f5f5f7", secondary="#b1b1bb",
        border="#3b3b42", shadow="#101012", accent="#80b9ff",
        primary="#006edc", primary_hover="#0878e7", primary_pressed="#005bb9",
        button="#38383f", button_hover="#44444d", button_pressed="#4f4f59",
        entry="#1b1b1e", entry_border="#505058", disabled_surface="#2e2e33",
        disabled_text="#8d8d98", selection="#0b65bc", trough="#43434c",
        scrollbar="#696974", scrollbar_hover="#92929d", success="#80dca6",
        error="#ffaaa3",
    ),
    "light": Palette(
        background="#e8edf4", surface="#ffffff", text="#172335", secondary="#465268",
        border="#adb9ca", shadow="#cdd6e3", accent="#005fc6",
        primary="#0071e3", primary_hover="#0077ed", primary_pressed="#005fbe",
        button="#e2e9f3", button_hover="#d3dfef", button_pressed="#c1d1e7",
        entry="#f7f9fd", entry_border="#748398", disabled_surface="#edf0f5",
        disabled_text="#788395", selection="#0064c8", trough="#c4cddd",
        scrollbar="#8390a2", scrollbar_hover="#5c6c83", success="#24804b",
        error="#b42318",
    ),
}


def enable_dpi_awareness() -> None:
    """Let Tk size fonts and surfaces at the display's actual Windows DPI."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def window_work_area(root: tk.Tk) -> tuple[int, int, int, int]:
    """Return the desktop's usable left, top, width and height, excluding the taskbar."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        rectangle = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rectangle), 0):
            return (
                rectangle.left, rectangle.top,
                rectangle.right - rectangle.left, rectangle.bottom - rectangle.top,
            )
    return (root.winfo_vrootx(), root.winfo_vrooty(), root.winfo_screenwidth(), root.winfo_screenheight())


class AppleAppearance:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.scale = max(1.0, float(root.tk.call("tk", "scaling")) / (96 / 72))
        self.images: list[ImageTk.PhotoImage] = []
        self.fonts: list[tkfont.Font] = []
        self._observers: list[Callable[[], None]] = []
        self._built_modes: set[str] = set()
        self._theme_names = {mode: f"VRLab{id(self):x}.{mode}" for mode in PALETTES}
        self._theme_names["_fade"] = f"VRLab{id(self):x}._fade"
        self._skin_sources = {mode: [] for mode in self._theme_names}
        self._style_colors = {}
        self.blend = 0.0
        self.mode = ""
        self.colors = PALETTES["dark"]
        self.style = ttk.Style(root)
        available = set(tkfont.families(root))
        preferred = (
            (".AppleSystemUIFont", "PingFang SC", "Helvetica Neue")
            if sys.platform == "darwin"
            else ("Microsoft YaHei UI", "Segoe UI", "Noto Sans CJK SC")
        )
        family = next((name for name in preferred if name in available), "TkDefaultFont")
        for name in ("TkDefaultFont", "TkTextFont"):
            tkfont.nametofont(name, root=root).configure(family=family, size=10)
        self.title_font = self.font(family, 17, "bold")
        self.subtitle_font = self.font(family, 9)
        self.section_font = self.font(family, 11, "bold")
        self.hint_font = self.font(family, 9)
        self.footer_font = self.font(family, 8)
        # Build skins once before showing the window. Animated frames only
        # recolor existing images/styles, never recreate controls or themes.
        for mode in ("dark", "light", "_fade"):
            self.mode = "dark" if mode == "_fade" else mode
            self.colors = PALETTES[self.mode]
            self._building_skin = mode
            self.style.theme_create(self._theme_names[mode], parent="clam")
            self.style.theme_use(self._theme_names[mode])
            self._configure_styles()
            self._built_modes.add(mode)
            if mode != "_fade":
                self._style_colors[mode] = self._capture_style_colors()
        self.mode, self.colors = "dark", PALETTES["dark"]
        self.style.theme_use(self._theme_names["dark"])
        root.configure(background=self.colors.background)
        from .theme_transition import ThemeTransition
        self.transition = ThemeTransition(self)
        root.bind("<Map>", self._on_map, add="+")

    def subscribe(self, callback: Callable[[], None]) -> None:
        self._observers.append(callback)

    def set_mode(self, mode: str, *, animate=False) -> None:
        if mode not in PALETTES:
            raise ValueError(f"Unknown appearance: {mode}")
        if mode == self.mode and self.blend == float(mode == "light") and self.transition.timer_id is None:
            return
        self.mode = mode
        self.transition.to(mode, animate=animate)

    def _make_photo(self, image: Image.Image) -> ImageTk.PhotoImage:
        photo = ImageTk.PhotoImage(image, master=self.root)
        self.images.append(photo)
        self._skin_sources[self._building_skin].append((photo, image))
        return photo

    def _capture_style_colors(self):
        names = (".", "TFrame", "Window.TFrame", "TLabel", "Window.TLabel", "Title.TLabel",
                 "Subtitle.TLabel", "Section.TLabel", "Hint.TLabel", "Footer.TLabel",
                 "Apple.TCheckbutton", "Apple.TRadiobutton", "Page.TRadiobutton",
                 "Primary.TButton", "Secondary.TButton", "Disclosure.TButton", "Apple.TEntry",
                 "Apple.Vertical.TScrollbar", "Page.Apple.Vertical.TScrollbar")
        return {name: (self.style.configure(name) or {}, self.style.map(name)) for name in names}

    def _present(self, colors: Palette, amount: float, *, endpoint=False):
        from .theme_transition import blend_color
        self.colors, self.blend = colors, amount
        skin = self.mode if endpoint else "_fade"
        if self.style.theme_use() != self._theme_names[skin]:
            self.style.theme_use(self._theme_names[skin])
        if not endpoint:
            for (photo, _), (_, dark), (_, light) in zip(self._skin_sources["_fade"],
                                                       self._skin_sources["dark"], self._skin_sources["light"]):
                photo.paste(Image.blend(dark, light, amount))
            for name, (dark_options, dark_maps) in self._style_colors["dark"].items():
                light_options, light_maps = self._style_colors["light"][name]
                is_color = lambda value: isinstance(value, str) and len(value) == 7 and value.startswith("#")
                options = {key: blend_color(value, light_options[key], amount)
                           for key, value in dark_options.items()
                           if is_color(value) and is_color(light_options.get(key))}
                if options:
                    self.style.configure(name, **options)
                for key, states in dark_maps.items():
                    other = light_maps.get(key, [])
                    if len(states) == len(other) and states and all(is_color(a[-1]) and is_color(b[-1]) for a, b in zip(states, other)):
                        self.style.map(name, **{key: [(*a[:-1], blend_color(a[-1], b[-1], amount)) for a, b in zip(states, other)]})
        # DWM caption and client widgets consume exactly the same frame palette.
        def windows(widget):
            if isinstance(widget, (tk.Tk, tk.Toplevel)):
                widget.configure(background=colors.background)
                self._native_titlebar(widget)
            for child in widget.winfo_children():
                if isinstance(child, (tk.Toplevel, ttk.Frame)):
                    windows(child)
        windows(self.root)
        for callback in tuple(self._observers):
            callback()

    def _configure_styles(self) -> None:
        c = self.colors
        self.style.configure(".", font="TkDefaultFont", background=c.surface, foreground=c.text)
        self.style.configure("TFrame", background=c.surface)
        self.style.configure("Window.TFrame", background=c.background)
        self.style.configure("TLabel", background=c.surface, foreground=c.text)
        self.style.configure("Window.TLabel", background=c.background, foreground=c.text)
        self.style.configure("Title.TLabel", background=c.background, font=self.title_font)
        self.style.configure("Subtitle.TLabel", background=c.background, foreground=c.secondary, font=self.subtitle_font)
        self.style.configure("Section.TLabel", font=self.section_font)
        self.style.configure("Hint.TLabel", foreground=c.secondary, font=self.hint_font)
        self.style.configure("Footer.TLabel", background=c.background, foreground=c.secondary, font=self.footer_font)
        self._buttons()
        self._entries()
        self._progress()
        self._option_controls()
        self._page_tabs()
        self.style.layout("Apple.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
            ]}),
        ])
        self.style.configure(
            "Apple.Vertical.TScrollbar", background=c.scrollbar, troughcolor=c.surface,
            borderwidth=0, bordercolor=c.surface, lightcolor=c.scrollbar,
            darkcolor=c.scrollbar, arrowsize=0, width=self.px(7),
        )
        self.style.map("Apple.Vertical.TScrollbar", background=[("active", c.scrollbar_hover), ("pressed", c.scrollbar_hover)])
        self.style.configure("Page.Apple.Vertical.TScrollbar", troughcolor=c.background, bordercolor=c.background)

    def _on_map(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self._native_titlebar()

    def _option_controls(self) -> None:
        c, p = self.colors, self.px
        for kind in ("Checkbutton", "Radiobutton"):
            images = []
            for selected, focus, disabled in ((False, False, False), (True, False, False),
                                               (False, True, False), (True, True, False),
                                               (False, False, True)):
                size, factor = p(20), 3
                image = Image.new("RGB", (size*factor, size*factor), c.surface)
                draw = ImageDraw.Draw(image)
                box = tuple(v*factor for v in (p(3), p(3), size-p(3), size-p(3)))
                color = c.disabled_surface if disabled else c.primary if selected else c.entry
                border = c.accent if focus else c.border if disabled else c.entry_border
                if kind == "Radiobutton":
                    draw.ellipse(box, fill=color, outline=border, width=(2 if focus else 1)*factor)
                    if selected:
                        draw.ellipse(tuple(v*factor for v in (p(8), p(8), size-p(8), size-p(8))), fill="#ffffff")
                else:
                    draw.rounded_rectangle(box, radius=p(3)*factor, fill=color, outline=border,
                                           width=(2 if focus else 1)*factor)
                    if selected:
                        draw.line([(p(6)*factor, p(10)*factor), (p(9)*factor, p(13)*factor),
                                   (p(14)*factor, p(7)*factor)], fill="#ffffff", width=p(2)*factor)
                photo = self._make_photo(image.resize((size, size), Image.Resampling.LANCZOS))
                images.append(photo)
            element = f"Apple.{kind}.option"
            self.style.element_create(element, "image", images[0], ("disabled", images[4]),
                                      ("selected", "focus", images[3]), ("focus", images[2]),
                                      ("selected", images[1]), sticky="w")
            style = f"Apple.T{kind}"
            self.style.layout(style, [(element, {"side": "left", "sticky": "w"}),
                                      (f"{kind}.padding", {"sticky": "nsew", "children": [
                                          (f"{kind}.label", {"sticky": "nsew"})]})])
            self.style.configure(style, background=c.surface, foreground=c.text, padding=(0, p(2)))
            self.style.map(style, background=[("active", c.surface)], foreground=[("disabled", c.disabled_text)])

    def _page_tabs(self) -> None:
        c, p = self.colors, self.px
        track = c.surface if self.mode == "dark" else c.button
        selection = c.button_hover if self.mode == "dark" else c.surface
        normal, hover, pressed, selected, selected_pressed, focused, selected_focused = [self.rounded_image(
            p(32), p(30), color, radius=p(8), background=track,
            outline=c.entry_border if chosen and self.mode == "dark" else c.border if chosen else None,
            focused=focus,
        ) for color, chosen, focus in (
            (track, False, False), (c.button if self.mode == "dark" else c.button_hover, False, False),
            (c.button_pressed, False, False), (selection, True, False),
            (c.button_pressed if self.mode == "dark" else c.entry, True, False),
            (track, False, True), (selection, True, True),
        )]
        element = "Apple.Page.tab"
        self.style.element_create(element, "image", normal,
                                  ("selected", "pressed", selected_pressed), ("pressed", pressed),
                                  ("selected", "focus", selected_focused), ("focus", focused),
                                  ("selected", selected), ("active", hover),
                                  border=p(10), padding=0, sticky="nsew")
        self.style.layout("Page.TRadiobutton", [(element, {"sticky": "nsew", "children": [
            ("Radiobutton.padding", {"sticky": "nsew", "children": [
                ("Radiobutton.label", {"sticky": "nsew"}),
            ]}),
        ]})])
        self.style.configure("Page.TRadiobutton", background=track, foreground=c.secondary,
                             padding=(p(8), p(4)), anchor="center", width=0)
        self.style.map("Page.TRadiobutton", foreground=[("selected", c.text), ("active", c.text)])

    def _native_titlebar(self, window: tk.Misc | None = None) -> None:
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        try:
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            target = window if window is not None else self.root
            hwnd = user32.GetParent(target.winfo_id()) or target.winfo_id()
            set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            set_attribute.restype = ctypes.c_long
            c = self.colors
            dark = sum(int(c.background[i:i+2], 16) * weight for i, weight in ((1, .2126), (3, .7152), (5, .0722))) < 128
            state = (hwnd, dark, c.background, c.text)
            previous = getattr(target, "_vrlab_titlebar_state", None)
            if state == previous:
                return
            if previous is None or previous[:2] != state[:2]:
                value = wintypes.BOOL(dark)
                for attribute in (20, 19):
                    if set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) >= 0:
                        break
            if previous is None or previous[0] != hwnd:
                target._vrlab_caption_colors_supported = None
            if target._vrlab_caption_colors_supported is not False:
                results = []
                for attribute, color in ((35, c.background), (36, c.text)):
                    value = wintypes.DWORD(sum(int(color[i:i+2], 16) << (8*index) for index, i in enumerate((1, 3, 5))))
                    results.append(set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)))
                target._vrlab_caption_colors_supported = all(result >= 0 for result in results)
            target._vrlab_titlebar_state = state
        except (AttributeError, OSError):
            # Client-area theming still works on systems without this DWM option.
            pass

    def px(self, value: float) -> int:
        return max(1, round(value * self.scale))

    def font(self, family: str, size: int, weight: str = "normal") -> tkfont.Font:
        value = tkfont.Font(root=self.root, family=family, size=size, weight=weight)
        self.fonts.append(value)
        return value

    def rounded_image(
        self, width: int, height: int, fill: str, *, radius: int,
        background: str | None = None, outline: str | None = None, focused: bool = False,
    ) -> ImageTk.PhotoImage:
        factor = 3
        image = Image.new("RGB", (width * factor, height * factor), background or self.colors.surface)
        draw = ImageDraw.Draw(image)
        inset = self.px(1)
        if focused:
            draw.rounded_rectangle(
                (0, 0, width * factor - 1, height * factor - 1),
                radius=radius * factor, fill=self.colors.accent,
            )
            inset = self.px(3)
        draw.rounded_rectangle(
            (inset * factor, inset * factor, (width - inset) * factor - 1, (height - inset) * factor - 1),
            radius=max(1, radius - inset) * factor, fill=fill,
            outline=outline, width=factor,
        )
        return self._make_photo(image.resize((width, height), Image.Resampling.LANCZOS))

    def _buttons(self) -> None:
        c = self.colors
        for name, normal, hover, pressed, foreground in (
            ("Primary", c.primary, c.primary_hover, c.primary_pressed, "#ffffff"),
            ("Secondary", c.button, c.button_hover, c.button_pressed, c.text),
            ("Disclosure", c.surface, c.button, c.button_hover, c.accent if self.mode == "light" else c.secondary),
        ):
            images = [self.rounded_image(
                self.px(36), self.px(36), color, radius=self.px(10), focused=focus,
                outline=c.entry_border if name == "Secondary" and self.mode == "light" and color != c.disabled_surface else None,
            ) for color, focus in ((normal, False), (hover, False), (pressed, False), (c.disabled_surface, False), (normal, True))]
            element = f"Apple.{name}.button"
            self.style.element_create(
                element, "image", images[0],
                ("disabled", images[3]), ("pressed", images[2]),
                ("active", images[1]), ("focus", images[4]),
                border=self.px(13), padding=0, sticky="nsew",
            )
            style_name = f"{name}.TButton"
            self.style.layout(style_name, [(element, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [
                    ("Button.label", {"sticky": "nsew"}),
                ]}),
            ]})])
            self.style.configure(
                style_name, foreground=foreground, background=c.surface,
                padding=(self.px(12), self.px(7)), anchor="center", borderwidth=0, width=0,
            )
            self.style.map(style_name, foreground=[("disabled", c.disabled_text)])

    def _entries(self) -> None:
        c = self.colors
        images = [self.rounded_image(
            self.px(32), self.px(32), color, radius=self.px(9),
            outline=outline, focused=focus,
        ) for color, outline, focus in (
            (c.entry, c.entry_border, False),
            (c.entry, None, True),
            (c.disabled_surface, c.border, False),
        )]
        self.style.element_create(
            "Apple.Entry.field", "image", images[0], ("disabled", images[2]),
            ("focus", images[1]), border=self.px(11), padding=0, sticky="nsew",
        )
        self.style.layout("Apple.TEntry", [("Apple.Entry.field", {"sticky": "nsew", "children": [
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"}),
            ]}),
        ]})])
        self.style.configure(
            "Apple.TEntry", padding=(self.px(10), self.px(7)),
            fieldbackground=c.entry, foreground=c.text, insertcolor=c.text,
            selectbackground=c.selection, selectforeground="#ffffff", borderwidth=0,
        )
        self.style.map(
            "Apple.TEntry", foreground=[("disabled", c.disabled_text)],
            fieldbackground=[("disabled", c.disabled_surface)],
        )

    def _progress(self) -> None:
        c = self.colors
        for name, color in (("trough", c.trough), ("pbar", c.primary)):
            image = self.rounded_image(
                self.px(16), self.px(6), color, radius=self.px(3),
                background=c.surface if name == "trough" else c.trough,
            )
            self.style.element_create(
                f"Apple.Progress.{name}", "image", image,
                border=self.px(3), padding=0, sticky="nsew",
            )
        self.style.layout("Apple.Horizontal.TProgressbar", [
            ("Apple.Progress.trough", {"sticky": "nsew", "children": [
                ("Apple.Progress.pbar", {"side": "left", "sticky": "ns"}),
            ]}),
        ])

class SegmentedPages(tk.Canvas):
    """One shared navigation track around native, keyboard-accessible radio buttons."""

    def __init__(self, parent: tk.Misc, appearance: AppleAppearance,
                 variable: tk.StringVar, choices: list[tuple[str, str | tk.StringVar]],
                 command: Callable[[str], None]) -> None:
        super().__init__(parent, height=appearance.px(36), width=appearance.px(440),
                         highlightthickness=0, borderwidth=0,
                         background=appearance.colors.background)
        self.appearance = appearance
        self.buttons: dict[str, ttk.Radiobutton] = {}
        self._windows: list[int] = []
        self._image = self.create_image(0, 0, anchor="nw")
        self._photo: ImageTk.PhotoImage | None = None
        self._size = None
        for name, label in choices:
            options = {"textvariable": label} if isinstance(label, tk.StringVar) else {"text": label}
            button = ttk.Radiobutton(self, **options, variable=variable, value=name,
                                     command=lambda key=name: command(key),
                                     style="Page.TRadiobutton", takefocus=True)
            self.buttons[name] = button
            self._windows.append(self.create_window(0, 0, window=button))
        self.bind("<Configure>", lambda event: self._layout())
        appearance.subscribe(self._recolor)

    def _recolor(self) -> None:
        self.configure(background=self.appearance.colors.background)
        self._layout(repaint=True)

    def _layout(self, *, repaint=False) -> None:
        p, c = self.appearance.px, self.appearance.colors
        width, height = min(self.winfo_width(), p(440)), self.winfo_height()
        if min(width, height) < 4:
            return
        if self._size != (width, height):
            self._size = (width, height)
            factor = 3
            self._rasters = []
            for mode, palette in PALETTES.items():
                image = Image.new("RGB", (width * factor, height * factor), palette.background)
                ImageDraw.Draw(image).rounded_rectangle((0, 0, width*factor-1, height*factor-1),
                                       radius=p(11)*factor,
                                       fill=palette.surface if mode == "dark" else palette.button,
                                       outline=palette.border, width=factor)
                self._rasters.append(image.resize((width, height), Image.Resampling.LANCZOS))
            self._photo = ImageTk.PhotoImage(self._rasters[0], master=self)
            self.itemconfigure(self._image, image=self._photo)
            repaint = True
        if repaint:
            self._photo.paste(Image.blend(*self._rasters, self.appearance.blend))
        inset, gap = p(3), p(2)
        usable = width - 2 * inset
        for index, window in enumerate(self._windows):
            left = inset + round(index * usable / len(self._windows))
            right = inset + round((index + 1) * usable / len(self._windows))
            self.coords(window, (left + right) / 2, height / 2)
            self.itemconfigure(window, width=max(1, right-left-gap), height=max(1, height-2*inset))


class RoundedCard(tk.Frame):
    """A resizable theme-aware surface around native Tk controls."""

    def __init__(self, parent: tk.Misc, appearance: AppleAppearance, *, padding: int = 20) -> None:
        super().__init__(parent, background=appearance.colors.background, borderwidth=0, highlightthickness=0)
        self.appearance = appearance
        self._photo: ImageTk.PhotoImage | None = None
        self._size = (0, 0)
        self.canvas = tk.Canvas(self, background=appearance.colors.background, borderwidth=0, highlightthickness=0, takefocus=False)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._image_id = self.canvas.create_image(0, 0, anchor="nw")
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=appearance.px(padding), pady=appearance.px(padding))
        self.bind("<Configure>", self._paint)
        appearance.subscribe(self._recolor)

    def _paint(self, event: tk.Event) -> None:
        self._draw(event.width, event.height)

    def _recolor(self) -> None:
        self.configure(background=self.appearance.colors.background)
        self.canvas.configure(background=self.appearance.colors.background)
        self._draw(self.winfo_width(), self.winfo_height(), repaint=True)

    def _draw(self, width: int, height: int, *, repaint=False) -> None:
        if min(width, height) < 4:
            return
        if self._size != (width, height):
            self._size = (width, height)
            factor = 2
            self._rasters = []
            for mode, c in PALETTES.items():
                image = Image.new("RGB", (width * factor, height * factor), c.background)
                draw = ImageDraw.Draw(image)
                radius = self.appearance.px(16) * factor
                draw.rounded_rectangle((factor, factor * 2, (width - 1) * factor, height * factor - 1), radius=radius, fill=c.shadow)
                draw.rounded_rectangle((factor, 0, (width - 1) * factor, (height - 2) * factor),
                                      radius=radius, fill=c.surface, outline=c.border,
                                      width=factor if mode == "light" else 1)
                self._rasters.append(image.resize((width, height), Image.Resampling.LANCZOS))
            self._photo = ImageTk.PhotoImage(self._rasters[0], master=self)
            self.canvas.itemconfigure(self._image_id, image=self._photo)
            repaint = True
        if repaint:
            self._photo.paste(Image.blend(*self._rasters, self.appearance.blend))


class ScrollArea(ttk.Frame):
    """Keep actions visible while forms remain usable at large system text sizes."""

    def __init__(self, parent: tk.Misc, appearance: AppleAppearance) -> None:
        super().__init__(parent, style="Window.TFrame")
        self.appearance = appearance
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=appearance.colors.background, highlightthickness=0, borderwidth=0, takefocus=False)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Page.Apple.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas, style="Window.TFrame")
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self._scrolling = False
        self._layout_id: str | None = None
        self.content.bind("<Configure>", self._schedule_layout)
        self.canvas.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._destroy)
        root = self.winfo_toplevel()
        # Wrapped child labels can change requested height without resizing the
        # fixed canvas window. Re-evaluate after their geometry has settled.
        root.bind("<Configure>", self._schedule_layout, add="+")
        root.bind("<MouseWheel>", self._wheel, add="+")
        root.bind("<Button-4>", self._wheel, add="+")
        root.bind("<Button-5>", self._wheel, add="+")
        root.bind("<FocusIn>", self._focus, add="+")
        appearance.subscribe(self._recolor)

    def _recolor(self) -> None:
        self.canvas.configure(background=self.appearance.colors.background)

    def _schedule_layout(self, event: tk.Event) -> None:
        if self._contains_widget(event.widget) and self._layout_id is None:
            self._layout_id = self.after_idle(self._layout)

    def _contains_widget(self, widget: tk.Misc) -> bool:
        path = str(widget)
        return path == str(self) or path.startswith(str(self) + ".")

    def _destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._layout_id is not None:
            self.after_cancel(self._layout_id)
            self._layout_id = None

    def _layout(self) -> None:
        self._layout_id = None
        width = self.canvas.winfo_width()
        viewport = self.canvas.winfo_height()
        if int(float(self.canvas.itemcget(self.window, "width"))) != width:
            self.canvas.itemconfigure(self.window, width=width)
        requested = self.content.winfo_reqheight()
        height = max(requested, viewport)
        if int(float(self.canvas.itemcget(self.window, "height"))) != height:
            self.canvas.itemconfigure(self.window, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        scrolling = requested > viewport + 1
        if scrolling != self._scrolling:
            self._scrolling = scrolling
            if scrolling:
                self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(3, 0))
            else:
                self.scrollbar.grid_remove()
                self.canvas.yview_moveto(0)

    def _wheel(self, event: tk.Event) -> str | None:
        if not self._scrolling or not self._contains_widget(event.widget) or isinstance(event.widget, tk.Text):
            return None
        delta = -1 if event.num == 4 else 1 if event.num == 5 else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(delta * 3, "units")
        return "break"

    def _focus(self, event: tk.Event) -> None:
        if not self._scrolling or not str(event.widget).startswith(str(self.content)):
            return
        self._scroll_to(event.widget)

    def reveal(self, widget: tk.Misc) -> None:
        """Bring newly expanded controls into view without changing window size."""
        self.update_idletasks()
        self._scroll_to(widget)

    def _scroll_to(self, widget: tk.Misc) -> None:
        if not self._scrolling:
            return
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        viewport = self.canvas.winfo_height()
        height = max(self.content.winfo_height(), 1)
        if widget.winfo_height() > viewport:
            self.canvas.yview_moveto(max(0, top - 8) / height)
        elif top < visible_top:
            self.canvas.yview_moveto(max(0, top - 12) / height)
        elif bottom > visible_top + viewport:
            self.canvas.yview_moveto((bottom - viewport + 12) / height)
