"""Opt-in, read-only PowerPoint compatibility check and slide rendering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import psutil
import pythoncom
import win32com.client
import win32process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("presentation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    before = set(psutil.pids())
    app = presentation = None
    owned = False
    pythoncom.CoInitialize()
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        servers = [p for p in psutil.process_iter(["pid", "name"])
                   if p.pid not in before and (p.info["name"] or "").lower() == "powerpnt.exe"]
        owned = len(servers) == 1
        if not owned:
            raise RuntimeError("PowerPoint reused an existing session; leaving its documents and settings untouched.")
        app.DisplayAlerts = 1
        presentation = app.Presentations.Open(str(args.presentation.resolve()), True, False, False)
        report = {"slides": int(presentation.Slides.Count),
                  "size_points": [presentation.PageSetup.SlideWidth, presentation.PageSetup.SlideHeight],
                  "pages": []}
        for i in range(1, presentation.Slides.Count + 1):
            slide = presentation.Slides(i)
            slide.Export(str((args.output / f"slide-{i}.png").resolve()), "PNG", 1600, 900)
            titles = []
            for shape in slide.Shapes:
                if shape.Name == "VRLab2GIF.BodyTitle":
                    text = shape.TextFrame.TextRange
                    titles.append({"text": text.Text, "font": text.Font.Name, "font_size": text.Font.Size,
                                   "color": text.Font.Color.RGB,
                                   "box": [shape.Left, shape.Top, shape.Width, shape.Height],
                                   "bounds": [text.BoundWidth, text.BoundHeight]})
            report["pages"].append({"slide": i, "titles": titles})
        report["master_shapes"] = [{"name": shape.Name, "text": shape.TextFrame.TextRange.Text if shape.HasTextFrame else ""}
                                   for shape in presentation.SlideMaster.Shapes]
        (args.output / "powerpoint-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        if presentation is not None:
            presentation.Close()
        if owned and app is not None and app.Presentations.Count == 0:
            app.Quit()
        app = presentation = None
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
