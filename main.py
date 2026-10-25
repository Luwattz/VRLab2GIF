"""Launch VRLab2GIF from source or its packaged Windows executable."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Virtual Reality Lab 视角合成器")
    parser.add_argument("--smoke-test", action="store_true", help="创建并关闭界面，验证应用可启动。")
    parser.add_argument("--native-export", type=str, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.native_export:
        from pathlib import Path
        from vrlab2gif.native import export_helper
        return export_helper(Path(args.native_export))
    if args.smoke_test:
        from pathlib import Path
        from vrlab2gif.core import bundled_font_path, load_font
        font = load_font(24)
        if (Path(getattr(font, "path", "")).resolve() != bundled_font_path().resolve()
                or font.getname()[0] != "Arial"):
            raise RuntimeError("内嵌 Arial 字体自检失败。请检查 fonts/arial.ttf 并重新打包。")
    from vrlab2gif.app import main as run_app
    return run_app(smoke_test=args.smoke_test)


if __name__ == "__main__":
    raise SystemExit(main())
