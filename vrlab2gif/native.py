"""Isolated VRLab COM export followed by the ordinary GIF encoder.

Only observer view sets are supported by ExportAllObserverImages. Immersive
panoramas need a separate camera renderer and must not be advertised as supported.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Event
import time
from typing import Callable

from .core import (AngleFilters, ConversionCancelled, ConversionResult,
                   create_gifs, create_sequence_gif, parse_filename)
from .observer import restore_export_angles

NATIVE_EXTENSIONS = {".optisvr", ".speos360"}


class VRLabRegistrationError(RuntimeError):
    """The current user cannot resolve a usable VRLab automation server."""

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        message = (
            "未检测到可用的 Ansys VRLab 自动化（COM）注册。\n"
            "已安装 Speos、能手动打开视角文件，也可能尚未完成自动化注册。\n\n"
            "方法一：完成一次注册\n"
            "1. 保存工作并关闭所有 VRLab 窗口。\n"
            "2. 在要使用的 Speos 版本安装目录中找到 VRLab.exe"
            "（通常位于 Optical Products\\Viewers），右键“以管理员身份运行”一次。\n"
            "3. 等待主界面完整打开后正常退出，再回本程序点击“开始生成 GIF”重试。\n"
            "注册后可正常以普通用户权限运行本程序，无需每次提权。\n\n"
            "方法二：使用 PNG 文件夹\n"
            "没有管理员权限时，可请 IT 协助注册；也可在 VRLab 中手动导出带 H/V 角度的 PNG，"
            "点击本程序“PNG 文件夹…”直接生成 GIF，无需 COM 注册。\n"
            "PNG 命名示例：demo_Image_-30°_10°.png。"
        )
        if detail:
            message += f"\n\n检查信息：{detail}"
        super().__init__(message)


def check_native_registration() -> tuple[str, Path]:
    """Read registration only; never activate COM, elevate or write registry keys."""
    if sys.platform != "win32":
        raise RuntimeError("VRLab 文件直接转换需要 Windows 和已安装的 Ansys VRLab。")
    return _registered_server()


def validate_native_source(source: Path) -> None:
    if source.is_dir():
        raise ValueError("不支持文件夹输入，请选择 .OptisVR 或 .speos360 视角文件。")
    if not source.is_file():
        raise ValueError(f"输入文件不存在：{source}")
    if source.suffix.lower() not in NATIVE_EXTENSIONS:
        raise ValueError(
            "直接转换目前支持 .OptisVR / .speos360 中已有的观察视角。\n"
            "XMP、HDR、EXR、PIC 及沉浸式全景需要另外的渲染流程，当前版本尚不支持。"
        )


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _registered_server() -> tuple[str, Path]:
    """Read registration without registering or modifying an Ansys installation."""
    import winreg
    # HKCR is Windows' effective merged per-user/per-machine view. A ProgID
    # and its CLSID need not have been registered in the same backing hive.
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            access = winreg.KEY_READ | view
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HDRIViewer.Application\CLSID", 0, access) as key:
                clsid = winreg.QueryValue(key, None)
            if not isinstance(clsid, str) or not clsid.strip():
                continue
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32", 0, access) as key:
                command = winreg.QueryValue(key, None)
            if not isinstance(command, str):
                continue
            match = re.match(r'^"([^"]+)"|^(.+?\.exe)(?:\s|$)', command.strip(), re.I)
            if match:
                executable = Path(os.path.expandvars(match.group(1) or match.group(2)))
                if executable.name.lower() == "vrlab.exe" and executable.is_file():
                    return clsid, executable.resolve()
        except OSError:
            continue
    raise VRLabRegistrationError()


def _is_registration_error(error: Exception) -> bool:
    code = getattr(error, "hresult", None)
    if code is None and error.args:
        code = error.args[0]
    return isinstance(code, int) and (code & 0xffffffff) in (0x80040154, 0x800401F3)


def _owned_process(identity: dict):
    """Verify PID, creation time and full executable path before touching it."""
    import psutil
    try:
        if not identity or not identity.get("pid"):
            return None
        process = psutil.Process(int(identity["pid"]))
        if (abs(process.create_time() - float(identity["created"])) < 0.001
                and os.path.normcase(process.exe()) == os.path.normcase(identity["executable"])
                and Path(process.exe()).name.lower() == "vrlab.exe"):
            return process
    except (psutil.Error, KeyError, ValueError, TypeError):
        pass
    return None


def _close_owned(identity: dict) -> None:
    import psutil
    process = _owned_process(identity)
    if process is None:
        return
    import win32con
    import win32gui
    import win32process

    def close_window(hwnd, extra):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == process.pid:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

    try:
        win32gui.EnumWindows(close_window, None)
        process.wait(timeout=2)
    except psutil.TimeoutExpired:
        process = _owned_process(identity)
        if process is not None:
            process.terminate()
            process.wait(timeout=3)
    except psutil.NoSuchProcess:
        pass


def export_helper(job_path: Path) -> int:
    """Private subprocess entry point; the Tk process never performs COM calls."""
    job = _read_json(job_path)
    result_path = job_path.parent / "result.json"
    owner_path = job_path.parent / "owner.json"
    status_path = job_path.parent / "status.json"
    app = None
    initialized = False
    owner = {}
    try:
        if sys.platform != "win32":
            raise RuntimeError("VRLab 文件直接转换需要 Windows 和已安装的 Ansys VRLab。")
        import psutil
        import pythoncom
        import win32com.client
        source = Path(job["source"])
        validate_native_source(source)
        clsid, executable = _registered_server()
        _write_json(status_path, {"message": "正在启动 Ansys VRLab，请留意授权提示…"})
        before = set(psutil.pids())
        pythoncom.CoInitialize()
        initialized = True
        try:
            app = win32com.client.DispatchEx(clsid)
        except Exception as exc:
            if _is_registration_error(exc):
                raise VRLabRegistrationError(str(exc)) from exc
            raise RuntimeError(f"无法连接 Ansys VRLab。请确认安装、COM 注册及授权正常，且与本程序以相同用户权限运行。详细信息：{exc}") from exc
        member = app.GetPID
        pid = int(member() if callable(member) else member)
        # Some COM servers reuse existing instances even for DispatchEx. Never
        # open a document or change settings until exclusive ownership is proved.
        if pid in before:
            raise RuntimeError("Ansys 返回了已打开的 VRLab 会话。为保护其中的文件，本次未进行操作；请保存并关闭 VRLab 后重试。")
        process = psutil.Process(pid)
        if os.path.normcase(process.exe()) != os.path.normcase(str(executable)):
            raise RuntimeError("无法确认新 VRLab 实例的身份，本次未打开文件。")
        owner = {"pid": pid, "created": process.create_time(), "executable": process.exe()}
        _write_json(owner_path, owner)
        app.SetAlwaysOnTop(False)
        app.Show(True)  # The documented export API requires a displayed HMI.
        _write_json(status_path, {"message": f"正在打开 {source.name}…"})
        if not app.OpenFile(str(source.resolve())):
            raise RuntimeError("VRLab 无法打开该文件。请检查文件版本、完整性和 Ansys 授权。")
        _write_json(status_path, {"message": "正在由 VRLab 导出全部观察视角…"})
        frames_dir = job_path.parent / "frames"
        frames_dir.mkdir()
        exported = app.ExportAllObserverImages(str(frames_dir.resolve()) + "\\", 1)
        paths = list(frames_dir.glob("*.png"))
        if not exported or not paths:
            raise RuntimeError("VRLab 未能导出观察视角。当前接口只支持观察视角数据；沉浸式全景文件尚不支持。也请检查授权提示。")
        _write_json(result_path, {"ok": True, "count": len(paths)})
        return 0
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if isinstance(exc, VRLabRegistrationError):
            result.update(error_code="vrlab_registration", registration_detail=exc.detail)
        _write_json(result_path, result)
        return 1
    finally:
        app = None
        if initialized:
            import pythoncom
            pythoncom.CoUninitialize()
        if owner:
            try:
                _close_owned(owner)
            except Exception:
                # The parent repeats verified cleanup and reports failures.
                pass


def _natural_key(path: Path) -> tuple:
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", path.name))


def _stop_helper(process) -> None:
    """A one-file PyInstaller EXE also owns a bootloader child process."""
    import psutil
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=5)
    _, alive = psutil.wait_procs(descendants, timeout=3)
    if alive:
        raise RuntimeError("导出辅助进程尚未退出，请关闭此次启动的 VRLab2GIF 辅助进程后重试。")


def convert_exported_views(
    frames_dir: Path, output_dir: Path, delay_ms: int, font_size: int,
    filters: AngleFilters, log=None, progress=None, cancel_event=None,
) -> ConversionResult:
    paths = sorted((p for p in frames_dir.iterdir() if p.suffix.lower() == ".png"), key=_natural_key)
    if not paths:
        raise ValueError("VRLab 没有导出 PNG 图片。")
    if all(parse_filename(p.name) is not None for p in paths):
        return create_gifs(frames_dir, output_dir, delay_ms, font_size, filters, log, progress, cancel_event)
    if filters != AngleFilters():
        raise ValueError("此文件导出的名称没有完整 H/V 角度，无法准确筛选。请清除角度筛选后重试；视角序号不能当作角度。")
    if log:
        log("导出名称未提供完整 H/V 角度：按文件名中的数字顺序合成 collection_all_views.gif，不添加角度文字或分组。")
        if len(paths) == 1:
            log("该文件仅含 1 个可导出视角，生成的 GIF 为静态图片。")
    return create_sequence_gif(paths, output_dir, delay_ms, log, progress, cancel_event)


def create_native_gifs(
    source: Path, output_dir: Path, delay_ms: int = 300, font_size: int = 24,
    filters: AngleFilters | None = None, log: Callable[[str], None] | None = None,
    progress=None, cancel_event: Event | None = None, *, timeout_seconds: float = 600,
) -> ConversionResult:
    validate_native_source(source)
    if sys.platform != "win32":
        raise RuntimeError("VRLab 文件直接转换需要 Windows 和已安装的 Ansys VRLab。")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"输出路径不是文件夹：{output_dir}")
    if isinstance(delay_ms, bool) or not isinstance(delay_ms, int) or not 10 <= delay_ms <= 655350:
        raise ValueError("每帧延时必须是 10 到 655350 之间的整数（毫秒）。")
    if isinstance(font_size, bool) or not isinstance(font_size, int) or not 1 <= font_size <= 512:
        raise ValueError("字体大小必须是 1 到 512 之间的整数。")
    emit = log or (lambda message: None)
    cancel = cancel_event or Event()
    if cancel.is_set():
        raise ConversionCancelled()
    emit("使用本机 Ansys VRLab 导出观察视角，需要可用授权；VRLab 窗口会短暂显示。")
    if progress:
        progress(0, 1, "正在启动 Ansys VRLab")
    # Job files and PNGs are private temporary data, removed after encoding.
    with tempfile.TemporaryDirectory(prefix="vrlab2gif-native-") as temporary:
        job_dir = Path(temporary)
        job = job_dir / "job.json"
        _write_json(job, {"source": str(source.resolve())})
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--native-export", str(job)]
        else:
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"), "--native-export", str(job)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + timeout_seconds
        last_message = ""
        try:
            while process.poll() is None:
                if cancel.wait(0.1):
                    raise ConversionCancelled()
                message = _read_json(job_dir / "status.json").get("message", "")
                if message and message != last_message:
                    emit(message)
                    if progress:
                        progress(0, 1, message)
                    last_message = message
                if time.monotonic() > deadline:
                    raise RuntimeError("等待 VRLab 超时（10 分钟）。请检查 Ansys 授权、弹出的对话框及文件是否可正常打开。")
            result = _read_json(job_dir / "result.json")
            if process.returncode != 0 or not result.get("ok"):
                if result.get("error_code") == "vrlab_registration":
                    raise VRLabRegistrationError(result.get("registration_detail"))
                raise RuntimeError(result.get("error") or "VRLab 导出进程未正常完成，请检查 Ansys 安装与授权。")
        finally:
            # Stop the helper first so no late ownership publication is missed.
            try:
                if process.poll() is None:
                    _stop_helper(process)
            finally:
                identity = _read_json(job_dir / "owner.json")
                if identity:
                    try:
                        _close_owned(identity)
                    except Exception as exc:
                        emit(f"无法自动关闭此次 VRLab 实例，请手动关闭：{exc}")
                elif cancel.is_set():
                    emit("已停止导出。如果 Ansys 仍停留在启动或授权界面，请手动关闭该窗口。")
        if cancel.is_set():
            raise ConversionCancelled()
        emit(f"VRLab 已导出 {result['count']} 个视角，开始合成 GIF。")
        restore_export_angles(source, job_dir / "frames", emit)
        return convert_exported_views(job_dir / "frames", output_dir, delay_ms, font_size,
                                      filters or AngleFilters(), emit, progress, cancel)
