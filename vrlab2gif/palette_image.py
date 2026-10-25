"""Recolor fixed bitmap geometry using a cached indexed PNG palette.

Flat surfaces use exactly the same rounding as native widget colors. Updating
the palette avoids ImageTk.paste's displayed-image copy on every fade frame.
"""
from __future__ import annotations

from collections import Counter
import struct
import tkinter as tk
import zlib

from PIL import Image


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind+data) & 0xffffffff)


class PaletteImage:
    def __init__(self, master, dark: Image.Image, light: Image.Image):
        if dark.size != light.size or dark.mode != light.mode or dark.mode not in ("RGB", "RGBA"):
            raise ValueError("Palette endpoints must have matching RGB/RGBA geometry.")
        counts = Counter(zip(dark.getdata(), light.getdata()))
        # Typical rounded skins have <256 edge colors. A few rare antialiased
        # corner colors may be merged; large flat fills always stay exact.
        self.colors = tuple(pair for pair, _ in counts.most_common(256))
        mapping = {pair: index for index, pair in enumerate(self.colors)}
        for pair in counts.keys() - mapping.keys():
            mapping[pair] = min(range(len(self.colors)), key=lambda i: sum(
                (a-b)**2 for endpoint, candidate in zip(pair, self.colors[i])
                for a, b in zip(endpoint, candidate)))
        indices = bytes(mapping[pair] for pair in zip(dark.getdata(), light.getdata()))
        width, height = dark.size
        rows = b"".join(b"\0"+indices[y*width:(y+1)*width] for y in range(height))
        self.header = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        self.tail = _chunk(b"IDAT", zlib.compress(rows)) + _chunk(b"IEND", b"")
        self.rgba = dark.mode == "RGBA"
        self.photo = tk.PhotoImage(master=master, width=width, height=height)
        self.amount = None
        self.render(0.0)

    def __str__(self):
        return str(self.photo)

    def render(self, amount: float):
        if self.amount == amount:
            return
        self.amount = amount
        palette = bytes(round(a*(1-amount)+b*amount) for dark, light in self.colors
                        for a, b in zip(dark[:3], light[:3]))
        alpha = (_chunk(b"tRNS", bytes(round(dark[3]*(1-amount)+light[3]*amount)
                                       for dark, light in self.colors)) if self.rgba else b"")
        self.photo.configure(data=self.header+_chunk(b"PLTE", palette)+alpha+self.tail, format="png")
