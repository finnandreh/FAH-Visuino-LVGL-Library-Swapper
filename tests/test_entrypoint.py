from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lvgl_visuino_setup_manager import __main__ as entrypoint


class EntrypointTests(unittest.TestCase):
    def test_frozen_application_uses_executable_directory_as_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = (
                Path(temporary)
                / "package"
                / "FAH-Visuino-LVGL-Library-Swapper.exe"
            )
            with (
                patch.object(entrypoint.sys, "frozen", True, create=True),
                patch.object(entrypoint.sys, "executable", str(executable)),
            ):
                workspace = entrypoint._application_workspace_root()

        self.assertEqual(executable.parent.resolve(), workspace)

    def test_controller_wires_project_vault_to_selected_normal_sketchbook(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sketchbook = root / "Custom Arduino"
            controller = entrypoint.build_controller(
                root / "data",
                sketchbook_root=sketchbook,
            )

            vault_root, libraries_path = controller.project_vault_locations()
            initialized = controller.initialize_project_vault()

            self.assertEqual(
                (sketchbook / "FAH LVGL").resolve(),
                vault_root,
            )
            self.assertEqual(
                (sketchbook / "libraries").resolve(),
                libraries_path,
            )
            self.assertEqual(vault_root, initialized)
            self.assertTrue((vault_root / "Clients").is_dir())
            self.assertTrue(libraries_path.is_dir())


if __name__ == "__main__":
    unittest.main()
