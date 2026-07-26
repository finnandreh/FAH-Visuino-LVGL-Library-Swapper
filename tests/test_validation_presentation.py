from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from lvgl_visuino_setup_manager.validation_dialog import (
    SOURCE_EXPLANATION,
    SOURCE_MISSING_MESSAGE,
    invalid_baseline_badges,
    repair_details,
    repair_heading,
    repair_summary_lines,
)


class ValidationPresentationTests(unittest.TestCase):
    def _plan(self) -> SimpleNamespace:
        return SimpleNamespace(
            source_path=Path("C:/Arduino/libraries"),
            setup_path=Path("C:/Profiles/Customer A"),
            copies=(
                SimpleNamespace(
                    name="Mitov",
                    file_count=3960,
                    total_bytes=158_580_308,
                ),
            ),
            retained=("ExistingMitovVersion",),
            unavailable=("VisuinoPro",),
        )

    def test_summary_leads_with_the_decision_and_safety(self) -> None:
        plan = self._plan()

        self.assertEqual(
            "Mitov is missing. This setup can be fixed safely.",
            repair_heading(plan),
        )
        self.assertEqual(
            (
                "Will add: Mitov",
                "Will keep: Every existing library and folder",
                "Changes now: None — nothing changes until you confirm",
            ),
            repair_summary_lines(plan),
        )

    def test_technical_information_remains_available_in_details(self) -> None:
        details = repair_details(self._plan())

        self.assertIn("C:\\Arduino\\libraries", details)
        self.assertIn("C:\\Profiles\\Customer A", details)
        self.assertIn("3,960 files", details)
        self.assertIn("151.2 MiB", details)
        self.assertIn("ExistingMitovVersion", details)
        self.assertIn("VisuinoPro", details)
        self.assertIn("all other libraries remain unchanged", details)

    def test_missing_source_copy_is_short_and_explains_the_boundary(self) -> None:
        self.assertIn("no trusted source was found", SOURCE_MISSING_MESSAGE)
        self.assertIn("normal Arduino libraries folder", SOURCE_MISSING_MESSAGE)
        self.assertIn("only as a source", SOURCE_EXPLANATION)
        self.assertIn("remain unchanged", SOURCE_EXPLANATION)

    def test_missing_setup_never_claims_baseline_libraries_are_ready(self) -> None:
        mitov, visuino_pro = invalid_baseline_badges(
            ("Setup folder does not exist: C:/Profiles/Missing",)
        )

        self.assertEqual(("invalid", "Mitov · unavailable"), mitov)
        self.assertEqual(("unknown", "VisuinoPro · unavailable"), visuino_pro)


if __name__ == "__main__":
    unittest.main()
