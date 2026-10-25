"""Present a theme change as one client-area frame on Windows.

The temporary owned surfaces do not activate or intercept input. Only the body
is composited; both header selectors stay live. Backing widgets are painted once
per endpoint instead of broadcasting a ttk theme change on every frame.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import tkinter as tk

from PIL import Image

if sys.platform == "win32":
    # Load native capture support at startup, not during the first click.
    import win32gui
    import win32ui


def capture_client(root) -> Image.Image:
    """Print only our own Tk client window, independent of overlapping windows."""
    user = ctypes.windll.user32
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user.PrintWindow.restype = wintypes.BOOL
    hwnd = int(root.wm_frame(), 0)
    width, height = root.winfo_width(), root.winfo_height()
    dc = win32gui.GetDC(hwnd)
    source = win32ui.CreateDCFromHandle(dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    previous = None
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        previous = memory.SelectObject(bitmap)
        if not user.PrintWindow(hwnd, memory.GetSafeHdc(), 3):
            raise OSError("Cannot capture this application's client area")
        return Image.frombytes("RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX")
    finally:
        if previous is not None:
            memory.SelectObject(previous)
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, dc)


class _LayerFrame:
    """Owned, input-transparent native surface with one reusable DIB buffer."""
    def __init__(self, root):
        user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        owner = int(root.wm_frame(), 0)
        self.hwnd = win32gui.CreateWindowEx(0x80000 | 0x20 | 0x08000000 | 0x80,
                                           "STATIC", "", 0x80000000, 0, 0, 1, 1, owner, 0, 0, None)
        self.user, self.gdi = user, gdi
        gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [wintypes.HDC], wintypes.HDC
        gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        gdi.CreateDIBSection.restype = wintypes.HBITMAP
        gdi.SelectObject.argtypes, gdi.SelectObject.restype = [wintypes.HDC, wintypes.HANDLE], wintypes.HANDLE
        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi.DeleteDC.argtypes = [wintypes.HDC]
        user.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_void_p,
                                             ctypes.c_void_p, wintypes.HDC, ctypes.c_void_p,
                                             wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dc = gdi.CreateCompatibleDC(None)
        if not self.dc:
            win32gui.DestroyWindow(self.hwnd)
            raise ctypes.WinError()
        self.bitmap = self.previous = None
        self.size = None
        self.shown = False

    def draw(self, image, position):
        self.position = position
        width, height = image.size
        if self.size != image.size:
            if self.bitmap:
                self.gdi.SelectObject(self.dc, self.previous)
                self.gdi.DeleteObject(self.bitmap)
            class Header(ctypes.Structure):
                _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                            ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                            ("bytes", wintypes.DWORD), ("x", wintypes.LONG), ("y", wintypes.LONG),
                            ("colors", wintypes.DWORD), ("important", wintypes.DWORD)]
            header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0)
            self.bits = ctypes.c_void_p()
            self.bitmap = self.gdi.CreateDIBSection(self.dc, ctypes.byref(header), 0, ctypes.byref(self.bits), None, 0)
            if not self.bitmap:
                raise ctypes.WinError()
            self.previous = self.gdi.SelectObject(self.dc, self.bitmap)
            self.size = image.size
        pixels = image.convert("RGBA").tobytes("raw", "BGRA")
        ctypes.memmove(self.bits, pixels, len(pixels))
        point, source = wintypes.POINT(*position), wintypes.POINT(0, 0)
        size = wintypes.SIZE(width, height)
        blend = (ctypes.c_ubyte*4)(0, 0, 255, 1)
        if not self.user.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(point), ctypes.byref(size),
                                             self.dc, ctypes.byref(source), 0, ctypes.byref(blend), 2):
            raise ctypes.WinError()
        if not self.shown:
            win32gui.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
            self.shown = True

    def opacity(self, value):
        """Let DWM blend the unchanged source buffer over the live endpoint."""
        point, source = wintypes.POINT(*self.position), wintypes.POINT(0, 0)
        size = wintypes.SIZE(*self.size)
        blend = (ctypes.c_ubyte*4)(0, 0, value, 1)
        if not self.user.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(point), ctypes.byref(size),
                                             self.dc, ctypes.byref(source), 0, ctypes.byref(blend), 2):
            raise ctypes.WinError()

    def destroy(self):
        if self.hwnd:
            if win32gui.IsWindow(self.hwnd):
                win32gui.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.bitmap:
            self.gdi.SelectObject(self.dc, self.previous)
            self.gdi.DeleteObject(self.bitmap)
            self.bitmap = None
        if self.dc:
            self.gdi.DeleteDC(self.dc)
            self.dc = None


class ThemeScene:
    def __init__(self, appearance, main, header, pages, paint_header):
        self.appearance, self.root = appearance, appearance.root
        self.main, self.header, self.pages, self.paint_header = main, header, pages, paint_header
        self.overlay = None
        self.base = None
        self.active = False
        self.last_error = None
        tag = f"VRThemeInput{id(self):x}"
        self.root.bind_class(tag, "<ButtonPress-1>", self._input)
        self.root.bind_class(tag, "<KeyPress>", self._input)
        self.root.bind_class(tag, "<MouseWheel>", self._input)
        self.root.bind_class(tag, "<FocusIn>", self._input)

        def attach(widget):
            widget.bindtags((tag, *widget.bindtags()))
            for child in widget.winfo_children():
                attach(child)
        attach(main)
        self.root.bind("<Configure>", self._configure, add="+")
        self.root.bind("<Unmap>", self._unmap, add="+")

    def _input(self, event):
        path, header = str(event.widget), str(self.header)
        if self.active and path != header and not path.startswith(header+"."):
            self.appearance.transition.finish()

    def _configure(self, event):
        if event.widget is self.root and self.active:
            geometry = (self.root.winfo_rootx(), self.root.winfo_rooty(),
                        self.root.winfo_width(), self.root.winfo_height())
            if geometry != self.geometry:
                self.appearance.transition.finish()

    def _unmap(self, event):
        if event.widget is self.root and self.active:
            self.appearance.transition.finish()

    def prepare(self, target):
        if self.active:
            return True
        if sys.platform != "win32" or not self.root.winfo_viewable():
            return False
        from .appearance import PALETTES
        appearance = self.appearance
        old_colors, old_amount = appearance.colors, appearance.blend
        self.root.update_idletasks()
        self.geometry = (self.root.winfo_rootx(), self.root.winfo_rooty(),
                         self.root.winfo_width(), self.root.winfo_height())
        x, y, width, height = self.geometry
        self.top = self.pages.winfo_rooty()-y
        try:
            source = capture_client(self.root)
            self.base = _LayerFrame(self.root)
            self.overlay = _LayerFrame(self.root)
            self.overlay.draw(source, (x, y))
            # Hide the one-time target paint behind the current visual frame.
            appearance._freeze_caption = True
            appearance._present(PALETTES[target], float(target == "light"), endpoint=True)
            self.root.update_idletasks()
            destination = capture_client(self.root)
            start = source.crop((0, self.top, width, height))
            appearance.colors, appearance.blend = old_colors, old_amount
            appearance._freeze_caption = False
            self.paint_header()
            self.root.update_idletasks()
            # An opaque destination layer also covers gaps/margins whose live
            # parent background belongs to the independently animated header.
            self.base.draw(destination.crop((0, self.top, width, height)), (x, y+self.top))
            self.overlay.draw(start, (x, y+self.top))
            win32gui.SetWindowPos(self.overlay.hwnd, 0, 0, 0, 0, 0, 0x13)
            self.source_amount = old_amount
            self.active = True
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            appearance._freeze_caption = False
            self.stop()
            return False

    def render(self, amount):
        # Source pixels are uploaded once. DWM composites the whole body with
        # one opacity; no per-frame bitmap copy or per-widget color broadcast.
        opacity = round(255*(1-amount if self.source_amount == 0 else amount))
        self.overlay.opacity(opacity)
        self.paint_header()

    def stop(self):
        self.active = False
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except tk.TclError:
                pass
        self.overlay = None
        if self.base is not None:
            self.base.destroy()
            self.base = None

    def close(self):
        self.stop()
