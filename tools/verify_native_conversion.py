"""Run an opt-in real Ansys conversion; never runs as part of unit tests."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
from threading import Event
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vrlab2gif.native import create_native_gifs
from vrlab2gif.core import ConversionCancelled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--helper-executable", type=Path)
    parser.add_argument("--cancel-at-open", action="store_true")
    args = parser.parse_args()
    report = {"source": str(args.source.resolve()), "packaged_helper": str(args.helper_executable) if args.helper_executable else None}
    cancel = Event()

    def log(message):
        print(json.dumps({"log": message}), flush=True)
        if args.cancel_at_open and ("正在打开" in message or "导出全部观察视角" in message):
            cancel.set()

    with ExitStack() as stack:
        if args.helper_executable:
            stack.enter_context(patch.object(sys, "frozen", True, create=True))
            stack.enter_context(patch.object(sys, "executable", str(args.helper_executable.resolve())))
        try:
            result = create_native_gifs(args.source, args.output, log=log, cancel_event=cancel)
        except ConversionCancelled:
            if not args.cancel_at_open:
                raise
            if args.output.exists() and list(args.output.iterdir()):
                raise RuntimeError("Cancelled native conversion left output files.")
            print(json.dumps({"cancelled": True, "no_output_files": True}), flush=True)
            return
    if args.cancel_at_open:
        raise RuntimeError("The conversion completed before the cancellation checkpoint.")
    report["matched_count"] = result.matched_count
    report["files"] = []
    for path in result.output_paths:
        with Image.open(path) as image:
            sizes, durations, digests = [], [], []
            for index in range(image.n_frames):
                image.seek(index)
                sizes.append(image.size)
                durations.append(image.info.get("duration"))
                digests.append(hashlib.sha256(image.convert("RGB").tobytes()).hexdigest())
            report["files"].append({"path": str(path.resolve()), "frames": image.n_frames,
                                    "sizes": sizes, "durations": durations,
                                    "decoded_frame_sha256": digests, "loop": image.info.get("loop")})
    (args.output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
