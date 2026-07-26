from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.audit import AuditRepository
from lvgl_visuino_setup_manager.controller import ApplicationController
from lvgl_visuino_setup_manager.profile_cleanup import (
    CLEAR_CONTENTS,
    DELETE_WITH_FOLDER,
    ProfileCleanupError,
    ProfileCleanupService,
)
from lvgl_visuino_setup_manager.registry import (
    RegistryError,
    RegistryRepository,
    RegistryService,
)
from lvgl_visuino_setup_manager.setup_service import SetupService


class FakeTrash:
    def __init__(self, target: Path, *, fail: bool = False) -> None:
        self.target = target
        self.fail = fail
        self.calls: list[Path] = []

    def __call__(self, source: str) -> None:
        source_path = Path(source)
        self.calls.append(source_path)
        if self.fail:
            raise OSError("simulated Recycle Bin failure")
        self.target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(self.target / source_path.name))


class ActivationStub:
    def __init__(self, *, running: bool = False) -> None:
        self.running = running

    def running_check(self) -> bool:
        return self.running


class ProfileCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        repository = RegistryRepository(
            self.root / "registry.json",
            self.root / "registry.previous.json",
        )
        self.registry = RegistryService(repository)
        self.client_id = self.registry.create_client("Client")
        self.project_id = self.registry.create_project(
            self.client_id,
            "Project",
        )
        self.setup_path = self.root / "profiles" / "Release A"
        (self.setup_path / "libraries" / "Mitov").mkdir(parents=True)
        (self.setup_path / "libraries" / "Mitov" / "Mitov.h").write_text(
            "mitov",
            encoding="utf-8",
        )
        (self.setup_path / "notes").mkdir()
        (self.setup_path / "notes" / "readme.txt").write_text(
            "profile notes",
            encoding="utf-8",
        )
        self.setup_id = self.registry.create_setup(
            self.client_id,
            self.project_id,
            "Release A",
            self.setup_path,
        )
        self.fake_trash = FakeTrash(self.root / "fake-recycle-bin")
        self.activation = ActivationStub()
        self.controller = ApplicationController(
            registry=self.registry,
            setup_service=SetupService(),
            implementation_service=object(),  # type: ignore[arg-type]
            activation_service=self.activation,  # type: ignore[arg-type]
            audit=AuditRepository(self.root / "audit.jsonl"),
            profile_cleanup_service=ProfileCleanupService(
                trash=self.fake_trash,
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _preview(self, action: str = CLEAR_CONTENTS):
        return self.controller.plan_profile_cleanup(
            self.client_id,
            self.project_id,
            self.setup_id,
            action,
        )

    def test_preview_counts_without_changing_content(self) -> None:
        plan = self._preview()

        self.assertEqual(2, plan.inventory.file_count)
        self.assertEqual(3, plan.inventory.folder_count)
        self.assertEqual(
            len("mitov".encode()) + len("profile notes".encode()),
            plan.inventory.total_bytes,
        )
        self.assertTrue(self.setup_path.is_dir())
        self.assertEqual([], self.fake_trash.calls)

    def test_clear_recycles_content_retains_profile_and_resets_state(self) -> None:
        self.registry.update_validation(
            self.setup_id,
            status="valid",
            checked_at="2026-07-25T12:00:00+02:00",
            warnings=[],
        )
        self.registry.set_device_package(
            self.setup_id,
            {
                "id": "device_release_a",
                "revision": "1",
                "libraryFolder": "libraries/DeviceBridge",
                "manifestPath": "libraries/DeviceBridge/manifest.json",
                "sourcePath": "C:/source",
                "status": "valid",
                "warnings": [],
                "lastImportedAt": "2026-07-25T12:00:00+02:00",
            },
        )
        plan = self._preview()

        result = self.controller.execute_profile_cleanup(
            plan,
            plan.confirmation_phrase,
        )

        self.assertFalse(result.profile_removed)
        self.assertTrue((self.setup_path / "libraries").is_dir())
        self.assertEqual([], list((self.setup_path / "libraries").iterdir()))
        self.assertFalse((self.setup_path / "notes").exists())
        setup = self.registry.find_setup(self.setup_id)
        self.assertEqual("unknown", setup["validation"]["status"])
        self.assertIsNone(setup["validation"]["lastValidatedAt"])
        self.assertIsNone(setup["devicePackage"])
        recycled = list((self.root / "fake-recycle-bin").iterdir())
        self.assertEqual(1, len(recycled))
        self.assertTrue(
            (recycled[0] / "libraries" / "Mitov" / "Mitov.h").is_file()
        )

    def test_delete_recycles_folder_then_removes_only_selected_profile(self) -> None:
        other_path = self.root / "profiles" / "Release B"
        (other_path / "libraries").mkdir(parents=True)
        other_id = self.registry.create_setup(
            self.client_id,
            self.project_id,
            "Release B",
            other_path,
        )
        plan = self._preview(DELETE_WITH_FOLDER)

        result = self.controller.execute_profile_cleanup(
            plan,
            plan.confirmation_phrase,
        )

        self.assertTrue(result.profile_removed)
        self.assertFalse(self.setup_path.exists())
        with self.assertRaises(RegistryError):
            self.registry.find_setup(self.setup_id)
        self.assertEqual("Release B", self.registry.find_setup(other_id)["name"])
        recycled = list((self.root / "fake-recycle-bin").iterdir())
        self.assertEqual(1, len(recycled))

    def test_failed_recycle_bin_operation_restores_original_folder(self) -> None:
        failing = FakeTrash(self.root / "unused", fail=True)
        self.controller.profile_cleanup_service = ProfileCleanupService(
            trash=failing
        )
        plan = self._preview()

        with self.assertRaises(ProfileCleanupError) as raised:
            self.controller.execute_profile_cleanup(
                plan,
                plan.confirmation_phrase,
            )

        self.assertTrue(raised.exception.rollback_attempted)
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertTrue(
            (self.setup_path / "libraries" / "Mitov" / "Mitov.h").is_file()
        )
        self.assertEqual("Release A", self.registry.find_setup(self.setup_id)["name"])
        events = [
            json.loads(line)
            for line in (self.root / "audit.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertTrue(
            any(
                item["event"] == "setup.cleanup.rollback"
                and item["result"] == "success"
                for item in events
            )
        )

    def test_active_profile_is_blocked(self) -> None:
        self.registry.set_active_setup(self.setup_id)

        with self.assertRaisesRegex(ProfileCleanupError, "active profile"):
            self._preview()

        self.assertTrue(self.setup_path.exists())

    def test_running_visuino_is_blocked_even_for_inactive_profile(self) -> None:
        self.activation.running = True

        with self.assertRaisesRegex(ProfileCleanupError, "Close Visuino Pro"):
            self._preview()

    def test_overlapping_registered_profile_is_blocked(self) -> None:
        nested = self.setup_path / "nested-profile"
        nested.mkdir()
        self.registry.create_setup(
            self.client_id,
            self.project_id,
            "Nested",
            nested,
        )

        with self.assertRaisesRegex(ProfileCleanupError, "overlaps another"):
            self._preview()

    def test_exact_confirmation_is_required(self) -> None:
        plan = self._preview()

        with self.assertRaisesRegex(ProfileCleanupError, "Type exactly"):
            self.controller.execute_profile_cleanup(plan, "DELETE Release")

        self.assertTrue(self.setup_path.exists())
        self.assertEqual([], self.fake_trash.calls)

    def test_content_change_after_preview_requires_new_preview(self) -> None:
        plan = self._preview()
        (self.setup_path / "new.txt").write_text("new", encoding="utf-8")

        with self.assertRaisesRegex(ProfileCleanupError, "changed after"):
            self.controller.execute_profile_cleanup(
                plan,
                plan.confirmation_phrase,
            )

        self.assertTrue((self.setup_path / "new.txt").is_file())

    def test_missing_folder_suggests_registry_only_remove(self) -> None:
        missing = self.root / "missing-profile"
        missing_id = self.registry.create_setup(
            self.client_id,
            self.project_id,
            "Missing",
            missing,
        )

        with self.assertRaisesRegex(ProfileCleanupError, "Use Remove Profile"):
            self.controller.plan_profile_cleanup(
                self.client_id,
                self.project_id,
                missing_id,
                CLEAR_CONTENTS,
            )

    def test_protected_application_path_is_blocked(self) -> None:
        self.controller.profile_cleanup_service = ProfileCleanupService(
            trash=self.fake_trash,
            application_data_root=self.setup_path,
        )

        with self.assertRaisesRegex(ProfileCleanupError, "protected"):
            self._preview()

    def test_nested_symbolic_link_is_blocked_when_supported(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        link = self.setup_path / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symbolic links are unavailable: {error}")

        with self.assertRaisesRegex(
            ProfileCleanupError,
            "junction|symbolic link",
        ):
            self._preview()


if __name__ == "__main__":
    unittest.main()
