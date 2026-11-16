"""Make bundled copyright and license texts accessible without starting the GUI."""
from pathlib import Path
import shutil
import sys


def export_licenses(destination: Path) -> None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    frozen = hasattr(sys, "_MEIPASS")
    third_party = root / ("third-party" if frozen else "docs/third-party")
    generated = third_party / "generated" if frozen else root / ".license-bundle"
    for path in (root / "LICENSE", root / "THIRD_PARTY_NOTICES.md", generated / "manifest.json"):
        if not path.is_file():
            raise RuntimeError(f"Missing license resource: {path.name}. Run the Windows build to collect notices first.")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("请选择新的或空的目录导出许可证，避免覆盖已有文件。")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(root / name, destination / name)
    shutil.copytree(third_party, destination / "third-party")
    if not frozen:
        shutil.copytree(generated, destination / "third-party/generated")
