# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project = Path(SPECPATH)
# COLLECT replaces its output directory. On Windows the bundle name also
# matches the source package case-insensitively, so reject overlapping paths.
folder_destination = (Path(DISTPATH) / "VRLab2GIF").resolve()
source_package = (project / "vrlab2gif").resolve()
if folder_destination.is_relative_to(source_package) or source_package.is_relative_to(folder_destination):
    raise ValueError("Folder output overlaps the source tree; choose a separate --distpath / OutputDirectory.")
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
exe_options = dict(
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

# Both distributions use exactly the same analysis, code, resources and icon.
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)
folder_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    contents_directory="_internal",
    **exe_options,
)
folder = COLLECT(
    folder_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VRLab2GIF",
)
