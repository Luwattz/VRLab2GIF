# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project = Path(SPECPATH)
# Arial is mandatory so release annotations do not depend on system fonts.
font = project / "fonts" / "arial.ttf"
if not font.is_file():
    raise FileNotFoundError("Missing bundled Arial: fonts/arial.ttf")
datas = [(str(project / "assets" / "vrlab2gif-logo.png"), "assets"),
         (str(font), "fonts")]
datas += collect_data_files("tkinterdnd2")
datas += [(str(license), "third-party") for license in (project / "docs" / "third-party").glob("*.txt")]

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=["pythoncom", "win32com.client", "win32timezone"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Pillow's optional NumPy integration is unused by PNG/GIF conversion.
    excludes=["numpy"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VRLab2GIF",
    icon=str(project / "assets" / "vrlab2gif.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=str(project / "windows-version.txt"),
)
