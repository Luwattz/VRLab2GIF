"""Capture only this application's client area for desktop layout review.

Run on Windows: python tools/preview_ui.py --output docs/apple-design.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tkinter as tk

from PIL import ImageGrab
from tkinterdnd2 import TkinterDnD

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vrlab2gif.app import GifCreatorApp
from vrlab2gif.appearance import enable_dpi_awareness
from vrlab2gif.ppt_dialog import PptExportDialog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--scale", type=float)
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--ppt-gif", type=Path, help="显示 PPT 设置窗口，以指定 GIF 作为已生成结果")
    pages = parser.add_mutually_exclusive_group()
    pages.add_argument("--page", choices=("settings", "filters", "logs"), default="settings")
    pages.add_argument("--filters", dest="page", action="store_const", const="filters", help="显示角度筛选页")
    pages.add_argument("--logs", dest="page", action="store_const", const="logs", help="显示运行日志页")
    args = parser.parse_args()
    enable_dpi_awareness()
    root = TkinterDnD.Tk()
    if args.scale is not None:
        root.tk.call("tk", "scaling", args.scale)
    app = GifCreatorApp(root)
    app.set_theme(args.theme)
    app.select_page(args.page)
    if args.width and args.height:
        root.geometry(f"{args.width}x{args.height}+40+40")
    else:
        root.geometry("+40+40")
    root.attributes("-topmost", True)
    root.update()
    dialog = None
    if args.ppt_gif:
        gif = args.ppt_gif.resolve()
        dialog = PptExportDialog(root, app.appearance, (gif,), gif.parent / "VRLab2GIF_report.pptx")
        dialog.attributes("-topmost", True)
    target = dialog if dialog is not None else root
    def capture() -> None:
        try:
            root.update_idletasks()
            left, top = target.winfo_rootx(), target.winfo_rooty()
            width, height = target.winfo_width(), target.winfo_height()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(bbox=(left, top, left + width, top + height)).save(args.output)
            print(json.dumps({
                "window": [width, height],
                "scale": app.appearance.scale,
                "theme": app.appearance.mode,
                "page": app.page_var.get(),
                "ppt_dialog": dialog is not None,
                "page_requested": app.scroll_area.content.winfo_reqheight(),
                "page_viewport": app.scroll_area.canvas.winfo_height(),
                "scrolling": app.scroll_area._scrolling,
                "actions_visible": app.actions_card.winfo_rooty() + app.actions_card.winfo_height() <= root.winfo_rooty() + root.winfo_height(),
                "screenshot": str(args.output.resolve()),
            }))
        finally:
            if dialog is not None:
                dialog.destroy()
            app.on_close()

    root.after(350, capture)
    root.mainloop()


if __name__ == "__main__":
    main()
