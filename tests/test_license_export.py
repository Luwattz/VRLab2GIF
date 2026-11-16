"""A standalone EXE must expose its original notices without loading Tk/Ansys."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from vrlab2gif.licensing import export_licenses


class LicenseExportTests(unittest.TestCase):
    def test_frozen_resources_are_exported_without_overwriting_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "_MEI"
            bundle = root / "third-party/generated"
            bundle.mkdir(parents=True)
            data = b"Original copyright and license\r\n"
            (bundle / "LICENSE.txt").write_bytes(data)
            (bundle / "manifest.json").write_text(json.dumps({"components": []}))
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                (root / name).write_bytes(data)
            output = Path(temporary) / "exported"
            with patch.object(sys, "_MEIPASS", str(root), create=True):
                export_licenses(output)
                self.assertEqual((output / "third-party/generated/LICENSE.txt").read_bytes(), data)
                (output / "LICENSE").write_bytes(b"keep this")
                with self.assertRaises(ValueError):
                    export_licenses(output)
                self.assertEqual((output / "LICENSE").read_bytes(), b"keep this")
