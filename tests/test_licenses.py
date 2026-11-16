"""Release notices must be complete, byte-preserving and safe to package."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.collect_licenses import Collector, is_notice, safe_path


class LicenseTests(unittest.TestCase):
    def test_native_library_notices_are_kept_with_their_original_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed"
            installed.mkdir()
            data = b"Pillow main license\r\n----\r\nFreeType original notice\r\n"
            license_file = installed / "LICENSE"
            license_file.write_bytes(data)
            dist = Mock()
            dist.version = "13.0.0"
            dist.metadata = {"Name": "Pillow"}
            dist.files = ["pillow.dist-info/licenses/LICENSE"]
            dist.locate_file.return_value = license_file
            output = root / "bundle"
            output.mkdir()
            collector = Collector(output)
            with patch("tools.collect_licenses.metadata.distribution", return_value=dist):
                collector.distribution("Pillow", "runtime")
            collector.finish(True)
            manifest = json.loads((output / "manifest.json").read_text())
            item = manifest["files"][0]
            self.assertEqual((output / item["path"]).read_bytes(), data)
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(manifest["components"][0]["version"], "13.0.0")
            self.assertNotIn(str(installed), (output / "manifest.json").read_text())

    def test_missing_notice_fails_instead_of_silently_using_latest_upstream(self):
        dist = Mock()
        dist.files = []
        dist.version = "1.0"
        with tempfile.TemporaryDirectory() as temporary:
            collector = Collector(Path(temporary))
            with patch("tools.collect_licenses.metadata.distribution", return_value=dist):
                with self.assertRaisesRegex(RuntimeError, "No installed license"):
                    collector.distribution("example", "runtime")

    def test_runtime_fallback_requires_exact_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            notices = root / "docs" / "third-party"
            notices.mkdir(parents=True)
            (notices / "Tcl-8.6.16-LICENSE.txt").write_text("Original license")
            collector = Collector(root / "output")
            with patch("tools.collect_licenses.PROJECT", root):
                with self.assertRaisesRegex(RuntimeError, "Tcl 8.6.17"):
                    collector.runtime_license("Tcl", "8.6.17", [], True)
                collector.runtime_license("Tcl", "8.6.16", [], True)
            self.assertEqual(collector.components[0]["version"], "8.6.16")

    def test_record_paths_cannot_escape_license_directory(self):
        self.assertEqual(safe_path("../../win32/License.txt"), Path("win32/License.txt"))
        self.assertEqual(safe_path(r"..\..\win32\License.txt"), Path("win32/License.txt"))
        self.assertTrue(is_notice("pillow.dist-info/licenses/native-lib/LICENSE.ftl"))
        self.assertTrue(is_notice("PyInstaller/COPYING.txt"))
        self.assertFalse(is_notice("win32/license_helper.py"))


if __name__ == "__main__":
    unittest.main()
