"""Native view export: metadata honesty, isolation, cancellation and atomic GIFs."""
from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from vrlab2gif.core import AngleFilters, ConversionCancelled, create_sequence_gif
from vrlab2gif.native import (VRLabRegistrationError, check_native_registration,
                             convert_exported_views, create_native_gifs, export_helper,
                             _natural_key, _owned_process, validate_native_source)


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-native-", dir=Path.cwd())
        self.root = Path(self.temporary.name)
        self.frames = self.root / "frames"
        self.frames.mkdir()
        self.output = self.root / "output"
        self.source = self.root / "sample.OptisVR"
        self.source.write_bytes(b"native-test-fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def picture(self, name, color="red", size=(90, 60)):
        path = self.frames / name
        with Image.new("RGB", size, color) as image:
            image.save(path)
        return path

    def convert(self, filters=None):
        return convert_exported_views(self.frames, self.output, 305, 24, filters or AngleFilters())

    def test_index_names_use_numeric_order_and_no_invented_angle_text(self):
        self.picture("sample_Image_10_0.png", "blue")
        self.picture("sample_Image_2_0.png", "green")
        self.picture("sample_Image_1_0.png", "red")
        result = self.convert()
        self.assertEqual([p.name for p in result.output_paths], ["collection_all_views.gif"])
        self.assertEqual(result.matched_count, 3)
        self.assertEqual(result.duration_ms, 300)
        with Image.open(result.output_paths[0]) as image:
            self.assertEqual(image.n_frames, 3)
            for index, color in enumerate(((255, 0, 0), (0, 128, 0), (0, 0, 255))):
                image.seek(index)
                self.assertEqual(image.convert("RGB").getpixel((12, 12)), color)
                self.assertEqual(image.info["duration"], 300)

    def test_real_angle_names_reuse_grouping_and_filters(self):
        self.picture("sample_Image_0°_10°.png")
        self.picture("sample_Image_30°_10°.png", "blue")
        result = self.convert(AngleFilters(h_min=1))
        self.assertEqual(result.matched_count, 1)
        self.assertEqual(len(result.output_paths), 2)
        self.assertEqual(result.output_paths[0].name, "vertical_angle_10.0.gif")

    def test_missing_or_partial_metadata_cannot_silently_apply_filters(self):
        self.picture("sample_Image_1_0.png")
        self.picture("sample_Image_30°_10°.png", "blue")
        with self.assertRaisesRegex(ValueError, "清除角度筛选"):
            self.convert(AngleFilters(h_min=1))
        self.assertFalse(self.output.exists())

    def test_empty_and_unsupported_sources_are_actionable_errors(self):
        with self.assertRaisesRegex(ValueError, "PNG"):
            self.convert()
        hdr = self.root / "panorama.hdr"
        hdr.write_bytes(b"test")
        with self.assertRaisesRegex(ValueError, "尚不支持"):
            validate_native_source(hdr)

    def test_bad_later_frame_preserves_existing_gif(self):
        self.output.mkdir()
        old = self.output / "collection_all_views.gif"
        old.write_bytes(b"old result")
        self.picture("view1.png")
        (self.frames / "view2.png").write_bytes(b"broken")
        with self.assertRaisesRegex(ValueError, "view2"):
            self.convert()
        self.assertEqual(old.read_bytes(), b"old result")
        self.assertEqual(list(self.output.iterdir()), [old])

    def test_size_mismatch_is_rejected_before_writing(self):
        self.picture("view1.png")
        self.picture("view2.png", size=(50, 50))
        with self.assertRaisesRegex(ValueError, "相同尺寸"):
            self.convert()
        self.assertFalse(self.output.exists())

    def test_cancellation_at_save_preserves_old_result_and_removes_temporary_file(self):
        path = self.picture("view1.png")
        self.output.mkdir()
        old = self.output / "collection_all_views.gif"
        old.write_bytes(b"old result")
        cancel = threading.Event()
        real_save = Image.Image.save

        def save_and_cancel(image, *args, **kwargs):
            real_save(image, *args, **kwargs)
            cancel.set()

        with patch.object(Image.Image, "save", save_and_cancel):
            with self.assertRaises(ConversionCancelled):
                create_sequence_gif([path], self.output, cancel_event=cancel)
        self.assertEqual(old.read_bytes(), b"old result")
        self.assertEqual(list(self.output.iterdir()), [old])

    def test_registration_guidance_explains_one_time_admin_setup_and_png_alternative(self):
        message = str(VRLabRegistrationError())
        for text in ("以管理员身份运行", "VRLab.exe", "普通用户权限", "PNG 文件夹", "没有管理员权限", "IT"):
            self.assertIn(text, message)

    def test_registration_reads_merged_registry_views_without_activation_or_writes(self):
        import winreg

        executable = self.root / "Ansys 视角" / "VRLab.exe"
        executable.parent.mkdir()
        executable.write_bytes(b"fixture")
        clsid = "{75C82530-D7F9-43C1-A493-724D96A5C0F1}"
        values = {r"HDRIViewer.Application\CLSID": clsid,
                  rf"CLSID\{clsid}\LocalServer32": f'"{executable}" /Embedding'}
        opened = []

        def open_key(hive, path, reserved, access):
            opened.append((hive, path, access))
            self.assertEqual(hive, winreg.HKEY_CLASSES_ROOT)
            self.assertIn(access, (winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                                   winreg.KEY_READ | winreg.KEY_WOW64_32KEY))
            if access & winreg.KEY_WOW64_64KEY:
                raise FileNotFoundError("Registered in the 32-bit view only")
            return nullcontext(path)

        with patch("winreg.OpenKey", side_effect=open_key), \
                patch("winreg.QueryValue", side_effect=lambda key, name: values[key]), \
                patch("winreg.CreateKey") as create, \
                patch("winreg.SetValueEx") as write, \
                patch("winreg.DeleteKey") as delete, \
                patch("win32com.client.DispatchEx") as dispatch, \
                patch("vrlab2gif.native.subprocess.Popen") as process:
            self.assertEqual(check_native_registration(), (clsid, executable.resolve()))
        self.assertTrue(any(access & winreg.KEY_WOW64_64KEY for _, _, access in opened))
        self.assertTrue(any(access & winreg.KEY_WOW64_32KEY for _, _, access in opened))
        for mutation in (create, write, delete, dispatch, process):
            mutation.assert_not_called()

    def test_missing_or_stale_registration_is_actionable(self):
        clsid = "{75C82530-D7F9-43C1-A493-724D96A5C0F1}"
        progid = r"HDRIViewer.Application\CLSID"
        server = rf"CLSID\{clsid}\LocalServer32"
        unrelated = self.root / "other.exe"
        unrelated.write_bytes(b"fixture")
        cases = ({}, {progid: ""}, {progid: clsid},
                 {progid: clsid, server: f'"{self.root / "missing" / "VRLab.exe"}"'},
                 {progid: clsid, server: f'"{unrelated}"'})
        for values in cases:
            with self.subTest(registry=values):
                def open_key(hive, path, reserved, access):
                    if path not in values:
                        raise FileNotFoundError(path)
                    return nullcontext(path)

                with patch("winreg.OpenKey", side_effect=open_key), \
                        patch("winreg.QueryValue", side_effect=lambda key, name: values[key]), \
                        patch("win32com.client.DispatchEx") as dispatch:
                    with self.assertRaises(VRLabRegistrationError) as raised:
                        check_native_registration()
                self.assertIn("VRLab.exe", str(raised.exception))
                self.assertIn("PNG 文件夹", str(raised.exception))
                dispatch.assert_not_called()

    def test_helper_returns_structured_registration_error_without_starting_com(self):
        job = self.root / "job.json"
        job.write_text(json.dumps({"source": str(self.source)}), encoding="utf-8")
        with patch("vrlab2gif.native._registered_server", side_effect=VRLabRegistrationError()), \
                patch("win32com.client.DispatchEx") as dispatch, \
                patch("vrlab2gif.native._close_owned") as close:
            self.assertEqual(export_helper(job), 1)
        result = json.loads((self.root / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "vrlab_registration")
        self.assertIn("以管理员身份运行", result["error"])
        dispatch.assert_not_called()
        close.assert_not_called()

    def test_dispatch_class_errors_are_registration_errors_but_other_com_failures_are_not(self):
        import pywintypes

        job = self.root / "job.json"
        job.write_text(json.dumps({"source": str(self.source)}), encoding="utf-8")
        for hresult, registration in ((0x80040154, True), (0x800401F3, True),
                                      (0x80070005, False), (0x80004005, False)):
            with self.subTest(hresult=hex(hresult)):
                error = pywintypes.com_error(hresult - (1 << 32), "COM fixture failure", None, None)
                with patch("vrlab2gif.native._registered_server", return_value=("clsid", Path("VRLab.exe"))), \
                        patch("psutil.pids", return_value=[]), \
                        patch("win32com.client.DispatchEx", side_effect=error), \
                        patch("vrlab2gif.native._close_owned") as close:
                    self.assertEqual(export_helper(job), 1)
                result = json.loads((self.root / "result.json").read_text(encoding="utf-8"))
                self.assertEqual(result.get("error_code") == "vrlab_registration", registration)
                self.assertIn("COM fixture failure", result["error"])
                close.assert_not_called()

    def test_parent_restores_registration_error_from_helper_without_repeating_guide(self):
        child = Mock()
        child.poll.return_value = 1
        child.returncode = 1
        detail = "The COM class could not be created"

        def spawn(command, **kwargs):
            job_dir = Path(command[-1]).parent
            result = {"ok": False, "error_code": "vrlab_registration",
                      "error": str(VRLabRegistrationError(detail)), "registration_detail": detail}
            (job_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
            return child

        temporary_directory = tempfile.TemporaryDirectory
        with patch("vrlab2gif.native.subprocess.Popen", side_effect=spawn), \
                patch("vrlab2gif.native._close_owned") as close, \
                patch("vrlab2gif.native.tempfile.TemporaryDirectory", side_effect=lambda **kwargs: temporary_directory(dir=self.root, **kwargs)):
            with self.assertRaises(VRLabRegistrationError) as raised:
                create_native_gifs(self.source, self.output)
        self.assertEqual(raised.exception.detail, detail)
        self.assertEqual(str(raised.exception).count("方法一"), 1)
        close.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_existing_com_session_is_never_opened_or_closed(self):
        job = self.root / "job.json"
        job.write_text(json.dumps({"source": str(self.source)}), encoding="utf-8")
        app = Mock()
        app.GetPID.return_value = 42
        with patch("vrlab2gif.native._registered_server", return_value=("clsid", Path("VRLab.exe"))), \
                patch("psutil.pids", return_value=[42]), \
                patch("win32com.client.DispatchEx", return_value=app), \
                patch("vrlab2gif.native._close_owned") as close:
            code = export_helper(job)
        self.assertEqual(code, 1)
        app.OpenFile.assert_not_called()
        app.Show.assert_not_called()
        close.assert_not_called()
        self.assertIn("已打开", json.loads((self.root / "result.json").read_text(encoding="utf-8"))["error"])

    def test_pid_reuse_or_executable_mismatch_is_never_touched(self):
        process = Mock()
        process.create_time.return_value = 100
        process.exe.return_value = r"C:\Ansys\VRLab.exe"
        identity = {"pid": 42, "created": 99, "executable": r"C:\Ansys\VRLab.exe"}
        with patch("psutil.Process", return_value=process):
            self.assertIsNone(_owned_process(identity))
            identity.update(created=100, executable=r"C:\other\VRLab.exe")
            self.assertIsNone(_owned_process(identity))
            identity["executable"] = r"C:\Ansys\VRLab.exe"
            self.assertIs(_owned_process(identity), process)
        process.terminate.assert_not_called()

    def test_cancel_stops_helper_and_only_cleans_published_owned_instance(self):
        cancel = threading.Event()
        owner = {"pid": 42, "created": 100, "executable": r"C:\Ansys\VRLab.exe"}
        child = Mock()
        child.poll.return_value = None

        def spawn(command, **kwargs):
            job_dir = Path(command[-1]).parent
            (job_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
            cancel.set()
            return child

        temporary_directory = tempfile.TemporaryDirectory
        with patch("vrlab2gif.native.subprocess.Popen", side_effect=spawn), \
                patch("vrlab2gif.native._stop_helper") as stop, \
                patch("vrlab2gif.native._close_owned") as close, \
                patch("vrlab2gif.native.tempfile.TemporaryDirectory", side_effect=lambda **kwargs: temporary_directory(dir=self.root, **kwargs)):
            with self.assertRaises(ConversionCancelled):
                create_native_gifs(self.source, self.output, cancel_event=cancel)
        stop.assert_called_once_with(child)
        close.assert_called_once_with(owner)
        self.assertFalse(self.output.exists())
        self.assertEqual({p.name for p in self.root.iterdir()}, {"sample.OptisVR", "frames"})


if __name__ == "__main__":
    unittest.main()
