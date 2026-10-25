"""Image conversion independent of Tkinter and its main thread."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from threading import Event
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from . import COPYRIGHT


_ANGLE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_FILENAME = re.compile(rf"^.+_Image_({_ANGLE})°_({_ANGLE})°\.png$", re.IGNORECASE)


def parse_filename(filename: str) -> tuple[float, float] | None:
    """Read H and V; equal numeric angles share a group regardless of spelling."""
    match = _FILENAME.fullmatch(filename)
    if not match:
        return None
    h, v = (float(value) for value in match.groups())
    if not (math.isfinite(h) and math.isfinite(v)):
        return None
    return (h if h else 0.0), (v if v else 0.0)


@dataclass(frozen=True)
class AngleFilters:
    h_min: float | None = None
    h_max: float | None = None
    v_min: float | None = None
    v_max: float | None = None

    def __post_init__(self) -> None:
        for name in ("h_min", "h_max", "v_min", "v_max"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError("角度范围必须是有限数值，不能使用 NaN 或无穷大。")
        for name, minimum, maximum in (
            ("水平 H", self.h_min, self.h_max),
            ("垂直 V", self.v_min, self.v_max),
        ):
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{name} 的最小角度不能大于最大角度。")

    def contains(self, h: float, v: float) -> bool:
        return (
            (self.h_min is None or h >= self.h_min)
            and (self.h_max is None or h <= self.h_max)
            and (self.v_min is None or v >= self.v_min)
            and (self.v_max is None or v <= self.v_max)
        )


@dataclass(frozen=True)
class ConversionResult:
    scanned_count: int
    skipped_count: int
    filtered_count: int
    matched_count: int
    output_paths: tuple[Path, ...]
    duration_ms: int


class ConversionCancelled(Exception):
    def __init__(self, output_paths: tuple[Path, ...] = ()) -> None:
        super().__init__("已取消生成。已完成的 GIF 会保留。")
        self.output_paths = output_paths


@dataclass(frozen=True)
class _Record:
    path: Path
    h: float
    v: float


def bundled_font_path() -> Path:
    """Locate the font inside source resources or PyInstaller's extracted bundle."""
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return resource_root / "fonts" / "arial.ttf"


def load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Prefer embedded Arial without installing it into the OS font directory."""
    candidates = [bundled_font_path()]
    if sys.platform == "win32":
        system_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend(system_fonts / name for name in ("arial.ttf", "segoeui.ttf"))
    elif sys.platform == "darwin":
        candidates.append(Path("/System/Library/Fonts/Supplemental/Arial.ttf"))
    candidates.append("DejaVuSans.ttf")
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), font_size)
        except OSError:
            continue
    return ImageFont.load_default(size=font_size)


def _make_frame(record: _Record, font: ImageFont.ImageFont) -> Image.Image:
    try:
        with Image.open(record.path) as source:
            with source.convert("RGBA") as rgba:
                draw = ImageDraw.Draw(rgba)
                # A dark outline keeps the original white label readable on light images.
                draw.text(
                    (10, 10), f"H: {record.h:.2f}° V: {record.v:g}°",
                    font=font, fill=(255, 255, 255, 255),
                    stroke_width=1, stroke_fill=(0, 0, 0, 255),
                )
                with Image.new("RGB", rgba.size, (0, 0, 0)) as background:
                    background.paste(rgba, (0, 0), rgba)
                    # GIF uses at most 256 colors. Retaining palette frames cuts memory
                    # usage relative to holding all RGB/RGBA images in memory.
                    return background.quantize(colors=256)
    except Exception as exc:
        raise ValueError(f"无法处理图片 {record.path.name}: {exc}") from exc


def _save_gif(
    frames: list[Image.Image], output: Path, duration_ms: int,
    check_cancel: Callable[[], None],
) -> None:
    """Only replace an existing result after the complete new GIF is written."""
    descriptor, temporary = tempfile.mkstemp(prefix=".vrlab2gif-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    try:
        frames[0].save(
            temporary, format="GIF", save_all=True, append_images=frames[1:],
            # Frames are fully opaque. Retaining the previous canvas lets Pillow
            # encode differences without clearing to palette index 0, which is
            # not necessarily black when each frame has its own palette.
            duration=duration_ms, loop=0, optimize=False, disposal=1,
        )
        check_cancel()
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def create_gifs(
    input_dir: Path | str,
    output_dir: Path | str,
    delay_ms: int = 300,
    font_size: int = 24,
    filters: AngleFilters | None = None,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    cancel_event: Event | None = None,
) -> ConversionResult:
    """Generate V groups (H ascending) and a collection (V descending, H ascending).

    Callbacks run on the calling thread. Cancellation is cooperative; a save in
    progress finishes to a temporary file, which is then discarded if cancelled.
    """
    if not str(input_dir).strip() or not str(output_dir).strip():
        raise ValueError("请选择输入文件夹和输出文件夹。")
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        raise ValueError(f"输入文件夹不存在或不是目录: {input_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"输出路径不是文件夹: {output_dir}")
    if isinstance(delay_ms, bool) or not isinstance(delay_ms, int) or not 10 <= delay_ms <= 655350:
        raise ValueError("每帧延时必须是 10 到 655350 之间的整数（毫秒）。")
    if isinstance(font_size, bool) or not isinstance(font_size, int) or not 1 <= font_size <= 512:
        raise ValueError("字体大小必须是 1 到 512 之间的整数。")
    filters = filters if filters is not None else AngleFilters()
    emit = log if log is not None else lambda message: None
    report = progress if progress is not None else lambda done, total, label: None
    outputs: list[Path] = []

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled(tuple(outputs))

    check_cancel()
    duration_ms = delay_ms // 10 * 10
    if duration_ms != delay_ms:
        emit(f"GIF 延时以 10 ms 为单位，实际每帧延时为 {duration_ms} ms。")
    emit(f"输入文件夹: {input_dir}")
    emit(f"输出文件夹: {output_dir}")
    emit("正在扫描并筛选 PNG 图片（仅当前文件夹）…")
    records: list[_Record] = []
    scanned = skipped = filtered = 0
    for path in sorted(input_dir.iterdir(), key=lambda value: (value.name.casefold(), value.name)):
        check_cancel()
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        scanned += 1
        angles = parse_filename(path.name)
        if angles is None:
            skipped += 1
            emit(f"[格式跳过] {path.name}")
        elif filters.contains(*angles):
            records.append(_Record(path, *angles))
        else:
            filtered += 1
    emit(f"扫描完成: {scanned} 张 PNG，格式跳过 {skipped} 张，筛选排除 {filtered} 张。")
    if not scanned:
        raise ValueError("输入文件夹中没有 PNG 图片。")
    if not records:
        raise ValueError("没有符合文件名格式及角度筛选条件的图片，未生成 GIF。")

    # Validate the whole selection before creating/replacing any output.
    emit(f"正在检查 {len(records)} 张图片的完整性和尺寸…")
    expected_size: tuple[int, int] | None = None
    for record in records:
        check_cancel()
        try:
            with Image.open(record.path) as image:
                image_size = image.size
                image.verify()
        except Exception as exc:
            raise ValueError(f"无法读取图片 {record.path.name}: {exc}") from exc
        if expected_size is None:
            expected_size = image_size
        elif image_size != expected_size:
            raise ValueError(
                f"图片尺寸不一致: {record.path.name} 为 {image_size[0]}×{image_size[1]}，"
                f"应为 {expected_size[0]}×{expected_size[1]}。请先统一所有图片尺寸。"
            )
        # PNG verify checks chunk integrity, but not the decompressed pixel
        # stream. Decode once now so a bad later image cannot replace earlier
        # results before its corruption is discovered.
        try:
            with Image.open(record.path) as image:
                image.load()
        except Exception as exc:
            raise ValueError(f"无法解码图片 {record.path.name}: {exc}") from exc

    grouped: dict[float, list[_Record]] = defaultdict(list)
    for record in records:
        grouped[record.v].append(record)
    jobs: list[tuple[Path, list[_Record]]] = []
    for v in sorted(grouped, reverse=True):
        ordered = sorted(grouped[v], key=lambda record: (record.h, record.path.name))
        jobs.append((output_dir / f"vertical_angle_{v}.gif", ordered))
    jobs.append((
        output_dir / "collection_all_angles.gif",
        sorted(records, key=lambda record: (-record.v, record.h, record.path.name)),
    ))

    font = load_font(font_size)
    check_cancel()
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(records) * 2
    completed = 0
    report(0, total, "准备生成")
    for output, ordered in jobs:
        check_cancel()
        emit(f"正在生成 {output.name}（{len(ordered)} 帧）…")
        frames: list[Image.Image] = []
        try:
            for record in ordered:
                check_cancel()
                frames.append(_make_frame(record, font))
                completed += 1
                report(completed, total, output.name)
            check_cancel()
            _save_gif(frames, output, duration_ms, check_cancel)
            outputs.append(output)
            emit(f"[成功] {output.name}")
        finally:
            for frame in frames:
                frame.close()
    check_cancel()
    emit(f"已完成：{len(records)} 张图片，{len(outputs)} 个 GIF。")
    emit(COPYRIGHT)
    return ConversionResult(scanned, skipped, filtered, len(records), tuple(outputs), duration_ms)


def create_sequence_gif(
    paths: list[Path], output_dir: Path, delay_ms: int = 300,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    cancel_event: Event | None = None,
) -> ConversionResult:
    """Encode ordered native views without inventing missing H/V metadata."""
    if not paths:
        raise ValueError("VRLab 没有导出任何视角图片。")
    if isinstance(delay_ms, bool) or not isinstance(delay_ms, int) or not 10 <= delay_ms <= 655350:
        raise ValueError("每帧延时必须是 10 到 655350 之间的整数（毫秒）。")
    emit = log or (lambda message: None)
    report = progress or (lambda done, total, label: None)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled()

    expected_size = None
    for path in paths:
        check_cancel()
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                if expected_size is not None and image.size != expected_size:
                    raise ValueError("所有导出视角必须具有相同尺寸。")
                expected_size = image.size
        except Exception as exc:
            raise ValueError(f"无法读取导出图片 {path.name}: {exc}") from exc
    duration = delay_ms // 10 * 10
    if duration != delay_ms:
        emit(f"GIF 延时以 10 ms 为单位，实际每帧延时为 {duration} ms。")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "collection_all_views.gif"
    frames = []
    report(0, len(paths), "正在合成视角")
    try:
        for index, path in enumerate(paths, 1):
            check_cancel()
            with Image.open(path) as image, image.convert("RGBA") as rgba:
                with Image.new("RGB", image.size, (0, 0, 0)) as background:
                    background.paste(rgba, (0, 0), rgba)
                    frames.append(background.quantize(colors=256))
            report(index, len(paths), output.name)
        check_cancel()
        _save_gif(frames, output, duration, check_cancel)
    finally:
        for frame in frames:
            frame.close()
    emit(f"[成功] {output.name}（{len(paths)} 个视角）")
    return ConversionResult(len(paths), 0, 0, len(paths), (output,), duration)
