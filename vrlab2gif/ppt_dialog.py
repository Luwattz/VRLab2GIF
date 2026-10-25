"""PowerPoint export settings for the generated GIFs only."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from .appearance import AppleAppearance, window_work_area
from .ppt import PptOptions, _title_for


@dataclass(frozen=True)
class PptExportRequest:
    paths: tuple[Path, ...]
    output_path: Path
    options: PptOptions
    open_after: bool = False


def suggested_ppt_path(directory: Path, stem: str) -> Path:
    base = directory / (stem + "_report.pptx")
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = base.with_stem(base.stem + f"_{counter:02d}")
        counter += 1
    return candidate


class PptExportDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, appearance: AppleAppearance,
                 paths: tuple[Path, ...], default_path: Path,
                 options: PptOptions | None = None, open_after=False):
        super().__init__(parent)
        self.withdraw()
        self.appearance = appearance
        self.paths = tuple(paths)
        self.default_path = default_path
        self.result: PptExportRequest | None = None
        options = options or PptOptions()
        self.title_var = tk.StringVar(self, value=options.title)
        self.footer_var = tk.StringVar(self, value=options.footer)
        self.path_var = tk.StringVar(self, value=str(default_path))
        self.collections_var = tk.BooleanVar(self, value=options.collections_only)
        self.open_var = tk.BooleanVar(self, value=open_after)
        self.error_var = tk.StringVar(self)
        self.title("导出 PPT · VRLab2GIF")
        self.transient(parent)
        self.configure(background=appearance.colors.surface)
        self.resizable(False, False)
        p = appearance.px
        outer = ttk.Frame(self, padding=p(16))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        ttk.Label(outer, text="导出 PowerPoint", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, p(6)))
        note = ttk.Label(outer, text=f"使用上次生成的 {len(paths)} 个 GIF，每个 GIF 一页，保留完整动画。", style="Hint.TLabel")
        note.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, p(10)))
        self.title_entry = ttk.Entry(outer, textvariable=self.title_var, style="Apple.TEntry", width=42)
        self.footer_entry = ttk.Entry(outer, textvariable=self.footer_var, style="Apple.TEntry")
        for row, label, entry in ((2, "报告标题", self.title_entry), (3, "页脚名称", self.footer_entry)):
            ttk.Label(outer, text=label).grid(row=row, column=0, sticky="w", padx=(0, p(10)))
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=(0, p(8)))
        ttk.Label(outer, text="导出内容").grid(row=4, column=0, sticky="nw", padx=(0, p(10)))
        choices = ttk.Frame(outer)
        choices.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(0, p(8)))
        ttk.Radiobutton(choices, text="全部已生成的 GIF", value=False, variable=self.collections_var, style="Apple.TRadiobutton").pack(anchor="w")
        collections = sum(path.stem in ("collection_all_angles", "collection_all_views") for path in paths)
        ttk.Radiobutton(choices, text=f"仅合集（{collections} 页）", value=True, variable=self.collections_var, style="Apple.TRadiobutton",
                        state="normal" if collections else "disabled").pack(anchor="w", pady=(p(3), 0))
        ttk.Label(outer, text="保存到").grid(row=5, column=0, sticky="w", padx=(0, p(10)))
        self.path_entry = ttk.Entry(outer, textvariable=self.path_var, style="Apple.TEntry")
        self.path_entry.grid(row=5, column=1, sticky="ew", pady=(0, p(8)))
        ttk.Button(outer, text="更改…", command=self.browse, style="Secondary.TButton").grid(row=5, column=2, padx=(p(6), 0), pady=(0, p(8)))
        ttk.Checkbutton(outer, text="完成后打开 PPT", variable=self.open_var, style="Apple.TCheckbutton").grid(row=6, column=1, columnspan=2, sticky="w", pady=(0, p(8)))
        details = "LumiDyna 版式：16:9 白底；微软雅黑 24 pt 橙色标题；\n母版上下横线、页脚和自动页码。GIF 等比例居中，不裁切。\n在桌面 PowerPoint 的幻灯片放映中查看动画。"
        ttk.Label(outer, text=details, style="Hint.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, p(5)))
        ttk.Label(outer, text="新导出默认使用未占用的文件名；自选同名文件会在成功后替换。", style="Hint.TLabel").grid(row=8, column=0, columnspan=3, sticky="w")
        ttk.Label(outer, textvariable=self.error_var, foreground=appearance.colors.error, wraplength=p(510)).grid(row=9, column=0, columnspan=3, sticky="ew", pady=p(5))
        actions = ttk.Frame(outer)
        actions.grid(row=10, column=0, columnspan=3, sticky="ew")
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="恢复默认", command=self.restore_defaults, style="Disclosure.TButton").grid(row=0, column=0)
        ttk.Button(actions, text="取消", command=self.destroy, style="Secondary.TButton").grid(row=0, column=2, padx=(0, p(6)))
        self.export_button = ttk.Button(actions, text="导出 PPT", command=self.confirm, style="Primary.TButton")
        self.export_button.grid(row=0, column=3)
        self.bind("<Escape>", lambda event: self.destroy())
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, screen_w, screen_h = window_work_area(parent)
        x = max(left, min(parent.winfo_rootx() + (parent.winfo_width()-width)//2, left+screen_w-width))
        y = max(top, min(parent.winfo_rooty() + (parent.winfo_height()-height)//2, top+screen_h-height))
        self.geometry(f"{width}x{height}{x:+d}{y:+d}")
        self.deiconify()
        self.update_idletasks()
        appearance._native_titlebar(self)
        self.path_entry.icursor(tk.END)
        self.path_entry.xview_moveto(1)
        self.title_entry.selection_range(0, tk.END)
        self.title_entry.focus_set()

    def browse(self):
        current = Path(self.path_var.get())
        selected = filedialog.asksaveasfilename(parent=self, title="保存 PowerPoint",
                                               initialdir=str(current.parent), initialfile=current.name,
                                               defaultextension=".pptx", filetypes=[("PowerPoint", "*.pptx")])
        if selected:
            self.path_var.set(selected)
            self.path_entry.xview_moveto(1)

    def restore_defaults(self):
        self.title_var.set("视角合成结果")
        self.footer_var.set(PptOptions().footer)
        self.collections_var.set(False)
        self.path_var.set(str(self.default_path))
        self.open_var.set(False)
        self.error_var.set("")

    def confirm(self):
        try:
            options = PptOptions(self.title_var.get(), self.footer_var.get(), self.collections_var.get())
            path_text = self.path_var.get().strip()
            if not path_text:
                raise ValueError("请选择 PPT 保存位置。")
            path = Path(path_text).expanduser()
            if path.suffix.lower() != ".pptx":
                raise ValueError("请使用 .pptx 文件扩展名。")
            selected = tuple(p for p in self.paths if not options.collections_only or p.stem in ("collection_all_angles", "collection_all_views"))
            if not selected:
                raise ValueError("没有可导出的合集 GIF。")
            if any(not p.is_file() for p in selected):
                raise ValueError("部分 GIF 已被移动或删除，请重新生成后导出。")
            for gif in selected:
                _title_for(gif, options)
        except (ValueError, OSError) as exc:
            self.error_var.set(str(exc))
            return
        self.result = PptExportRequest(selected, path, options, self.open_var.get())
        self.destroy()
