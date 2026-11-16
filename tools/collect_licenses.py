"""Collect the actual build environment's notices before freezing an application.

Windows release builds are strict. --allow-non-windows permits a development
check and records unavailable Windows/runtime components instead of pretending
that this is a release inventory. Never fetch licenses from the network here.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys
import tkinter

from packaging.requirements import Requirement

PROJECT = Path(__file__).resolve().parents[1]
RUNTIME = ("Pillow", "tkinterdnd2", "psutil", "pywin32")


def is_notice(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if PurePosixPath(parts[-1]).suffix.lower() in {".py", ".pyc", ".pyd", ".dll", ".so"}:
        return False
    if any(part.lower() in {"licenses", "licences"} for part in parts[:-1]):
        return True
    return bool(re.match(r"^(licen[cs]e|copying|copyright|notice)(?:[._-].*)?$", parts[-1], re.I))


def safe_path(path: str) -> Path:
    # Installed RECORD files can use ../../ paths. They must never escape output.
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return Path(*(part for part in parts if part not in {".", "..", "/"}))


class Collector:
    def __init__(self, output: Path):
        self.output = output
        self.components: list[dict] = []
        self.files: dict[str, dict] = {}
        self.unavailable: list[str] = []

    def copy(self, source: Path, destination: Path) -> str:
        data = source.read_bytes()
        if not data.strip():
            raise RuntimeError(f"Empty license file: {source.name}")
        relative = destination.as_posix()
        target = self.output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.files[relative] = {"path": relative, "sha256": hashlib.sha256(data).hexdigest()}
        return relative

    def distribution(self, name: str, scope: str) -> metadata.Distribution:
        dist = metadata.distribution(name)
        notices = [file for file in dist.files or () if is_notice(str(file))]
        notices = [file for file in notices if Path(dist.locate_file(file)).is_file()]
        if not notices:
            raise RuntimeError(f"No installed license text found for {name} {dist.version}. "
                               "Use a wheel with license metadata; do not release without its notices.")
        directory = re.sub(r"[^A-Za-z0-9_.-]", "_", dist.metadata["Name"] or name)
        files = [self.copy(Path(dist.locate_file(file)), Path("licenses") / directory / safe_path(str(file)))
                 for file in sorted(notices, key=str)]
        self.components.append({"name": dist.metadata["Name"] or name,
                                "version": dist.version, "scope": scope, "files": files})
        return dist

    def runtime_license(self, name: str, version: str, roots: list[Path], strict: bool) -> None:
        candidates = []
        for root in roots:
            if root.is_dir():
                candidates.extend(file for file in root.iterdir() if file.is_file() and is_notice(file.name))
        # Only an explicitly version-matched upstream copy may replace absent installed text.
        fallback = PROJECT / "docs" / "third-party" / f"{name}-{version}-LICENSE.txt"
        fallback_source = None
        if not candidates and fallback.is_file():
            candidates = [fallback]
            source_file = PROJECT / "docs" / "third-party" / "tcl-tk-sources.json"
            if source_file.is_file():
                fallback_source = json.loads(source_file.read_text(encoding="utf-8")).get(fallback.name)
                if fallback_source and hashlib.sha256(fallback.read_bytes()).hexdigest() != fallback_source["sha256"]:
                    raise RuntimeError(f"Fallback license checksum mismatch: {fallback.name}")
        if not candidates:
            message = f"No license text found for {name} {version}"
            if strict:
                raise RuntimeError(message + "; add that exact upstream version's license to docs/third-party.")
            self.unavailable.append(message)
            return
        files = [self.copy(p, Path("licenses") / name / p.name) for p in sorted(set(candidates))]
        component = {"name": name, "version": version, "scope": "runtime", "files": files}
        if fallback_source:
            component["source_url"] = fallback_source["source_url"]
        self.components.append(component)

    def finish(self, strict: bool) -> None:
        manifest = {"schema_version": 1, "release_inventory": strict,
                    "platform": sys.platform, "python": sys.version.split()[0],
                    "components": sorted(self.components, key=lambda item: item["name"].lower()),
                    "files": sorted(self.files.values(), key=lambda item: item["path"]),
                    "unavailable": self.unavailable,
                    "scope_note": "Installed-package notices are a conservative superset, not an assertion that every optional module or native library is frozen."}
        (self.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect(output: Path, allow_non_windows: bool = False) -> Collector:
    strict = sys.platform == "win32"
    if not strict and not allow_non_windows:
        raise RuntimeError("Release notices must be collected on Windows; use --allow-non-windows for development only.")
    output = output.resolve()
    if output in {PROJECT, PROJECT.parent, Path(output.anchor)} or PROJECT.is_relative_to(output):
        raise ValueError("Output must be a dedicated generated directory, not the project or a parent.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    result = Collector(output)
    pending = [(name, "runtime") for name in RUNTIME if strict or name not in {"pywin32", "psutil"}]
    pending.append(("PyInstaller", "build-tool / bundled bootloader"))
    seen: set[str] = set()
    while pending:
        name, scope = pending.pop(0)
        canonical = re.sub(r"[-_.]+", "-", name).lower()
        if canonical in seen:
            continue
        seen.add(canonical)
        dist = result.distribution(name, scope)
        for text in dist.requires or ():
            requirement = Requirement(text)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append((requirement.name, "build dependency" if scope != "runtime" else "runtime dependency"))
    result.runtime_license("Python", sys.version.split()[0], [Path(sys.base_prefix)], strict)
    interpreter = tkinter.Tcl()
    tcl_version = interpreter.eval("info patchlevel")
    tcl_library = Path(interpreter.eval("info library"))
    result.runtime_license("Tcl", tcl_version, [tcl_library, Path(sys.base_prefix) / "tcl" / f"tcl{tkinter.TclVersion}"], strict)
    try:
        # Python's Windows runtime initializes Tk through _tkinter; a plain
        # Tcl 'package require Tk' cannot always locate its bundled DLL/index.
        interpreter.loadtk()
        interpreter.withdraw()
        tk_version = interpreter.eval("package provide Tk")
        tk_library = Path(interpreter.eval("set tk_library"))
        result.runtime_license("Tk", tk_version, [tk_library, Path(sys.base_prefix) / "tcl" / f"tk{tkinter.TkVersion}"], strict)
    except tkinter.TclError as exc:
        if strict:
            raise RuntimeError(f"Cannot determine the installed Tk runtime and license: {exc}") from exc
        result.unavailable.append("Tk runtime license: no graphical display available")
    finally:
        try:
            interpreter.eval("destroy .")
        except tkinter.TclError:
            pass
    vendored_files = {}
    for source in sorted((PROJECT / "docs" / "third-party").glob("*.txt")):
        if re.match(r"^(Tcl|Tk)-[0-9].*-LICENSE\.txt$", source.name):
            continue  # Runtime collection selected only the installed version.
        vendored_files[source.name] = result.copy(source, Path("licenses") / "vendored" / source.name)
    for required in ("LiberationFonts-LICENSE.txt", "TkDnD-LICENSE.txt", "tkinterdnd2-LICENSE.txt"):
        if required not in vendored_files:
            raise RuntimeError(f"Missing vendored notice: {required}")
    result.components.append({"name": "Liberation Sans Regular", "version": "2.1.5",
                              "scope": "embedded font",
                              "files": [vendored_files["LiberationFonts-LICENSE.txt"]]})
    tkdnd_dist = metadata.distribution("tkinterdnd2")
    target_dir = ("win-x64" if struct.calcsize("P") == 8 else "win-x86") if strict else "linux-x64"
    indexes = [file for file in tkdnd_dist.files or ()
               if str(file).replace("\\", "/").endswith(f"/{target_dir}/pkgIndex.tcl")]
    versions = set()
    for index in indexes:
        text = Path(tkdnd_dist.locate_file(index)).read_text(encoding="utf-8")
        versions.update(re.findall(r"package\s+ifneeded\s+tkdnd\s+([0-9.]+)", text))
    if len(versions) != 1:
        raise RuntimeError(f"Cannot identify the TkDnD version for {target_dir}")
    result.components.append({"name": "TkDnD", "version": versions.pop(),
                              "scope": f"native drag-and-drop ({target_dir})",
                              "files": [vendored_files["TkDnD-LICENSE.txt"]]})
    result.copy(PROJECT / "THIRD_PARTY_NOTICES.md", Path("THIRD_PARTY_NOTICES.md"))
    result.finish(strict)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / ".license-bundle")
    parser.add_argument("--allow-non-windows", action="store_true")
    args = parser.parse_args()
    try:
        result = collect(args.output, args.allow_non_windows)
    except (OSError, RuntimeError, ValueError, metadata.PackageNotFoundError) as exc:
        parser.exit(1, f"License collection failed: {exc}\n")
    print(f"Collected {len(result.files)} notice files for {len(result.components)} components into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
