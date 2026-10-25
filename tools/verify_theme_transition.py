"""Inspect only this app's window, including real Windows caption colors."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time

from PIL import ImageGrab
from tkinterdnd2 import TkinterDnD

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vrlab2gif.app import GifCreatorApp
from vrlab2gif.appearance import enable_dpi_awareness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    enable_dpi_awareness()
    root = TkinterDnD.Tk()
    app = GifCreatorApp(root)
    root.geometry("+40+40")
    root.update()
    fade = app.appearance.transition
    report = {"frames": []}
    user, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    user.GetParent.argtypes, user.GetParent.restype = [wintypes.HWND], wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    hwnd = user.GetParent(root.winfo_id()) or root.winfo_id()
    try:
        for amount in (0, .2, .4, .6, .8, 1):
            fade.render(amount)
            root.update_idletasks()
            item = {"alpha": amount, "background": app.appearance.colors.background,
                    "text": app.appearance.colors.text}
            bounds = wintypes.RECT()
            assert user.GetWindowRect(hwnd, ctypes.byref(bounds))
            dwm.DwmFlush()
            picture = ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom))
            item["caption_colors_supported"] = getattr(root, "_vrlab_caption_colors_supported", False)
            if item["caption_colors_supported"]:
                # DWM accepts caption-color setters on this Windows build but
                # returns E_INVALIDARG for querying attributes 35/36. Verify the
                # actual painted caption against the client-area background.
                caption_height = root.winfo_rooty()-bounds.top
                native_pixel = picture.getpixel((picture.width//2, caption_height//2))[:3]
                client_pixel = picture.getpixel((picture.width//2, caption_height+10))[:3]
                expected = tuple(int(item["background"][i:i+2], 16) for i in (1, 3, 5))
                assert max(abs(a-b) for a, b in zip(native_pixel, expected)) <= 2, (native_pixel, expected)
                assert max(abs(a-b) for a, b in zip(client_pixel, expected)) <= 2, (client_pixel, expected)
                item["native_caption_matches_client_pixels"] = True
            picture.save(args.output / f"frame-{round(amount*100):03d}.png")
            report["frames"].append(item)
        app.set_theme("dark")
        fade.motion_enabled = app.theme_switch.motion_enabled = True
        start = time.perf_counter()
        app.theme_switch.select("light")
        while fade.timer_id is not None and time.perf_counter()-start < 5:
            root.update()
            time.sleep(.003)
        report["elapsed_ms"] = round((time.perf_counter()-start)*1000)
        assert fade.alpha == 1 and fade.timer_id is None
        (args.output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        app.on_close()


if __name__ == "__main__":
    main()
