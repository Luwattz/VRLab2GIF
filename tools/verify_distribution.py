"""Verify shipped font/notices in both Windows distributions before publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

FONT = "fonts/LiberationSans-Regular.ttf"


def expected_resources(project: Path) -> dict[str, bytes]:
    resources = {
        "LICENSE": (project / "LICENSE").read_bytes(),
        "THIRD_PARTY_NOTICES.md": (project / "THIRD_PARTY_NOTICES.md").read_bytes(),
        FONT: (project / FONT).read_bytes(),
    }
    bundle = project / ".license-bundle"
    if not (bundle / "manifest.json").is_file():
        raise ValueError("Missing generated license manifest; rebuild first.")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("release_inventory") or manifest.get("unavailable"):
        raise ValueError("Development or incomplete license inventory cannot be released.")
    required = {"pillow", "tkinterdnd2", "psutil", "pywin32", "python", "tcl", "tk", "pyinstaller"}
    components = {item["name"].lower() for item in manifest["components"]}
    if not required <= components:
        raise ValueError(f"Missing release components: {sorted(required - components)}")
    for item in manifest["files"]:
        data = (bundle / item["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"License hash mismatch: {item['path']}")
    for path in bundle.rglob("*"):
        if path.is_file():
            resources["third-party/generated/" + path.relative_to(bundle).as_posix()] = path.read_bytes()
    for path in (project / "docs/third-party").glob("*.txt"):
        resources["third-party/" + path.name] = path.read_bytes()
    return resources


def check_resources(read, names, expected: dict[str, bytes], prefix: str = "") -> None:
    """Check bytes as well as presence; a stale license must fail a rebuild."""
    if any(PurePosixPath(name.replace("\\", "/")).name.lower() == "arial.ttf" for name in names):
        raise ValueError("Arial is still present in the distribution.")
    for name, data in expected.items():
        actual = read(prefix + name)
        if actual != data:
            raise ValueError(f"Missing, stale or corrupt packaged resource: {prefix + name}")


def verify(directory: Path, project: Path) -> None:
    from PyInstaller.archive.readers import CArchiveReader

    resources = expected_resources(project)
    exe = directory / "VRLab2GIF.exe"
    archive = CArchiveReader(str(exe))
    entries = {name.replace("\\", "/"): name for name in archive.toc}
    check_resources(lambda name: archive.extract(entries[name]), entries, resources)

    for filename, prefix in (("VRLab2GIF-Windows-x64.zip", ""),
                             ("VRLab2GIF-Windows-x64-folder.zip", "VRLab2GIF/")):
        with zipfile.ZipFile(directory / filename) as zipped:
            bad = zipped.testzip()
            if bad:
                raise ValueError(f"Corrupt ZIP entry: {bad}")
            entries = {name.replace("\\", "/"): name for name in zipped.namelist()}
            read = lambda name: zipped.read(entries[name])
            # Both ZIPs expose notices as normal files as well as inside EXE.
            outside = {"LICENSE": resources["LICENSE"],
                       "THIRD_PARTY_NOTICES.md": resources["THIRD_PARTY_NOTICES.md"]}
            for name, data in resources.items():
                if name.startswith("third-party/"):
                    outside["docs/" + name] = data
            check_resources(read, entries, outside, prefix)
            if prefix:
                check_resources(read, entries, resources, prefix + "_internal/")
            elif read("VRLab2GIF.exe") != exe.read_bytes():
                raise ValueError("Single-file ZIP contains a different EXE.")

    checksums = []
    for name in ("VRLab2GIF.exe", "VRLab2GIF-Windows-x64.zip", "VRLab2GIF-Windows-x64-folder.zip"):
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}\n")
    (directory / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
    print("Verified both ZIPs, embedded Liberation Sans and all license resources; SHA256SUMS.txt written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    verify(args.directory, Path(__file__).resolve().parents[1])
