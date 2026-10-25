"""Developer probe: export workspace sample files in a fresh VRLab instance."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import psutil
import pythoncom
import win32com.client
import win32con
import win32gui
import win32process


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "samples" / "ansys-vrlab" / "api-probe"
    destination.mkdir(exist_ok=True)
    before = set(win32process.EnumProcesses())
    pythoncom.CoInitialize()
    app = None
    owned = None
    report = []
    try:
        app = win32com.client.DispatchEx("{3344F009-C61A-4C1D-9684-53D3AE8557BD}")
        member = app.GetPID
        pid = int(member() if callable(member) else member)
        print(json.dumps({"pid": pid, "fresh_process": pid not in before}), flush=True)
        if pid in before:
            raise RuntimeError("VRLab returned an existing process; leaving that session untouched.")
        owned = psutil.Process(pid)
        if Path(owned.exe()).name.lower() != "vrlab.exe":
            owned = None
            raise RuntimeError("Unexpected COM server executable.")
        app.SetAlwaysOnTop(False)
        app.Show(True)
        for source in (
            root / "samples" / "ansys-vrlab" / "test_07_VRLab_export.OptisVR",
            Path(r"C:\Program Files\ANSYS Inc\v241\CEI\ensight241\site_preferences\environmaps\garden.hdr"),
            Path(r"C:\Program Files\ANSYS Inc\v241\Optical Products\Viewers\Resources\AmbientSource\stars.exr"),
        ):
            output = destination / source.stem
            output.mkdir(exist_ok=True)
            item = {"source": str(source)}
            print("OPEN " + source.name, flush=True)
            item["open"] = app.OpenFile(str(source))
            print("OPEN RESULT " + str(item["open"]), flush=True)
            if item["open"]:
                item["all_views"] = app.ExportAllObserverImages(str(output) + "\\", 1)
                item["current_view"] = app.ExportObserverImage(str(output / "current.png"))
                item["files"] = [{"name": p.name, "bytes": p.stat().st_size} for p in output.glob("*.png")]
            report.append(item)
            (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(item), flush=True)
    finally:
        app = None
        pythoncom.CoUninitialize()
        if owned is not None and owned.is_running():
            def close_window(hwnd: int, extra: object) -> None:
                if win32process.GetWindowThreadProcessId(hwnd)[1] == owned.pid:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            win32gui.EnumWindows(close_window, None)
            try:
                owned.wait(timeout=3)
            except psutil.TimeoutExpired:
                owned.terminate()
                owned.wait(timeout=3)


if __name__ == "__main__":
    main()
