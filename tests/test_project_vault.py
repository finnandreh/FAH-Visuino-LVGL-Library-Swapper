from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.project_vault import (
    LINK_REGISTRY_SCHEMA_VERSION,
    ManagedJunctionService,
    ProjectVaultError,
    ProjectVaultService,
    WindowsJunctionBackend,
)


class ProjectVaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sketchbook = self.root / "Arduino"
        self.libraries = self.sketchbook / "libraries"
        self.vault = self.sketchbook / "FAH LVGL"
        self.state = self.root / "appdata" / "project-vault-links.json"
        self.service = ProjectVaultService(self.vault)
        self.service.initialize()
        self.revision_path = (
            self.vault
            / "Clients"
            / "client_acme"
            / "Projects"
            / "project_panel"
            / "Revisions"
            / "r001"
        )
        self.library_name = "FAH_ACME_Panel_r001"
        self.library = (
            self.revision_path / "libraries" / self.library_name
        )
        (self.library / "src" / "vendor" / "lvgl").mkdir(parents=True)
        (self.library / "library.properties").write_text(
            "name=FAH ACME Panel r001\n"
            "version=1.0.0\n"
            "author=FAH\n"
            "maintainer=FAH\n"
            "sentence=Project library.\n"
            "paragraph=Self-contained project library.\n"
            "category=Display\n"
            "url=https://finnandre.no\n"
            "architectures=esp32\n",
            encoding="utf-8",
        )
        (self.library / "src" / f"{self.library_name}.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )
        (self.library / "src" / "vendor" / "lvgl" / "lvgl.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )
        (self.revision_path / "FAH-ACME-Panel.ino").write_text(
            f"#include <{self.library_name}.h>\n",
            encoding="utf-8",
        )
        (self.revision_path / "project-meta.json").write_text(
            json.dumps({"schemaVersion": 1}),
            encoding="utf-8",
        )
        (self.revision_path / "ui-elements.json").write_text(
            json.dumps({"schemaVersion": 1, "elements": []}),
            encoding="utf-8",
        )
        self.manifest_path = self.revision_path / "fah-project.json"
        self.manifest = {
            "schemaVersion": 1,
            "revision": {"id": "r001", "immutable": True},
            "client": {"id": "client_acme", "name": "ACME"},
            "project": {"id": "project_panel", "name": "Panel"},
            "library": {
                "name": self.library_name,
                "relativePath": f"libraries/{self.library_name}",
                "selfContained": True,
                "lvgl": {"version": "8.4.0", "storage": "vendored"},
            },
            "handoff": {
                "rootIno": "FAH-ACME-Panel.ino",
                "projectMeta": "project-meta.json",
                "uiElements": "ui-elements.json",
            },
        }
        self._write_manifest(self.manifest)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_manifest(self, value: dict) -> None:
        self.manifest_path.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )

    def _junction_service(
        self, *, running: bool = False
    ) -> ManagedJunctionService:
        return ManagedJunctionService(
            libraries_path=self.libraries,
            vault_root=self.vault,
            state_path=self.state,
            running_check=lambda: running,
        )

    def _create_second_revision(self):
        second_revision_path = (
            self.vault
            / "Clients"
            / "client_acme"
            / "Projects"
            / "project_panel"
            / "Revisions"
            / "r002"
        )
        shutil.copytree(self.revision_path, second_revision_path)
        second_library_name = "FAH_ACME_Panel_r002"
        old_library = second_revision_path / "libraries" / self.library_name
        second_library = second_revision_path / "libraries" / second_library_name
        old_library.rename(second_library)
        old_header = second_library / "src" / f"{self.library_name}.h"
        old_header.rename(second_library / "src" / f"{second_library_name}.h")
        (second_revision_path / "FAH-ACME-Panel.ino").write_text(
            f"#include <{second_library_name}.h>\n",
            encoding="utf-8",
        )
        manifest_path = second_revision_path / "fah-project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["revision"]["id"] = "r002"
        manifest["library"]["name"] = second_library_name
        manifest["library"]["relativePath"] = (
            f"libraries/{second_library_name}"
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.service.load_revision(manifest_path)

    def test_valid_manifest_loads_and_scans(self) -> None:
        revision = self.service.load_revision(self.manifest_path)
        inventory = self.service.scan()

        self.assertEqual("ACME / Panel / r001 / FAH_ACME_Panel_r001", revision.display_path)
        self.assertEqual(self.library.resolve(), revision.library_path)
        self.assertEqual("8.4.0", revision.lvgl_version)
        self.assertEqual((revision,), inventory.revisions)
        self.assertEqual((), inventory.issues)

    def test_manifest_rejects_path_escape_and_non_vendored_lvgl(self) -> None:
        escaping = json.loads(json.dumps(self.manifest))
        escaping["library"]["relativePath"] = "../outside"
        self._write_manifest(escaping)
        with self.assertRaisesRegex(ProjectVaultError, "relativePath must be"):
            self.service.load_revision(self.manifest_path)

        shared = json.loads(json.dumps(self.manifest))
        shared["library"]["lvgl"]["storage"] = "shared_junction"
        self._write_manifest(shared)
        with self.assertRaisesRegex(ProjectVaultError, "only vendored"):
            self.service.load_revision(self.manifest_path)

    def test_manifest_requires_exact_hierarchy_and_one_root_ino(self) -> None:
        invalid = json.loads(json.dumps(self.manifest))
        invalid["client"]["id"] = "client_other"
        self._write_manifest(invalid)
        with self.assertRaisesRegex(ProjectVaultError, "directory hierarchy"):
            self.service.load_revision(self.manifest_path)

        self._write_manifest(self.manifest)
        (self.revision_path / "Second.ino").write_text(
            "void setup() {}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProjectVaultError, "exactly one root INO"):
            self.service.load_revision(self.manifest_path)

    @unittest.skipUnless(
        os.name == "nt" and hasattr(os.path, "isjunction"),
        "Windows directory junctions are required.",
    )
    def test_activation_creates_owned_junction_and_deactivation_preserves_target(
        self,
    ) -> None:
        revision = self.service.load_revision(self.manifest_path)
        junctions = self._junction_service()

        plan = junctions.plan(revision)
        self.assertEqual("create", plan.action)
        self.assertEqual("inactive", plan.status)

        result = junctions.activate(revision)
        link = self.libraries / self.library_name
        self.assertEqual("created", result.action)
        self.assertTrue(os.path.isjunction(link))
        self.assertEqual(self.library.resolve(), link.resolve())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(LINK_REGISTRY_SCHEMA_VERSION, state["schemaVersion"])
        self.assertEqual(self.library_name, state["links"][0]["name"])
        self.assertEqual("active", junctions.status(revision))
        active = junctions.active_links()
        self.assertEqual(1, len(active))
        self.assertTrue(active[0].verified)
        self.assertEqual("client_acme", active[0].client_id)
        self.assertEqual("project_panel", active[0].project_id)
        self.assertEqual("r001", active[0].revision_id)
        self.assertTrue(active[0].linked_at)

        removed = junctions.deactivate(self.library_name)
        self.assertEqual("removed", removed.action)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(self.library.is_dir())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual([], state["links"])

    @unittest.skipUnless(
        os.name == "nt" and hasattr(os.path, "isjunction"),
        "Windows directory junctions are required.",
    )
    def test_switch_keeps_exactly_one_active_link_and_preserves_both_targets(
        self,
    ) -> None:
        first_revision = self.service.load_revision(self.manifest_path)
        second_revision = self._create_second_revision()
        junctions = self._junction_service()

        junctions.activate(first_revision)
        plan = junctions.plan(second_revision)
        self.assertEqual("switch", plan.action)
        self.assertEqual(self.library_name, plan.previous_library_name)

        result = junctions.activate(second_revision)

        first_link = self.libraries / self.library_name
        second_link = self.libraries / second_revision.library_name
        self.assertEqual("switched", result.action)
        self.assertEqual(self.library_name, result.previous_library_name)
        self.assertFalse(os.path.lexists(first_link))
        self.assertTrue(os.path.isjunction(second_link))
        self.assertEqual(second_revision.library_path, second_link.resolve())
        self.assertTrue(first_revision.library_path.is_dir())
        self.assertTrue(second_revision.library_path.is_dir())

        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(1, len(state["links"]))
        self.assertEqual(second_revision.library_name, state["links"][0]["name"])
        self.assertEqual("r002", state["links"][0]["revisionId"])
        active = junctions.active_links()
        self.assertEqual(1, len(active))
        self.assertTrue(active[0].verified)
        self.assertEqual(second_revision.library_name, active[0].library_name)

        junctions.deactivate(second_revision.library_name)

    @unittest.skipUnless(
        os.name == "nt" and hasattr(os.path, "isjunction"),
        "Windows directory junctions are required.",
    )
    def test_failed_switch_restores_previous_link_and_manifest(self) -> None:
        first_revision = self.service.load_revision(self.manifest_path)
        second_revision = self._create_second_revision()
        junctions = self._junction_service()
        junctions.activate(first_revision)
        original_save = junctions.repository.save

        def fail_save(_data: dict) -> None:
            raise RuntimeError("simulated state persistence failure")

        junctions.repository.save = fail_save
        try:
            with self.assertRaisesRegex(
                ProjectVaultError,
                "previous verified junction.*restored",
            ):
                junctions.activate(second_revision)
        finally:
            junctions.repository.save = original_save

        first_link = self.libraries / self.library_name
        second_link = self.libraries / second_revision.library_name
        self.assertTrue(os.path.isjunction(first_link))
        self.assertEqual(first_revision.library_path, first_link.resolve())
        self.assertFalse(os.path.lexists(second_link))
        self.assertTrue(first_revision.library_path.is_dir())
        self.assertTrue(second_revision.library_path.is_dir())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(1, len(state["links"]))
        self.assertEqual(self.library_name, state["links"][0]["name"])

        junctions.deactivate(self.library_name)

    def test_activation_blocks_real_folder_conflict(self) -> None:
        revision = self.service.load_revision(self.manifest_path)
        conflict = self.libraries / self.library_name
        conflict.mkdir(parents=True)
        junctions = self._junction_service()

        plan = junctions.plan(revision)
        self.assertEqual("blocked", plan.action)
        self.assertEqual("conflict", plan.status)
        with self.assertRaisesRegex(ProjectVaultError, "real folder"):
            junctions.activate(revision)
        self.assertTrue(conflict.is_dir())

    @unittest.skipUnless(
        os.name == "nt" and hasattr(os.path, "isjunction"),
        "Windows directory junctions are required.",
    )
    def test_activation_blocks_foreign_junction(self) -> None:
        revision = self.service.load_revision(self.manifest_path)
        self.libraries.mkdir(parents=True)
        link = self.libraries / self.library_name
        WindowsJunctionBackend().create(self.library, link)

        junctions = self._junction_service()
        plan = junctions.plan(revision)
        self.assertEqual("blocked", plan.action)
        self.assertIn("not owned", plan.message)
        with self.assertRaisesRegex(ProjectVaultError, "not owned"):
            junctions.activate(revision)
        self.assertTrue(os.path.isjunction(link))

        WindowsJunctionBackend().remove(link)
        self.assertTrue(self.library.is_dir())

    def test_activation_is_blocked_while_visuino_is_running(self) -> None:
        revision = self.service.load_revision(self.manifest_path)
        with self.assertRaisesRegex(ProjectVaultError, "Close Visuino"):
            self._junction_service(running=True).activate(revision)

    def test_service_requires_sibling_normal_libraries_and_vault_roots(self) -> None:
        with self.assertRaisesRegex(ProjectVaultError, "sibling"):
            ManagedJunctionService(
                libraries_path=self.root / "other" / "libraries",
                vault_root=self.vault,
                state_path=self.state,
            )
        with self.assertRaisesRegex(ProjectVaultError, "normal sketchbook"):
            ManagedJunctionService(
                libraries_path=self.sketchbook / "not-libraries",
                vault_root=self.vault,
                state_path=self.state,
            )


if __name__ == "__main__":
    unittest.main()
