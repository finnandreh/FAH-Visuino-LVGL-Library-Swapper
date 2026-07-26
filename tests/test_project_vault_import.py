from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.project_vault import (
    ProjectVaultError,
    ProjectVaultService,
)
from lvgl_visuino_setup_manager.project_vault_import import (
    ProjectVaultImportRequest,
    ProjectVaultImportService,
)


class ProjectVaultImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "StandaloneDemo"
        self.source.mkdir()
        (self.source / "Demo.ino").write_text(
            "#include <DemoDevice.h>\n"
            "void setup() { demo_begin(); }\n"
            "void loop() { demo_loop(); }\n",
            encoding="utf-8",
        )
        (self.source / "project-meta.json").write_text(
            json.dumps({"projectName": "Demo"}),
            encoding="utf-8",
        )
        (self.source / "ui-elements.json").write_text(
            json.dumps({"schemaVersion": 1, "elements": []}),
            encoding="utf-8",
        )
        (self.source / "README.md").write_text(
            "# Demo\n\nStandalone test project.\n",
            encoding="utf-8",
        )
        (self.source / "lv_conf.h").write_text(
            "#pragma once\n#define LV_COLOR_DEPTH 16\n",
            encoding="utf-8",
        )
        include = self.source / "include"
        include.mkdir()
        (include / "DemoDevice.h").write_text(
            "#pragma once\nvoid demo_begin();\nvoid demo_loop();\n",
            encoding="utf-8",
        )
        project_src = self.source / "src"
        project_src.mkdir()
        (project_src / "DemoDevice.cpp").write_text(
            '#include "DemoDevice.h"\n'
            "void demo_begin() {}\n"
            "void demo_loop() {}\n",
            encoding="utf-8",
        )

        lvgl = self.source / "libraries" / "lvgl"
        (lvgl / "src").mkdir(parents=True)
        (lvgl / "library.properties").write_text(
            "name=lvgl\nversion=8.4.0\n",
            encoding="utf-8",
        )
        (lvgl / "lvgl.h").write_text(
            '#pragma once\n#include "src/lvgl.h"\n',
            encoding="utf-8",
        )
        (lvgl / "src" / "lvgl.h").write_text(
            "#pragma once\nvoid lv_init(void);\n",
            encoding="utf-8",
        )
        (lvgl / "src" / "lvgl.c").write_text(
            '#include "lvgl.h"\nvoid lv_init(void) {}\n',
            encoding="utf-8",
        )

        support = self.source / "libraries" / "SupportLib"
        (support / "src").mkdir(parents=True)
        (support / "library.properties").write_text(
            "name=SupportLib\nversion=1.2.3\n",
            encoding="utf-8",
        )
        (support / "support_conf.h").write_text(
            "#pragma once\n#define SUPPORT_VALUE 43\n",
            encoding="utf-8",
        )
        (support / "src" / "Support.h").write_text(
            "#pragma once\nint support_value();\n",
            encoding="utf-8",
        )
        (support / "src" / "Support.cpp").write_text(
            '#include "Support.h"\n'
            '#include "support_conf.h"\n'
            "int support_value() { return SUPPORT_VALUE; }\n",
            encoding="utf-8",
        )

        self.vault = ProjectVaultService(
            self.root / "Arduino" / "FAH LVGL"
        )
        self.importer = ProjectVaultImportService(self.vault)
        self.request = ProjectVaultImportRequest(
            source_path=self.source,
            client_id="client_fah",
            client_name="FAH",
            project_id="project_demo",
            project_name="Demo",
            revision_id="r001",
            library_name="FAH_Demo_r001",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plan_and_execute_create_one_immutable_self_contained_revision(
        self,
    ) -> None:
        original_ino = (self.source / "Demo.ino").read_bytes()

        plan = self.importer.plan(self.request)
        result = self.importer.execute(plan)

        revision = result.revision
        self.assertEqual("FAH / Demo / r001 / FAH_Demo_r001", revision.display_path)
        self.assertEqual("8.4.0", revision.lvgl_version)
        self.assertEqual(original_ino, revision.root_ino_path.read_bytes())
        self.assertEqual("r001.ino", revision.root_ino_path.name)
        self.assertTrue((revision.library_path / "src" / "DemoDevice.h").is_file())
        self.assertTrue((revision.library_path / "src" / "Support.cpp").is_file())
        self.assertTrue((revision.library_path / "src" / "support_conf.h").is_file())
        self.assertTrue(
            (
                revision.library_path
                / "src"
                / "vendor"
                / "lvgl"
                / "src"
                / "lvgl.c"
            ).is_file()
        )
        self.assertIn(
            'include "vendor/lvgl/lvgl.h"',
            (revision.library_path / "src" / "lvgl.h").read_text(
                encoding="utf-8"
            ),
        )
        self.assertTrue((self.source / "Demo.ino").is_file())
        self.assertEqual(1, len(self.vault.scan().revisions))

        with self.assertRaisesRegex(ProjectVaultError, "already exists"):
            self.importer.plan(self.request)

    def test_plan_rejects_case_insensitive_aggregate_source_collision(self) -> None:
        support = self.source / "libraries" / "SupportLib" / "src"
        (support / "demodevice.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ProjectVaultError, "same case-insensitive path"):
            self.importer.plan(self.request)

    def test_plan_requires_one_root_ino_and_required_metadata(self) -> None:
        (self.source / "Second.ino").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ProjectVaultError, "exactly one root INO"):
            self.importer.plan(self.request)

        (self.source / "Second.ino").unlink()
        (self.source / "ui-elements.json").unlink()
        with self.assertRaisesRegex(ProjectVaultError, "UI element metadata"):
            self.importer.plan(self.request)

    def test_execute_requires_reanalysis_after_source_size_change(self) -> None:
        plan = self.importer.plan(self.request)
        with (self.source / "README.md").open("a", encoding="utf-8") as stream:
            stream.write("Changed after analysis.\n")

        with self.assertRaisesRegex(ProjectVaultError, "changed after analysis"):
            self.importer.execute(plan)
        self.assertFalse(plan.revision_path.exists())

    def test_plan_rejects_generated_content(self) -> None:
        build = self.source / "build"
        build.mkdir()
        (build / "firmware.bin").write_bytes(b"generated")

        with self.assertRaisesRegex(ProjectVaultError, "generated folder"):
            self.importer.plan(self.request)


if __name__ == "__main__":
    unittest.main()
