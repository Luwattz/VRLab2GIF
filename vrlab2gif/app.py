"""Chinese desktop interface for the Virtual Reality Lab GIF converter."""

from __future__ import annotations

import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageTk
from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP, TkinterDnD

from . import COPYRIGHT, __version__
from .core import AngleFilters, ConversionCancelled
from .native import NATIVE_EXTENSIONS, create_native_gifs, validate_native_source
from .ppt import PptOptions, export_gifs_to_pptx
from .ppt_dialog import PptExportDialog, PptExportRequest, suggested_ppt_path
from .appearance import AppleAppearance, RoundedCard, ScrollArea, SegmentedPages, enable_dpi_awareness, window_work_area
from .theme_switch import ThemeSwitch


class GifCreatorApp:
    """Keep all Tk operations on the main thread; workers publish queue events."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"VRLab2GIF v{__version__} · 视角合成器")

        self.input_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.delay_var = tk.StringVar(value="300")
        self.font_size_var = tk.StringVar(value="24")
        self.h_min_var = tk.StringVar()
        self.h_max_var = tk.StringVar()
        self.v_min_var = tk.StringVar()
        self.v_max_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪，拖入视角文件或点击“选择文件”。")
        self.progress_var = tk.DoubleVar(value=0)

        self.log_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._processing = False
        self._close_requested = False
        self._pending_outcome: tuple[str, Any] | None = None
        self._poll_id: str | None = None
        self._editable_widgets: list[ttk.Widget] = []
        self.page_var = tk.StringVar(value="settings")
        self.filter_tab_var = tk.StringVar(value="角度筛选")
        self._parameters_stacked: bool | None = None
        self._last_auto_output = ""
        self.filter_summary_var = tk.StringVar(value="不限角度")
        self.dark_mode_var = tk.BooleanVar(value=True)
        self.theme_label_var = tk.StringVar(value="Dark")
        self._status_tone = "secondary"
        self._filter_summary_invalid = False
        self._drop_hover = False
        self._completed_gifs: tuple[Path, ...] = ()
        self._completed_source: Path | None = None
        self._job_source: Path | None = None
        self._active_job = "gif"
        self._ppt_options: PptOptions | None = None
        self._ppt_open_after = False
        self._ppt_request: PptExportRequest | None = None
        self._reveal_dir: Path | None = None

        self._configure_style()
        self._configure_icon()
        p = self.appearance.px
        self.work_area = window_work_area(root)
        left, top, desktop_width, desktop_height = self.work_area
        width = min(p(700), round(desktop_width * 0.60))
        height = min(p(450), round(desktop_height * 0.68))
        x, y = left + (desktop_width - width) // 2, top + (desktop_height - height) // 2
        self.root.geometry(f"{width}x{height}{x:+d}{y:+d}")
        self.root.minsize(min(p(540), width), min(p(340), height))
        self.create_widgets()
        self.appearance.subscribe(self._refresh_colors)
        self.input_file_var.trace_add("write", self._sync_default_output)
        self.output_dir_var.trace_add("write", self._clear_reveal_directory)
        self._configure_drop_targets()
        for variable in (self.h_min_var, self.h_max_var, self.v_min_var, self.v_max_var):
            variable.trace_add("write", self._update_filter_summary)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-Return>", self._start_shortcut)
        self.root.bind("<Escape>", self._cancel_shortcut)
        self.root.bind("<Control-Tab>", lambda event: self._cycle_page(1))
        self.root.bind("<Control-Shift-Tab>", lambda event: self._cycle_page(-1))
        self._poll_id = self.root.after(100, self.check_log_queue)

    def _configure_style(self) -> None:
        self.appearance = AppleAppearance(self.root)

    def set_theme(self, mode: str, *, animate=False) -> None:
        self.appearance.set_mode(mode, animate=animate)
        if self.dark_mode_var.get() != (mode == "dark"):
            self.dark_mode_var.set(mode == "dark")
        self.theme_label_var.set("Dark" if mode == "dark" else "Light")
        if not animate:
            self.theme_switch._retarget(float(mode == "light"), animate=False)

    def toggle_theme(self, *, animate=True) -> None:
        self.set_theme("dark" if self.dark_mode_var.get() else "light", animate=animate)

    def _set_status_tone(self, tone: str) -> None:
        self._status_tone = tone
        self.status_label.configure(foreground=getattr(self.appearance.colors, tone))

    def _refresh_colors(self) -> None:
        c = self.appearance.colors
        self.log_text.configure(
            background=c.surface, foreground=c.secondary,
            selectbackground=c.selection, selectforeground="#ffffff", insertbackground=c.text,
        )
        self.log_text.tag_configure("success", foreground=c.success)
        self.log_text.tag_configure("error", foreground=c.error)
        self._set_status_tone(self._status_tone)
        self.filter_summary_label.configure(foreground=c.error if self._filter_summary_invalid else c.secondary)
        self._paint_drop_area()

    def _configure_icon(self) -> None:
        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        icon_path = resource_root / "assets" / "vrlab2gif-logo.png"
        self.header_icon: ImageTk.PhotoImage | None = None
        self._window_icons: list[ImageTk.PhotoImage] = []
        if not icon_path.is_file():
            return
        with Image.open(icon_path) as icon:
            for size in (16, 32, 48, 64, 128, 256):
                self._window_icons.append(ImageTk.PhotoImage(
                    icon.resize((size, size), Image.Resampling.LANCZOS), master=self.root,
                ))
            size = self.appearance.px(34)
            self.header_icon = ImageTk.PhotoImage(
                icon.resize((size, size), Image.Resampling.LANCZOS), master=self.root,
            )
        self.root.iconphoto(True, *self._window_icons)

    def _track(self, widget: ttk.Widget) -> ttk.Widget:
        self._editable_widgets.append(widget)
        return widget

    def create_widgets(self) -> None:
        p = self.appearance.px
        c = self.appearance.colors
        main = ttk.Frame(self.root, style="Window.TFrame", padding=(p(16), p(12), p(16), p(8)))
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        heading = ttk.Frame(main, style="Window.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, p(8)))
        text_column = 1 if self.header_icon is not None else 0
        heading.columnconfigure(text_column, weight=1)
        if self.header_icon is not None:
            ttk.Label(heading, image=self.header_icon, style="Window.TLabel").grid(row=0, column=0, rowspan=2, padx=(0, p(10)))
        title_line = ttk.Frame(heading, style="Window.TFrame")
        title_line.grid(row=0, column=text_column, sticky="w")
        self.title_label = ttk.Label(title_line, text="视角合成器", style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.version_label = ttk.Label(title_line, text=f"v{__version__}", style="Subtitle.TLabel")
        self.version_label.grid(row=0, column=1, sticky="sw", padx=(p(10), 0), pady=(0, p(3)))
        self.navigation = SegmentedPages(
            heading, self.appearance, self.page_var,
            [("settings", "生成设置"), ("filters", self.filter_tab_var), ("logs", "运行日志")],
            self.select_page,
        )
        self.navigation.grid(row=1, column=text_column, columnspan=2, sticky="ew", pady=(p(4), 0))
        self.page_buttons = self.navigation.buttons
        self.theme_switch = ThemeSwitch(heading, self.appearance, self.dark_mode_var, self.toggle_theme)
        self.theme_switch.grid(row=0, column=text_column + 1, sticky="e", padx=(p(8), 0))

        pages = ttk.Frame(main, style="Window.TFrame")
        pages.grid(row=1, column=0, sticky="nsew")
        pages.rowconfigure(0, weight=1)
        pages.columnconfigure(0, weight=1)
        self.page_areas = {name: ScrollArea(pages, self.appearance) for name in self.page_buttons}
        for area in self.page_areas.values():
            area.content.columnconfigure(0, weight=1)
        page = self.page_areas["settings"].content
        page.columnconfigure(0, weight=1)

        self.settings_card = RoundedCard(page, self.appearance, padding=10)
        self.settings_card.grid(row=0, column=0, sticky="ew")
        settings = self.settings_card.content
        settings.columnconfigure(1, weight=1)
        self.drop_surface = tk.Canvas(settings, height=p(68), width=1,
                                      highlightthickness=0, background=c.surface)
        self.drop_surface.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._drop_border = self.drop_surface.create_polygon(0, 0, 0, 0, smooth=True)
        self._drop_title = self.drop_surface.create_text(0, 0, anchor="w", font="TkDefaultFont")
        self.input_entry = self._track(ttk.Entry(self.drop_surface, textvariable=self.input_file_var, style="Apple.TEntry", width=1))
        self._drop_entry_window = self.drop_surface.create_window(0, 0, window=self.input_entry, anchor="w")
        self.input_browse_button = self._track(ttk.Button(self.drop_surface, text="选择文件…", command=self.ask_input_file, style="Secondary.TButton", takefocus=True))
        self._drop_button_window = self.drop_surface.create_window(0, 0, window=self.input_browse_button, anchor="e")
        self.drop_surface.bind("<Configure>", self._layout_drop_area)
        ttk.Label(settings, text="输出 GIF").grid(row=1, column=0, sticky="w", padx=(0, p(12)), pady=(p(6), 0))
        self.output_entry = self._track(ttk.Entry(settings, textvariable=self.output_dir_var, style="Apple.TEntry", width=1))
        self.output_entry.grid(row=1, column=1, sticky="ew", pady=(p(6), 0))
        self.output_browse_button = self._track(ttk.Button(settings, text="更改…", command=self.ask_output_dir, style="Secondary.TButton", takefocus=True))
        self.output_browse_button.grid(row=1, column=2, sticky="e", padx=(p(8), 0), pady=(p(6), 0))
        self._hint(settings, "支持观察视角文件；需要本机 Ansys VRLab 及可用授权。", row=2, columnspan=3, pady=(p(2), p(2)))

        self.parameters_frame = ttk.Frame(settings)
        self.parameters_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.parameters_frame.columnconfigure(0, weight=1, uniform="parameters")
        self.parameters_frame.columnconfigure(1, weight=1, uniform="parameters")
        self.delay_group = ttk.Frame(self.parameters_frame)
        self.font_group = ttk.Frame(self.parameters_frame)
        self.delay_group.columnconfigure(0, weight=1)
        self.font_group.columnconfigure(0, weight=1)
        ttk.Label(self.delay_group, text="每帧延时").grid(row=0, column=0, sticky="w", padx=(0, p(8)))
        self.delay_entry = self._track(ttk.Entry(self.delay_group, textvariable=self.delay_var, width=6, justify="right", style="Apple.TEntry"))
        self.delay_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.delay_group, text="ms", style="Hint.TLabel").grid(row=0, column=2, padx=(p(6), 0))
        ttk.Label(self.font_group, text="文字大小").grid(row=0, column=0, sticky="w", padx=(0, p(8)))
        self.font_size_entry = self._track(ttk.Entry(self.font_group, textvariable=self.font_size_var, width=6, justify="right", style="Apple.TEntry"))
        self.font_size_entry.grid(row=0, column=1, sticky="ew")
        ttk.Label(self.font_group, text="px", style="Hint.TLabel").grid(row=0, column=2, padx=(p(6), 0))
        self.parameters_frame.bind("<Configure>", self._reflow_parameters)

        self.filters_card = RoundedCard(self.page_areas["filters"].content, self.appearance, padding=12)
        self.filters_card.grid(row=0, column=0, sticky="ew")
        filter_content = self.filters_card.content
        filter_content.columnconfigure(0, weight=1)
        filter_heading = ttk.Frame(filter_content)
        filter_heading.grid(row=0, column=0, sticky="ew", pady=(0, p(8)))
        filter_heading.columnconfigure(1, weight=1)
        ttk.Label(filter_heading, text="角度筛选", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.filter_summary_label = ttk.Label(filter_heading, textvariable=self.filter_summary_var, style="Hint.TLabel")
        self.filter_summary_label.grid(row=0, column=1, sticky="e", padx=p(6))

        self.filters_frame = ttk.Frame(filter_content)
        self.filters_frame.grid(row=1, column=0, sticky="ew")
        self.filters_frame.columnconfigure(1, weight=1)
        self.filters_frame.columnconfigure(3, weight=1)
        ttk.Label(self.filters_frame, text="最小值", style="Hint.TLabel").grid(row=0, column=1, sticky="w", pady=(0, p(4)))
        ttk.Label(self.filters_frame, text="最大值", style="Hint.TLabel").grid(row=0, column=3, sticky="w", pady=(0, p(4)))
        for row, label, minimum, maximum in (
            (1, "水平 H", self.h_min_var, self.h_max_var),
            (2, "垂直 V", self.v_min_var, self.v_max_var),
        ):
            ttk.Label(self.filters_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, p(12)), pady=(0, p(6)))
            self._track(ttk.Entry(self.filters_frame, textvariable=minimum, style="Apple.TEntry", width=1)).grid(row=row, column=1, sticky="ew", pady=(0, p(6)))
            ttk.Label(self.filters_frame, text="至", style="Hint.TLabel").grid(row=row, column=2, padx=p(8), pady=(0, p(6)))
            self._track(ttk.Entry(self.filters_frame, textvariable=maximum, style="Apple.TEntry", width=1)).grid(row=row, column=3, sticky="ew", pady=(0, p(6)))
            ttk.Label(self.filters_frame, text="°", style="Hint.TLabel").grid(row=row, column=4, padx=(p(6), 0), pady=(0, p(6)))
        filter_footer = ttk.Frame(self.filters_frame)
        filter_footer.grid(row=3, column=0, columnspan=5, sticky="ew")
        filter_footer.columnconfigure(0, weight=1)
        ttk.Label(filter_footer, text="留空不限制，范围包含边界值。", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
        self.filter_reset_button = self._track(ttk.Button(filter_footer, text="清除筛选", command=self.clear_filters, style="Disclosure.TButton", takefocus=True))
        self.filter_reset_button.grid(row=0, column=1, sticky="e")

        log_page = self.page_areas["logs"].content
        log_page.rowconfigure(0, weight=1)
        self.logs_card = RoundedCard(log_page, self.appearance, padding=12)
        self.logs_card.grid(row=0, column=0, sticky="nsew")
        logs = self.logs_card.content
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(1, weight=1)
        ttk.Label(logs, text="运行日志", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, p(6)))
        self.log_text = tk.Text(
            logs, state="disabled", wrap="word", height=3, width=1, relief="flat", borderwidth=0,
            highlightthickness=0, background=c.surface, foreground=c.secondary,
            selectbackground=c.selection, selectforeground="#ffffff", insertbackground=c.text, font="TkTextFont",
            padx=0, pady=0, spacing1=p(1), spacing3=p(1),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(logs, orient="vertical", command=self.log_text.yview, style="Apple.Vertical.TScrollbar")
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(p(6), 0))
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_configure("success", foreground=c.success)
        self.log_text.tag_configure("error", foreground=c.error)
        self.log_message("准备就绪。选择或拖入一个 .OptisVR / .speos360 观察视角文件。")

        self.actions_card = RoundedCard(main, self.appearance, padding=12)
        self.actions_card.grid(row=2, column=0, sticky="ew", pady=(p(10), 0))
        actions = self.actions_card.content
        actions.columnconfigure(0, weight=1)
        self.status_label = self._hint(actions, "", row=0)
        self.status_label.configure(textvariable=self.status_var)
        self.progress_bar = ttk.Progressbar(actions, variable=self.progress_var, maximum=1, mode="determinate", style="Apple.Horizontal.TProgressbar")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(p(6), p(8)))
        controls = ttk.Frame(actions)
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(2, weight=1)
        self.open_output_button = self._track(ttk.Button(controls, text="打开输出", command=self.open_output_dir, style="Secondary.TButton", takefocus=True))
        self.open_output_button.grid(row=0, column=0)
        self.ppt_button = self._track(ttk.Button(controls, text="导出 PPT…", command=self.ask_export_ppt,
                                                style="Secondary.TButton", state="disabled", takefocus=True))
        self.ppt_button.grid(row=0, column=1, padx=(p(6), 0))
        self.cancel_button = ttk.Button(controls, text="取消", command=self.cancel_processing, state="disabled", style="Secondary.TButton", takefocus=True)
        self.cancel_button.grid(row=0, column=3, padx=(p(4), p(6)))
        self.cancel_button.grid_remove()
        self.start_button = self._track(ttk.Button(controls, text="开始生成 GIF", command=self.start_processing, style="Primary.TButton", takefocus=True))
        self.start_button.grid(row=0, column=4)
        ttk.Label(main, text=COPYRIGHT, style="Footer.TLabel").grid(row=3, column=0, sticky="e", pady=(p(5), 0))
        self.select_page("settings")

    @staticmethod
    def _hint(parent: tk.Misc, text: str, **grid_options: Any) -> ttk.Label:
        label = ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=200, anchor="w")
        label.grid(column=0, sticky="ew", **grid_options)
        # Adapt prose to the allocated width instead of widening the window.
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width)))
        return label

    def _reflow_parameters(self, event: tk.Event) -> None:
        stacked = event.width < self.appearance.px(540)
        if stacked == self._parameters_stacked:
            return
        self._parameters_stacked = stacked
        self.delay_group.grid(row=0, column=0, columnspan=2 if stacked else 1, sticky="ew", padx=(0, 0 if stacked else self.appearance.px(12)))
        self.font_group.grid(row=1 if stacked else 0, column=0 if stacked else 1, columnspan=2 if stacked else 1, sticky="ew", pady=(self.appearance.px(8) if stacked else 0, 0))

    @property
    def scroll_area(self) -> ScrollArea:
        return self.page_areas[self.page_var.get()]

    def select_page(self, name: str) -> None:
        if name not in self.page_areas:
            raise ValueError(f"Unknown page: {name}")
        focused = self.root.focus_get()
        hidden_focus = focused is not None and any(
            key != name and (str(focused) == str(area) or str(focused).startswith(str(area) + "."))
            for key, area in self.page_areas.items()
        )
        for key, area in self.page_areas.items():
            if key == name:
                area.grid(row=0, column=0, sticky="nsew")
            else:
                area.grid_remove()
        self.page_var.set(name)
        if hidden_focus:
            self.page_buttons[name].focus_set()

    def _cycle_page(self, step: int) -> str:
        names = tuple(self.page_areas)
        self.navigation.select(names[(names.index(self.page_var.get()) + step) % len(names)], animate=False)
        self.page_buttons[self.page_var.get()].focus_set()
        return "break"

    def clear_filters(self) -> None:
        if self._processing:
            return
        for variable in (self.h_min_var, self.h_max_var, self.v_min_var, self.v_max_var):
            variable.set("")

    def _update_filter_summary(self, *args: str) -> None:
        values = [variable.get().strip() for variable in (self.h_min_var, self.h_max_var, self.v_min_var, self.v_max_var)]
        try:
            parsed = [self._parse_angle(value, "角度") for value in values]
            AngleFilters(*parsed)
        except ValueError:
            self._filter_summary_invalid = True
            self.filter_summary_var.set("范围需检查")
            self.filter_tab_var.set("角度筛选 · 检查")
            self.filter_summary_label.configure(foreground=self.appearance.colors.error)
        else:
            self._filter_summary_invalid = False
            h_active, v_active = any(values[:2]), any(values[2:])
            self.filter_tab_var.set("角度筛选 · 已设" if h_active or v_active else "角度筛选")
            self.filter_summary_var.set(
                "不限角度" if not (h_active or v_active)
                else f"H {'已限制' if h_active else '不限'} · V {'已限制' if v_active else '不限'}"
            )
            self.filter_summary_label.configure(foreground=self.appearance.colors.secondary)

    def _sync_default_output(self, *args: str) -> None:
        input_text = self.input_file_var.get().strip()
        if input_text:
            source = Path(input_text)
            default = str(source.parent / (source.stem + "_GIF")) if source.suffix.lower() in NATIVE_EXTENSIONS else ""
        else:
            default = ""
        current = self.output_dir_var.get().strip()
        if not current or current == self._last_auto_output:
            self.output_dir_var.set(default)
        self._last_auto_output = default

    def _start_shortcut(self, event: tk.Event) -> str:
        self.start_processing()
        return "break"

    def _cancel_shortcut(self, event: tk.Event) -> str | None:
        if self._processing:
            self.cancel_processing()
            return "break"
        return None

    def ask_input_file(self) -> None:
        if self._processing:
            return
        selected = filedialog.askopenfilename(
            parent=self.root, title="选择 VRLab 观察视角文件（需要本机 Ansys）",
            filetypes=[("VRLab 观察视角文件", "*.OptisVR *.optisvr *.speos360")],
        )
        if selected:
            self.select_input_file(selected)

    def select_input_file(self, filename: str) -> bool:
        if self._processing or self._close_requested:
            return False
        try:
            source = Path(filename).expanduser()
            validate_native_source(source)
        except (ValueError, OSError) as exc:
            self.status_var.set(str(exc))
            self._set_status_tone("error")
            self.log_message(f"选择失败：{exc}")
            return False
        self.input_file_var.set(os.path.normpath(str(source)))
        self.select_page("settings")
        self.input_entry.xview_moveto(1)
        self.output_entry.xview_moveto(1)
        self.status_var.set(f"已选择 {source.name}，点击开始生成 GIF。")
        self._set_status_tone("accent")
        self.log_message(f"输入文件：{source}")
        self.log_message(f"输出文件夹：{self.output_dir_var.get()}")
        return True

    def _layout_drop_area(self, event: tk.Event) -> None:
        p = self.appearance.px
        w, h, r = event.width - 1, event.height - 1, p(10)
        self.drop_surface.coords(self._drop_border, 1, r, 1, 1, r, 1, w-r, 1,
                                 w, 1, w, r, w, h-r, w, h, w-r, h, r, h, 1, h, 1, h-r)
        self.drop_surface.coords(self._drop_title, p(12), p(15))
        button_width = self.input_browse_button.winfo_reqwidth()
        self.drop_surface.coords(self._drop_button_window, w-p(10), h/2)
        self.drop_surface.coords(self._drop_entry_window, p(10), p(42))
        self.drop_surface.itemconfigure(self._drop_entry_window, width=max(1, w-button_width-p(32)))
        self.drop_surface.itemconfigure(self._drop_title, width=max(1, w-button_width-p(34)))
        self._paint_drop_area()

    def _paint_drop_area(self) -> None:
        c = self.appearance.colors
        active = self._drop_hover and not self._processing
        self.drop_surface.configure(background=c.surface)
        # The native controls' rounded skins are composited over c.surface.
        # Keep the drop target on that same surface, including while dragging,
        # so their rectangular widget bounds never appear at the corners.
        self.drop_surface.itemconfigure(self._drop_border, fill=c.surface,
                                        outline=c.accent if active else c.entry_border,
                                        width=self.appearance.px(2 if active else 1))
        text = "正在生成，请稍候…" if self._processing else "松开以选择此文件" if active else "＋ 拖入 .OptisVR / .speos360 文件"
        self.drop_surface.itemconfigure(self._drop_title, text=text,
                                        fill=c.disabled_text if self._processing else c.accent)

    def _configure_drop_targets(self) -> None:
        for widget in (self.root, self.drop_surface, self.input_entry):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DropPosition>>", self._on_drag_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            widget.dnd_bind("<<Drop>>", self._on_file_drop)

    def _on_drag_enter(self, event: Any) -> str:
        acceptable = not (self._processing or self._close_requested)
        data = getattr(event, "data", "")
        if data and data != "%D":
            try:
                paths = self.root.tk.splitlist(data)
                acceptable = acceptable and len(paths) == 1 and Path(paths[0]).suffix.lower() in NATIVE_EXTENSIONS
            except tk.TclError:
                acceptable = False
        self._drop_hover = acceptable
        self._paint_drop_area()
        return COPY if acceptable else REFUSE_DROP

    def _on_drag_leave(self, event: Any) -> None:
        self._drop_hover = False
        self._paint_drop_area()

    def _on_file_drop(self, event: Any) -> str:
        self._on_drag_leave(event)
        if self._processing or self._close_requested:
            return REFUSE_DROP
        try:
            paths = self.root.tk.splitlist(event.data)
            if len(paths) != 1:
                raise ValueError("请一次拖入一个 .OptisVR 或 .speos360 视角文件。")
        except (tk.TclError, ValueError) as exc:
            self.status_var.set(str(exc) if isinstance(exc, ValueError) else "无法识别拖入的文件路径，请重新拖入。")
            self._set_status_tone("error")
            return REFUSE_DROP
        return COPY if self.select_input_file(paths[0]) else REFUSE_DROP

    def ask_output_dir(self) -> None:
        if self._processing:
            return
        selected = filedialog.askdirectory(parent=self.root, title="选择 GIF 输出文件夹", mustexist=False)
        if selected:
            self.output_dir_var.set(os.path.normpath(selected))
            self.output_entry.xview_moveto(1)
            self.log_message(f"输出文件夹：{self.output_dir_var.get()}")

    def open_output_dir(self) -> None:
        output_text = str(self._reveal_dir) if self._reveal_dir is not None else self.output_dir_var.get().strip()
        if not output_text:
            messagebox.showwarning("提示", "请先选择输出文件夹。", parent=self.root)
            return
        output_dir = Path(output_text).expanduser()
        if not output_dir.is_dir():
            messagebox.showerror("无法打开", f"输出文件夹不存在：\n{output_dir}\n\n生成 GIF 时会自动创建。", parent=self.root)
            return
        try:
            absolute_path = str(output_dir.resolve())
            if sys.platform == "win32":
                os.startfile(absolute_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", absolute_path])
            else:
                subprocess.Popen(["xdg-open", absolute_path])
        except OSError as exc:
            messagebox.showerror("打开失败", f"无法打开文件夹：{exc}", parent=self.root)

    def _clear_reveal_directory(self, *args) -> None:
        self._reveal_dir = None

    def ask_export_ppt(self) -> None:
        if self._processing or self._close_requested:
            return
        if not self._completed_gifs:
            messagebox.showwarning("导出 PPT", "请先成功生成 GIF，再导出 PowerPoint。", parent=self.root)
            return
        stem = self._completed_source.stem if self._completed_source is not None else "VRLab2GIF"
        default_path = suggested_ppt_path(self._completed_gifs[-1].parent, stem)
        dialog = PptExportDialog(self.root, self.appearance, self._completed_gifs, default_path,
                                 self._ppt_options, self._ppt_open_after)
        dialog.grab_set()
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.start_ppt_export(dialog.result)

    def start_ppt_export(self, request: PptExportRequest) -> None:
        if self._processing or self._close_requested:
            return
        self._active_job = "ppt"
        self._ppt_request = request
        self._ppt_options = request.options
        self._ppt_open_after = request.open_after
        self._cancel_event = threading.Event()
        self._pending_outcome = None
        self.progress_var.set(0)
        self.progress_bar.configure(maximum=1)
        self.status_var.set("正在导出 PPT…")
        self._set_status_tone("accent")
        self.log_message("--- 导出 PowerPoint ---")
        self.log_message(f"PPT 保存位置：{request.output_path}")
        self._set_processing(True)
        self._worker = threading.Thread(target=self._run_ppt_worker, args=(request,),
                                        name="VRLab2GIF-ppt-export", daemon=False)
        try:
            self._worker.start()
        except RuntimeError as exc:
            self._worker = None
            self._set_processing(False)
            self.status_var.set("PPT 导出启动失败。")
            self._set_status_tone("error")
            self.log_message(f"PPT 导出启动失败：{exc}")
            messagebox.showerror("PPT 导出失败", str(exc), parent=self.root)

    def _run_ppt_worker(self, request: PptExportRequest) -> None:
        try:
            result = export_gifs_to_pptx(
                request.paths, request.output_path, request.options,
                log=lambda message: self.log_queue.put(("log", message)),
                progress=lambda done, total, label: self.log_queue.put(("progress", (done, total, label))),
                cancel_event=self._cancel_event,
            )
        except ConversionCancelled as exc:
            self.log_queue.put(("cancelled", exc))
        except Exception as exc:
            self.log_queue.put(("error", exc))
        else:
            self.log_queue.put(("ppt_done", result))

    def log_message(self, message: str, clear: bool = False) -> None:
        self.log_text.configure(state="normal")
        if clear:
            self.log_text.delete("1.0", tk.END)
        tags = ("error",) if any(word in message for word in ("错误", "失败")) else ("success",) if "[成功]" in message else ()
        self.log_text.insert(tk.END, message + "\n", tags)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    @staticmethod
    def _parse_integer(value: str, label: str, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label}必须是整数。") from exc
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{label}必须在 {minimum}–{maximum} 之间。")
        return parsed

    @staticmethod
    def _parse_angle(value: str, label: str) -> float | None:
        if not value.strip():
            return None
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label}必须是有效数字。") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"{label}必须是有限数字，不能使用 NaN 或无穷大。")
        return parsed

    def start_processing(self) -> None:
        if self._processing or self._close_requested:
            return
        try:
            input_text = self.input_file_var.get().strip()
            output_text = self.output_dir_var.get().strip()
            if not input_text:
                raise ValueError("请选择或拖入一个 VRLab 视角文件。")
            if not output_text:
                self._sync_default_output()
                output_text = self.output_dir_var.get().strip()
            input_file = Path(input_text).expanduser()
            output_dir = Path(output_text).expanduser()
            validate_native_source(input_file)
            if output_dir.exists() and not output_dir.is_dir():
                raise ValueError(f"输出路径已经存在，但不是文件夹：\n{output_dir}")
            delay_ms = self._parse_integer(self.delay_var.get(), "每帧延时", 10, 655350)
            font_size = self._parse_integer(self.font_size_var.get(), "字体大小", 1, 512)
            filters = AngleFilters(
                h_min=self._parse_angle(self.h_min_var.get(), "水平角度下限"),
                h_max=self._parse_angle(self.h_max_var.get(), "水平角度上限"),
                v_min=self._parse_angle(self.v_min_var.get(), "垂直角度下限"),
                v_max=self._parse_angle(self.v_max_var.get(), "垂直角度上限"),
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("输入错误", str(exc), parent=self.root)
            return

        self.log_message("--- 开始生成 GIF ---", clear=True)
        self._completed_gifs = ()
        self._active_job = "gif"
        self._job_source = input_file
        self.log_message(f"输入文件：{input_file}")
        self.log_message(f"输出文件夹：{output_dir}")
        self.progress_var.set(0)
        self.progress_bar.configure(maximum=1)
        self.status_var.set("正在启动 Ansys VRLab…")
        self._set_status_tone("accent")
        self._cancel_event = threading.Event()
        self._pending_outcome = None
        self._set_processing(True)
        self._worker = threading.Thread(
            target=self._run_worker,
            args=(input_file, output_dir, delay_ms, font_size, filters),
            name="VRLab2GIF-converter",
            daemon=False,
        )
        try:
            self._worker.start()
        except RuntimeError as exc:
            self._worker = None
            self._set_processing(False)
            self.status_var.set("启动失败。")
            self._set_status_tone("error")
            self.log_message(f"无法启动处理线程：{exc}")
            messagebox.showerror("启动失败", str(exc), parent=self.root)

    def _run_worker(self, input_file: Path, output_dir: Path, delay_ms: int, font_size: int, filters: AngleFilters) -> None:
        # This function and its callbacks must never access Tk widgets or variables.
        try:
            result = create_native_gifs(
                input_file,
                output_dir,
                delay_ms=delay_ms,
                font_size=font_size,
                filters=filters,
                log=lambda message: self.log_queue.put(("log", message)),
                progress=lambda done, total, label: self.log_queue.put(("progress", (done, total, label))),
                cancel_event=self._cancel_event,
            )
        except ConversionCancelled as exc:
            self.log_queue.put(("cancelled", exc))
        except Exception as exc:
            self.log_queue.put(("error", exc))
        else:
            self.log_queue.put(("done", result))

    def _set_processing(self, processing: bool) -> None:
        self._processing = processing
        self._drop_hover = False
        self._paint_drop_area()
        for widget in self._editable_widgets:
            widget.configure(state="disabled" if processing else "normal")
        self.ppt_button.configure(state="normal" if not processing and self._completed_gifs else "disabled")
        self.cancel_button.configure(state="normal" if processing else "disabled")
        if processing:
            self.cancel_button.grid()
        else:
            self.cancel_button.grid_remove()

    def cancel_processing(self) -> None:
        if not self._processing or self._cancel_event.is_set():
            return
        self._cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("正在取消，等待当前操作安全结束…")
        self._set_status_tone("secondary")
        self.log_message("已请求取消，等待当前操作安全结束；未完成的文件不会保留。")

    def check_log_queue(self) -> None:
        self._poll_id = None
        # Bound each pass so a large batch of log messages cannot freeze the UI.
        for _ in range(400):
            try:
                kind, payload = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_message(str(payload))
            elif kind == "progress":
                done, total, label = payload
                self.progress_bar.configure(maximum=max(total, 1))
                self.progress_var.set(done)
                if not self._cancel_event.is_set():
                    self.status_var.set(f"{label}（{done}/{total}）")
            elif kind in ("done", "ppt_done", "cancelled", "error"):
                self._pending_outcome = (kind, payload)

        if self._worker is not None and not self._worker.is_alive():
            # A terminal event can arrive just before the worker actually exits.
            # Never destroy the window or enable a second job until it has exited.
            if self._pending_outcome is not None:
                self._worker.join()
                self._worker = None
                outcome = self._pending_outcome
                self._pending_outcome = None
                self._finish_processing(*outcome)
                if self._close_requested:
                    self._destroy()
                    return
        if self._close_requested and self._worker is None:
            self._destroy()
            return
        self._poll_id = self.root.after(100, self.check_log_queue)

    def _finish_processing(self, kind: str, payload: Any) -> None:
        self._set_processing(False)
        if kind == "done":
            self._completed_gifs = payload.output_paths
            self._completed_source = self._job_source
            self._reveal_dir = payload.output_paths[-1].parent
            self.ppt_button.configure(state="normal")
            count = len(payload.output_paths)
            self.progress_var.set(self.progress_bar.cget("maximum"))
            summary = f"生成完成：{payload.matched_count} 张图片，{count} 个 GIF。"
            self.status_var.set(summary)
            self._set_status_tone("success")
            self.log_message(summary)
        elif kind == "ppt_done":
            self._reveal_dir = payload.output_path.parent
            self.progress_var.set(self.progress_bar.cget("maximum"))
            summary = f"PPT 导出完成：{payload.slide_count} 页。"
            self.status_var.set(summary)
            self._set_status_tone("success")
            self.log_message(summary)
            if self._ppt_request is not None and self._ppt_request.open_after and not self._close_requested:
                try:
                    os.startfile(str(payload.output_path.resolve()))
                except OSError as exc:
                    self.log_message(f"PPT 已保存，自动打开失败：{exc}")
                    self.status_var.set("PPT 已保存，自动打开失败；点击“打开输出”查看。")
        elif kind == "cancelled":
            count = len(payload.output_paths)
            summary = "PPT 导出已取消，原有文件保留。" if self._active_job == "ppt" else f"已取消，保留已生成的 {count} 个 GIF。"
            self.status_var.set(summary)
            self._set_status_tone("secondary")
            self.log_message(summary)
        else:
            self.status_var.set("生成失败，请查看日志。")
            self._set_status_tone("error")
            self.log_message(f"生成失败 [{type(payload).__name__}]：{payload}")
            if not self._close_requested:
                self.select_page("logs")
                self.scroll_area.reveal(self.logs_card)
                messagebox.showerror("生成失败", f"{payload}\n\n请查看运行日志；已生成的 GIF 保留在输出文件夹中。", parent=self.root)
                self.log_text.focus_set()

    def on_close(self) -> None:
        if self._close_requested:
            return
        self._close_requested = True
        if self._worker is not None:
            self.cancel_processing()
            self.status_var.set("正在取消并关闭，等待当前操作安全结束…")
            self.root.title(f"正在关闭 · VRLab2GIF v{__version__}")
        else:
            self._destroy()

    def _destroy(self) -> None:
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.root.destroy()


def main(*, smoke_test: bool = False) -> int:
    enable_dpi_awareness()
    root = TkinterDnD.Tk()
    if smoke_test:
        root.withdraw()
    app = GifCreatorApp(root)
    if smoke_test:
        import tempfile
        try:
            root.update_idletasks()
            # Exercise the same OLE-to-Tk callback bridge in the packaged EXE.
            # This only selects a local fixture; it never launches Ansys.
            if sys.platform == "win32":
                with tempfile.TemporaryDirectory(prefix=".vrlab2gif-drop-check-", dir=Path.cwd()) as temporary:
                    source = Path(temporary) / "中文 空格 {视角}.OptisVR"
                    source.write_bytes(b"drop self-test")
                    target = str(app.drop_surface)
                    root.tk.call("tkdnd::olednd::HandleDragEnter", target,
                                 ("CF_HDROP",), ("copy",), (), 0, 0, (0,), (str(source),))
                    action = root.tk.call("tkdnd::olednd::HandleDrop", target, (), 0, 0,
                                          "CF_HDROP", (str(source),))
                    if action != COPY or Path(app.input_file_var.get()) != source or app._processing:
                        raise RuntimeError("文件拖放自检失败。")
                    gif_path = Path(temporary) / "collection_all_views.gif"
                    with Image.new("RGB", (64, 32), "black") as image:
                        image.save(gif_path, format="GIF")
                    ppt = export_gifs_to_pptx((gif_path,), Path(temporary) / "report.pptx")
                    from zipfile import ZipFile
                    with ZipFile(ppt.output_path) as archive:
                        if ppt.slide_count != 1 or archive.read("ppt/media/image1.gif") != gif_path.read_bytes():
                            raise RuntimeError("PPT 导出自检失败。")
        finally:
            app.on_close()
        print("VRLab2GIF GUI, native file-drop and PPT export smoke test passed.")
        return 0
    root.mainloop()
    return 0
