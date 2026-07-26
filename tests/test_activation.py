from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.activation import ActivationService
from lvgl_visuino_setup_manager.paths import AppPaths
from lvgl_visuino_setup_manager.visuino_config import (
    RegistryValue,
    read_directories_user,
)


class FakeRegistry:
    def __init__(self, value: str, kind: int = 2) -> None:
        self.current = RegistryValue(value, kind)

    def read(self) -> RegistryValue:
        return self.current

    def write(self, value: str, kind: int | None = None) -> None:
        self.current = RegistryValue(value, 2 if kind is None else kind)

    def restore(self, original: RegistryValue) -> None:
        self.current = original


class FakeProcess:
    def __init__(self, pid: int = 1234) -> None:
        self.pid = pid
        self.return_code: int | None = None

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.return_code = 0

    def wait(self, timeout: float | None = None) -> int:
        self.return_code = 0
        return 0

    def kill(self) -> None:
        self.return_code = -9


class ActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = AppPaths.discover(self.root / "appdata")
        self.paths.ensure()
        self.yaml_path = self.root / "Arduino15" / "arduino-cli.yaml"
        self.yaml_path.parent.mkdir()
        self.original_yaml = (
            "directories:\n"
            '    data: "C:\\\\Arduino15"\n'
            '    user: "C:\\\\Original"\n'
            "logging:\n"
            "    level: info\n"
        ).encode("utf-8")
        self.yaml_path.write_bytes(self.original_yaml)
        self.registry = FakeRegistry("C:\\Original\\libraries\\")
        self.executable = self.root / "VisuinoPro.exe"
        self.executable.touch()
        self.setup = self.root / "profiles" / "Release A"
        self.libraries = self.setup / "libraries"
        (self.libraries / "Mitov").mkdir(parents=True)
        (self.libraries / "VisuinoPro").mkdir()
        self.launched: list[list[str]] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def launcher_with_valid_cache(self, arguments: list[str]) -> FakeProcess:
        self.launched.append(arguments)
        cache_argument = next(
            (item for item in arguments if item.startswith("-CACHE")), None
        )
        if cache_argument:
            cache = Path(cache_argument[len("-CACHE") :])
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "DynamicDefinitions.txt").write_text(
                f"{self.libraries / 'Mitov'}\n"
                f"{self.libraries / 'VisuinoPro'}\n",
                encoding="utf-8",
            )
        return FakeProcess()

    def build_service(self, launcher) -> ActivationService:
        return ActivationService(
            self.paths,
            yaml_path=self.yaml_path,
            executable=self.executable,
            registry=self.registry,
            running_check=lambda: False,
            launcher=launcher,
            command_line_reader=lambda _pid: " ".join(self.launched[-1]),
            sleep=lambda _seconds: None,
            cache_timeout=1,
            startup_wait=0,
        )

    def test_activation_writes_pair_verifies_cache_and_captures_default(self) -> None:
        service = self.build_service(self.launcher_with_valid_cache)
        result = service.activate("setup_release_a", self.setup)

        self.assertEqual(
            f"{self.libraries}\\",
            self.registry.current.value,
        )
        current_yaml = self.yaml_path.read_text(encoding="utf-8")
        self.assertEqual(str(self.setup), read_directories_user(current_yaml))
        self.assertTrue(service.default_snapshot_exists)
        snapshot_metadata = json.loads(
            (self.paths.default_snapshot / "state.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("yamlSha256", snapshot_metadata)
        self.assertEqual(1234, result.process_id)
        self.assertIn("-REBUILD_CACHE", self.launched[0])

    def test_failed_launch_restores_exact_original_configuration(self) -> None:
        def failing_launcher(_arguments: list[str]) -> FakeProcess:
            raise OSError("simulated launch failure")

        service = self.build_service(failing_launcher)
        with self.assertRaisesRegex(Exception, "previous configuration was restored"):
            service.activate("setup_release_a", self.setup)

        self.assertEqual("C:\\Original\\libraries\\", self.registry.current.value)
        self.assertEqual(self.original_yaml, self.yaml_path.read_bytes())

    def test_restore_default_reverses_a_successful_activation(self) -> None:
        service = self.build_service(self.launcher_with_valid_cache)
        service.activate("setup_release_a", self.setup)
        result = service.restore_default()

        self.assertEqual("C:\\Original\\libraries\\", self.registry.current.value)
        self.assertEqual(self.original_yaml, self.yaml_path.read_bytes())
        self.assertEqual(1234, result.process_id)
        self.assertEqual([str(self.executable.resolve())], self.launched[-1])

    def test_activation_accepts_mitov_only_and_verifies_that_cache(self) -> None:
        (self.libraries / "VisuinoPro").rmdir()

        def launcher(arguments: list[str]) -> FakeProcess:
            self.launched.append(arguments)
            cache_argument = next(
                (item for item in arguments if item.startswith("-CACHE")),
                None,
            )
            if cache_argument:
                cache = Path(cache_argument[len("-CACHE") :])
                cache.mkdir(parents=True, exist_ok=True)
                (cache / "DynamicDefinitions.txt").write_text(
                    f"{self.libraries / 'Mitov'}\n",
                    encoding="utf-8",
                )
            return FakeProcess()

        service = self.build_service(launcher)
        result = service.activate("setup_release_a", self.setup)

        self.assertEqual(1234, result.process_id)
        self.assertTrue(service.default_snapshot_exists)


if __name__ == "__main__":
    unittest.main()
