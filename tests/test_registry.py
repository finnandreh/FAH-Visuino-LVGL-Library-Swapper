from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.registry import (
    RegistryRepository,
    RegistryService,
)


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = RegistryRepository(
            self.root / "registry.json", self.root / "registry.previous.json"
        )
        self.registry = RegistryService(self.repository)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_crud_persists_stable_hierarchy(self) -> None:
        setup_folder = self.root / "profiles" / "Release A"
        setup_folder.mkdir(parents=True)
        client_id = self.registry.create_client("Northwind")
        project_id = self.registry.create_project(client_id, "Display")
        setup_id = self.registry.create_setup(
            client_id, project_id, "Release A", setup_folder
        )
        self.registry.update_validation(
            setup_id,
            status="valid",
            checked_at="2026-07-24T12:00:00+02:00",
            warnings=[],
        )
        self.registry.set_active_setup(setup_id)

        reloaded = RegistryService(self.repository)
        setup = reloaded.find_setup(setup_id)
        self.assertEqual("Release A", setup["name"])
        self.assertEqual(str(setup_folder.resolve()), setup["folderPath"])
        self.assertEqual("valid", setup["validation"]["status"])
        self.assertEqual(setup_id, reloaded.data["activeSetupId"])
        self.assertTrue((self.root / "registry.previous.json").is_file())

    def test_invalid_current_registry_falls_back_to_previous(self) -> None:
        client_id = self.registry.create_client("Client A")
        self.registry.rename_client(client_id, "Client B")
        (self.root / "registry.json").write_text("{broken", encoding="utf-8")

        recovered = self.repository.load()
        self.assertEqual("Client A", recovered["clients"][0]["name"])

    def test_duplicate_names_are_rejected_case_insensitively(self) -> None:
        self.registry.create_client("Example")
        with self.assertRaisesRegex(Exception, "already exists"):
            self.registry.create_client("example")

    def test_saved_file_is_valid_json(self) -> None:
        self.registry.create_client("Example")
        data = json.loads((self.root / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(3, data["schemaVersion"])

    def test_setup_profile_can_be_renamed_and_removed_without_deleting_folder(
        self,
    ) -> None:
        setup_folder = self.root / "profiles" / "Preserved"
        setup_folder.mkdir(parents=True)
        marker = setup_folder / "keep-me.txt"
        marker.write_text("preserved", encoding="utf-8")
        client_id = self.registry.create_client("Client")
        project_id = self.registry.create_project(client_id, "Project")
        setup_id = self.registry.create_setup(
            client_id,
            project_id,
            "Original",
            setup_folder,
        )

        self.registry.rename_setup(
            client_id,
            project_id,
            setup_id,
            "Renamed",
        )
        removed = self.registry.remove_setup(
            client_id,
            project_id,
            setup_id,
        )

        self.assertEqual("Renamed", removed["name"])
        self.assertEqual(str(setup_folder.resolve()), removed["folderPath"])
        self.assertTrue(marker.is_file())
        with self.assertRaisesRegex(Exception, "Unknown setup ID"):
            self.registry.find_setup(setup_id)
        reloaded = RegistryService(self.repository)
        self.assertEqual([], reloaded.find_project(client_id, project_id)["setups"])

    def test_active_setup_profile_cannot_be_removed(self) -> None:
        setup_folder = self.root / "profiles" / "Active"
        setup_folder.mkdir(parents=True)
        client_id = self.registry.create_client("Client")
        project_id = self.registry.create_project(client_id, "Project")
        setup_id = self.registry.create_setup(
            client_id,
            project_id,
            "Active",
            setup_folder,
        )
        self.registry.set_active_setup(setup_id)

        with self.assertRaisesRegex(Exception, "active setup profile"):
            self.registry.remove_setup(client_id, project_id, setup_id)

        self.assertEqual("Active", self.registry.find_setup(setup_id)["name"])
        self.assertTrue(setup_folder.is_dir())

    def test_setup_rename_rejects_duplicate_name(self) -> None:
        first_folder = self.root / "profiles" / "First"
        second_folder = self.root / "profiles" / "Second"
        first_folder.mkdir(parents=True)
        second_folder.mkdir(parents=True)
        client_id = self.registry.create_client("Client")
        project_id = self.registry.create_project(client_id, "Project")
        self.registry.create_setup(
            client_id,
            project_id,
            "First",
            first_folder,
        )
        second_id = self.registry.create_setup(
            client_id,
            project_id,
            "Second",
            second_folder,
        )

        with self.assertRaisesRegex(Exception, "already exists"):
            self.registry.rename_setup(
                client_id,
                project_id,
                second_id,
                "first",
            )

    def test_schema_one_registry_migrates_without_losing_setups(self) -> None:
        setup_folder = self.root / "profiles" / "Legacy"
        setup_folder.mkdir(parents=True)
        legacy = {
            "schemaVersion": 1,
            "activeSetupId": None,
            "defaultSetupId": None,
            "clients": [
                {
                    "id": "client_legacy",
                    "name": "Legacy Client",
                    "projects": [
                        {
                            "id": "project_legacy",
                            "name": "Legacy Project",
                            "setups": [
                                {
                                    "id": "setup_legacy",
                                    "name": "Legacy Setup",
                                    "folderPath": str(setup_folder),
                                    "baseline": {
                                        "mitovRequired": True,
                                        "visuinoProRequired": True,
                                    },
                                    "validation": {
                                        "status": "unknown",
                                        "lastValidatedAt": None,
                                        "warnings": [],
                                    },
                                    "createdAt": "2026-07-24T12:00:00+02:00",
                                    "updatedAt": "2026-07-24T12:00:00+02:00",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.repository.path.write_text(
            json.dumps(legacy),
            encoding="utf-8",
        )

        migrated = RegistryService(self.repository)
        setup = migrated.find_setup("setup_legacy")

        self.assertEqual(3, migrated.data["schemaVersion"])
        self.assertIsNone(setup["devicePackage"])
        self.assertFalse(setup["baseline"]["visuinoProRequired"])
        self.assertEqual("missing_only", setup["baseline"]["copyPolicy"])
        self.assertEqual("Legacy Setup", setup["name"])

    def test_schema_two_registry_migrates_optional_visuino_pro_policy(
        self,
    ) -> None:
        setup_folder = self.root / "profiles" / "Version Two"
        setup_folder.mkdir(parents=True)
        version_two = {
            "schemaVersion": 2,
            "activeSetupId": None,
            "defaultSetupId": None,
            "clients": [
                {
                    "id": "client_v2",
                    "name": "Version Two Client",
                    "projects": [
                        {
                            "id": "project_v2",
                            "name": "Version Two Project",
                            "setups": [
                                {
                                    "id": "setup_v2",
                                    "name": "Version Two Setup",
                                    "folderPath": str(setup_folder),
                                    "baseline": {
                                        "mitovRequired": True,
                                        "visuinoProRequired": True,
                                    },
                                    "validation": {
                                        "status": "unknown",
                                        "lastValidatedAt": None,
                                        "warnings": [],
                                    },
                                    "devicePackage": None,
                                    "createdAt": "2026-07-24T12:00:00+02:00",
                                    "updatedAt": "2026-07-24T12:00:00+02:00",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.repository.path.write_text(
            json.dumps(version_two),
            encoding="utf-8",
        )

        migrated = RegistryService(self.repository)
        setup = migrated.find_setup("setup_v2")

        self.assertEqual(3, migrated.data["schemaVersion"])
        self.assertFalse(setup["baseline"]["visuinoProRequired"])
        self.assertEqual("missing_only", setup["baseline"]["copyPolicy"])


if __name__ == "__main__":
    unittest.main()
