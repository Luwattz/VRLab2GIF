"""Recover observer angles omitted from VRLab 2024 R1 COM export filenames.

This reads only the bounded, compressed XML header, never image payloads. The
supported header layout and index mapping were checked against Ansys's 2020.2
and 2024.1 samples and all 35 manually exported AR views. Unknown layouts keep
the index-only fallback; they must not produce guessed angle labels.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zlib

from .core import parse_filename

_SIGNATURE = b"OPTIS - OPTIS_VR file v"
_MAX_HEADER = 4 * 1024 * 1024


class AngleMetadataUnavailable(ValueError):
    """The source cannot be mapped to COM image indices with confidence."""


@dataclass(frozen=True)
class ObserverAxes:
    horizontal: tuple[float, ...]
    vertical: tuple[float, ...]


def read_observer_axes(source: Path) -> ObserverAxes:
    """Read the verified rectangular observer layout; return degrees, not indices."""
    try:
        with source.open("rb") as stream:
            if stream.read(len(_SIGNATURE)) != _SIGNATURE:
                raise ValueError("无法识别视角文件头")
            version, name_size = struct.unpack("<fI", stream.read(8))
            if version != 1.0 or name_size != len(b"MultiPictures OptisVR"):
                raise ValueError("尚未验证的视角文件头版本")
            if stream.read(name_size) != b"MultiPictures OptisVR":
                raise ValueError("不是已支持的多视角数据结构")
            layout, flags, xml_size, repeated_size, packed_size = struct.unpack("<fIIII", stream.read(20))
            if layout != 2.0 or flags != 0:
                raise ValueError("尚未验证的视角元数据布局")
            if not (0 < xml_size == repeated_size <= _MAX_HEADER and 0 < packed_size <= _MAX_HEADER):
                raise ValueError("视角元数据长度无效")
            packed = stream.read(packed_size)
            if len(packed) != packed_size:
                raise ValueError("视角元数据不完整")
        decoder = zlib.decompressobj()
        xml = decoder.decompress(packed, xml_size + 1)
        if len(xml) != xml_size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("视角元数据解压校验失败")
        if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
            raise ValueError("不支持包含实体声明的视角元数据")
        root = ET.fromstring(xml)
        indexer = root.find("PictureIndexerHeader")
        if (root.tag != "Header_OptisVR" or root.find("SimulationObserver") is None
                or root.findtext("PictureFormat") != "0" or indexer is None
                or indexer.findtext("version") not in ("1.000000", "1")
                or indexer.findtext("IndexerType") != "1" or indexer.findtext("ZenithMode") != "1"
                or indexer.findtext("ThetaAnglesStoredFromBottomToTop", "true").lower() != "true"):
            raise ValueError("尚未验证的观察视角索引类型、立体模式或垂直方向")

        def axis(name: str, maximum: float) -> tuple[float, ...]:
            radians = tuple(float(node.text) for node in indexer.findall(f"{name}/Value"))
            if not radians or not all(math.isfinite(x) and abs(x) <= maximum + 1e-6 for x in radians):
                raise ValueError("角度表为空或包含无效数值")
            # Match File > Export all views' two-decimal degree labels. Refuse
            # grids whose distinct angles would collapse at that precision.
            degrees = tuple(round(math.degrees(x), 2) or 0.0 for x in radians)
            if len(set(degrees)) != len(degrees):
                raise ValueError("角度间距小于两位小数的标注精度")
            if any(a >= b for a, b in zip(radians, radians[1:])):
                raise ValueError("尚未验证的角度表排序")
            return degrees

        axes = ObserverAxes(axis("PhiList", math.pi), axis("ThetaList", math.pi / 2))
        count = len(axes.horizontal) * len(axes.vertical)
        if count > 100_000:
            raise ValueError("视角网格超过元数据读取上限")
        order = tuple(int(node.text) for node in indexer.findall("PictureOrder/Value"))
        if int(root.findtext("NumberOfPicture", "0")) != count or order != tuple(range(count)):
            raise ValueError("尚未验证的非完整网格或图片重排")
        return axes
    except (OSError, ValueError, TypeError, struct.error, zlib.error, ET.ParseError) as exc:
        raise AngleMetadataUnavailable(str(exc)) from exc


def restore_export_angles(source: Path, frames_dir: Path, log=None) -> bool:
    """Rename only temporary COM exports using validated H/V tables from source."""
    paths = list(frames_dir.glob("*.png"))
    if paths and all(parse_filename(path.name) is not None for path in paths):
        return True
    try:
        axes = read_observer_axes(source)
        pattern = re.compile(rf"^{re.escape(source.stem)}_Image_(\d+)_(\d+)\.png$", re.I)
        expected = {(h, v) for h in range(len(axes.horizontal)) for v in range(len(axes.vertical))}
        found = set()
        renames = []
        for path in paths:
            match = pattern.fullmatch(path.name)
            if not match:
                raise AngleMetadataUnavailable("导出文件名与已验证的索引格式不一致")
            h, v = map(int, match.groups())
            if (h, v) not in expected or (h, v) in found:
                raise AngleMetadataUnavailable("导出视角索引越界或重复")
            found.add((h, v))
            target = path.with_name(f"{source.stem}_Image_{axes.horizontal[h]:.2f}°_{axes.vertical[v]:.2f}°.png")
            if target.exists():
                raise AngleMetadataUnavailable("临时目录中已有相同角度的图片")
            renames.append((path, target))
        if found != expected:
            raise AngleMetadataUnavailable("导出数量与源文件角度网格不一致")
    except AngleMetadataUnavailable as exc:
        if log:
            log(f"无法从源文件安全恢复 H/V 角度：{exc}。保留原始导出名称。")
        return False
    # All names and indices are checked before any temporary PNG is renamed.
    for path, target in renames:
        path.rename(target)
    if log:
        log(f"已从源文件角度表恢复 {len(renames)} 个视角的 H/V 角度（弧度转换为度），启用角度标注、筛选和分组。")
    return True
