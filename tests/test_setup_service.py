from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.setup_service import (
    BaselineRepairError,
    SetupService,
)


class SetupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = SetupService()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_setup_requires_mitov_and_treats_visuino_pro_as_optional(
        self,
    ) -> None:
        setup = self.root / "setup"
        setup.mkdir()
        result = self.service.validate(setup)
        self.assertEqual("invalid", result.status)
        self.assertFalse(result.mitov_present)
        self.assertFalse(result.visuino_pro_present)
        self.assertTrue((setup / "libraries").is_dir())

        (setup / "libraries" / "Mitov").mkdir()
        result = self.service.validate(setup)
        self.assertTrue(result.is_valid)
        self.assertIn("Optional VisuinoPro", result.warnings[0])

        (setup / "libraries" / "VisuinoPro").mkdir()
        result = self.service.validate(setup)
        self.assertTrue(result.is_valid)
        self.assertEqual((), result.warnings)

    def test_baseline_repair_copies_only_mitov_and_optional_visuino_pro(
        self,
    ) -> None:
        setup = self.root / "setup"
        setup.mkdir()
        (setup / "libraries").mkdir()
        source = self.root / "arduino" / "libraries"
        (source / "Mitov").mkdir(parents=True)
        (source / "VisuinoPro").mkdir()
        (source / "OtherLibrary").mkdir()
        (source / "Mitov" / "Mitov.h").write_text("mitov", encoding="utf-8")
        (source / "VisuinoPro" / "VisuinoPro.h").write_text(
            "pro",
            encoding="utf-8",
        )
        (source / "OtherLibrary" / "Other.h").write_text(
            "other",
            encoding="utf-8",
        )

        plan = self.service.plan_baseline_repair(
            "setup_a",
            setup,
            source.parent,
        )
        self.assertEqual(
            ("Mitov", "VisuinoPro"),
            tuple(item.name for item in plan.copies),
        )
        self.assertTrue(plan.required_available)

        result = self.service.repair_baseline(plan)
        self.assertEqual(("Mitov", "VisuinoPro"), result.copied)
        self.assertTrue((setup / "libraries" / "Mitov" / "Mitov.h").is_file())
        self.assertTrue(
            (setup / "libraries" / "VisuinoPro" / "VisuinoPro.h").is_file()
        )
        self.assertFalse((setup / "libraries" / "OtherLibrary").exists())

    def test_baseline_repair_retains_existing_user_version(self) -> None:
        setup = self.root / "setup"
        (setup / "libraries" / "Mitov").mkdir(parents=True)
        (setup / "libraries" / "Mitov" / "version.txt").write_text(
            "user-selected",
            encoding="utf-8",
        )
        source = self.root / "source"
        (source / "Mitov").mkdir(parents=True)
        (source / "VisuinoPro").mkdir()
        (source / "Mitov" / "version.txt").write_text(
            "default",
            encoding="utf-8",
        )
        (source / "VisuinoPro" / "version.txt").write_text(
            "pro",
            encoding="utf-8",
        )

        plan = self.service.plan_baseline_repair(
            "setup_a",
            setup,
            source,
        )
        self.assertEqual(("Mitov",), plan.retained)
        self.assertEqual(
            ("VisuinoPro",),
            tuple(item.name for item in plan.copies),
        )
        self.service.repair_baseline(plan)

        self.assertEqual(
            "user-selected",
            (setup / "libraries" / "Mitov" / "version.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertTrue(
            (setup / "libraries" / "VisuinoPro" / "version.txt").is_file()
        )

    def test_baseline_repair_rejects_source_without_required_mitov(self) -> None:
        setup = self.root / "setup"
        setup.mkdir()
        (setup / "libraries").mkdir()
        source = self.root / "source"
        (source / "VisuinoPro").mkdir(parents=True)
        (source / "VisuinoPro" / "version.txt").write_text(
            "pro",
            encoding="utf-8",
        )

        plan = self.service.plan_baseline_repair(
            "setup_a",
            setup,
            source,
        )
        self.assertFalse(plan.required_available)
        with self.assertRaisesRegex(BaselineRepairError, "required Mitov"):
            self.service.repair_baseline(plan)
        self.assertFalse((setup / "libraries" / "VisuinoPro").exists())

    def test_baseline_repair_detects_size_change_after_dry_run(self) -> None:
        setup = self.root / "setup"
        setup.mkdir()
        (setup / "libraries").mkdir()
        source = self.root / "source"
        (source / "Mitov").mkdir(parents=True)
        source_file = source / "Mitov" / "version.txt"
        source_file.write_text("first", encoding="utf-8")
        plan = self.service.plan_baseline_repair(
            "setup_a",
            setup,
            source,
        )
        source_file.write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(BaselineRepairError, "byte count changed"):
            self.service.repair_baseline(plan)
        self.assertFalse((setup / "libraries" / "Mitov").exists())
        self.assertFalse(
            any(
                item.name.startswith(".lvgl-visuino-baseline-staging-")
                for item in setup.iterdir()
            )
        )

    def test_create_setup_never_overwrites_existing_folder(self) -> None:
        created = self.service.create_setup_folder(self.root, "Release: A")
        self.assertEqual("Release_ A", created.name)
        self.assertTrue((created / "libraries").is_dir())
        with self.assertRaises(FileExistsError):
            self.service.create_setup_folder(self.root, "Release: A")

    def test_validation_copies_legacy_flat_layout_without_deleting_original(
        self,
    ) -> None:
        setup = self.root / "legacy"
        (setup / "Mitov" / "src").mkdir(parents=True)
        (setup / "Mitov" / "library.properties").write_text(
            "name=Visuino\n",
            encoding="utf-8",
        )
        (setup / "Mitov" / "src" / "OpenWire.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )
        (setup / "lv_conf.h").write_text(
            "#define LV_COLOR_DEPTH 16\n",
            encoding="utf-8",
        )

        result = self.service.validate(setup)

        self.assertTrue(result.is_valid)
        self.assertTrue(result.libraries_created)
        self.assertEqual(("lv_conf.h", "Mitov"), result.legacy_entries_copied)
        self.assertTrue((setup / "Mitov" / "src" / "OpenWire.h").is_file())
        self.assertTrue(
            (setup / "libraries" / "Mitov" / "src" / "OpenWire.h").is_file()
        )
        self.assertTrue((setup / "libraries" / "lv_conf.h").is_file())

    def test_root_paths_are_rejected(self) -> None:
        root = Path(self.root.anchor)
        result = self.service.validate(root)
        self.assertEqual("invalid", result.status)
        self.assertIn("filesystem root", result.warnings[0])


if __name__ == "__main__":
    unittest.main()
