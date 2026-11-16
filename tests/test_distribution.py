"""Reject missing/stale notices or accidental redistribution of Arial."""
import unittest

from tools.verify_distribution import check_resources


class DistributionTests(unittest.TestCase):
    def test_missing_or_stale_notice_fails(self):
        expected = {"third-party/generated/licenses/Pillow/LICENSE": b"current license"}
        with self.assertRaises(KeyError):
            check_resources({}.__getitem__, [], expected)
        with self.assertRaisesRegex(ValueError, "stale"):
            check_resources(lambda name: b"old license", expected, expected)

    def test_arial_is_rejected_in_any_directory(self):
        with self.assertRaisesRegex(ValueError, "Arial"):
            check_resources(lambda name: b"", ["VRLab2GIF/_internal/fonts/Arial.ttf"], {})

    def test_complete_resources_with_folder_prefix_pass(self):
        expected = {"LICENSE": b"project", "third-party/generated/manifest.json": b"versions"}
        actual = {"VRLab2GIF/_internal/" + name: data for name, data in expected.items()}
        check_resources(actual.__getitem__, actual, expected, "VRLab2GIF/_internal/")
