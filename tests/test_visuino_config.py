from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.visuino_config import (
    read_directories_user,
    replace_directories_user,
    write_directories_user,
)


SAMPLE_YAML = """board_manager:
    additional_urls:
        - https://example.test/package.json
directories:
    data: C:\\Users\\Example\\AppData\\Local\\Arduino15
    downloads: C:\\Users\\Example\\AppData\\Local\\Arduino15\\staging
    user: C:\\Users\\Example\\Documents\\Arduino
library:
    enable_unsafe_install: false
"""


class VisuinoYamlTests(unittest.TestCase):
    def test_replaces_only_directories_user(self) -> None:
        target = r"C:\Library Setups\Client #1\Release A"
        rendered = replace_directories_user(SAMPLE_YAML, target)
        self.assertEqual(target, read_directories_user(rendered))
        self.assertIn("https://example.test/package.json", rendered)
        self.assertIn("enable_unsafe_install: false", rendered)

    def test_adds_missing_directories_section(self) -> None:
        rendered = replace_directories_user("logging:\n    level: info\n", r"D:\Setups")
        self.assertEqual(r"D:\Setups", read_directories_user(rendered))

    def test_atomic_file_write_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "arduino-cli.yaml"
            path.write_text(SAMPLE_YAML, encoding="utf-8")
            write_directories_user(path, r"D:\Customer\Display")
            self.assertEqual(
                r"D:\Customer\Display",
                read_directories_user(path.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
