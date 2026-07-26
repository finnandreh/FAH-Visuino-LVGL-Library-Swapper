from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.audit import AuditRepository
from lvgl_visuino_setup_manager.controller import ApplicationController
from lvgl_visuino_setup_manager.registry import RegistryRepository, RegistryService
from lvgl_visuino_setup_manager.setup_service import (
    BaselineRepairError,
    SetupService,
)


class ActivationStub:
    def __init__(self, candidates: tuple[Path, ...], running: bool) -> None:
        self._candidates = candidates
        self._running = running

    def default_library_candidates(self) -> tuple[Path, ...]:
        return self._candidates

    def running_check(self) -> bool:
        return self._running


class BaselineControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        repository = RegistryRepository(
            self.root / "registry.json",
            self.root / "registry.previous.json",
        )
        self.registry = RegistryService(repository)
        client_id = self.registry.create_client("Client")
        project_id = self.registry.create_project(client_id, "Project")
        self.setup = self.root / "setup"
        self.setup.mkdir()
        self.libraries = self.setup / "libraries"
        self.libraries.mkdir()
        self.setup_id = self.registry.create_setup(
            client_id,
            project_id,
            "Setup",
            self.setup,
        )
        self.source = self.root / "default-libraries"
        (self.source / "Mitov").mkdir(parents=True)
        (self.source / "Mitov" / "Mitov.h").write_text(
            "mitov",
            encoding="utf-8",
        )
        self.activation = ActivationStub((self.source,), running=True)
        self.controller = ApplicationController(
            registry=self.registry,
            setup_service=SetupService(),
            implementation_service=object(),  # type: ignore[arg-type]
            activation_service=self.activation,  # type: ignore[arg-type]
            audit=AuditRepository(self.root / "audit.jsonl"),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_discovers_default_source_and_repairs_inactive_setup(self) -> None:
        source = self.controller.find_default_baseline_source(self.setup_id)
        self.assertEqual(self.source.resolve(), source)
        plan = self.controller.plan_baseline_repair(self.setup_id, source)

        result = self.controller.repair_setup_baseline(plan)

        self.assertEqual(("Mitov",), result.copied)
        self.assertTrue(
            (self.libraries / "Mitov" / "Mitov.h").is_file()
        )
        self.assertFalse((self.libraries / "VisuinoPro").exists())

    def test_blocks_repair_of_active_setup_while_visuino_runs(self) -> None:
        plan = self.controller.plan_baseline_repair(
            self.setup_id,
            self.source,
        )
        self.registry.set_active_setup(self.setup_id)

        with self.assertRaisesRegex(BaselineRepairError, "Close Visuino"):
            self.controller.repair_setup_baseline(plan)
        self.assertFalse((self.libraries / "Mitov").exists())

    def test_prefers_source_that_supplies_the_currently_missing_library(
        self,
    ) -> None:
        (self.libraries / "Mitov").mkdir()
        pro_source = self.root / "pro-default-libraries"
        (pro_source / "VisuinoPro").mkdir(parents=True)
        (pro_source / "VisuinoPro" / "VisuinoPro.h").write_text(
            "pro",
            encoding="utf-8",
        )
        self.controller.activation_service = ActivationStub(
            (self.source, pro_source),
            running=False,
        )  # type: ignore[assignment]

        source = self.controller.find_default_baseline_source(self.setup_id)
        self.assertEqual(pro_source.resolve(), source)
        plan = self.controller.plan_baseline_repair(self.setup_id, source)
        self.assertEqual(
            ("VisuinoPro",),
            tuple(item.name for item in plan.copies),
        )


if __name__ == "__main__":
    unittest.main()
