from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .paths import AppPaths, resolve_safe_directory
from .setup_service import SetupService
from .visuino_config import (
    ConfigurationError,
    RegistryValue,
    VisuinoRegistryBackend,
    WindowsVisuinoRegistry,
    atomic_write_bytes,
    read_directories_user,
    write_directories_user,
)


class ActivationError(RuntimeError):
    """Raised when a guarded activation or restore cannot complete safely."""


class ProcessHandle(Protocol):
    pid: int

    def poll(self) -> int | None:
        ...

    def terminate(self) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...

    def kill(self) -> None:
        ...


@dataclass(frozen=True)
class ActivationResult:
    setup_path: Path
    cache_path: Path
    backup_path: Path
    process_id: int
    message: str


@dataclass(frozen=True)
class RestoreResult:
    backup_path: Path
    process_id: int
    restored_registry_path: str
    message: str


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    registry: RegistryValue
    yaml_bytes: bytes


def default_yaml_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Arduino15" / "arduino-cli.yaml"
    return Path.home() / "AppData" / "Local" / "Arduino15" / "arduino-cli.yaml"


def is_visuino_running() -> bool:
    if os.name != "nt":
        return False
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        errors="ignore",
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if completed.returncode != 0:
        raise ActivationError("Cannot verify whether Visuino is running.")
    output = completed.stdout.casefold()
    return '"visuinopro.exe"' in output or '"visuino.exe"' in output


def launch_process(arguments: list[str]) -> ProcessHandle:
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        arguments,
        cwd=str(Path(arguments[0]).parent),
        creationflags=creation_flags,
    )


def read_process_command_line(process_id: int) -> str:
    if os.name != "nt":
        return ""
    script = (
        f"(Get-CimInstance Win32_Process -Filter "
        f"'ProcessId = {int(process_id)}').CommandLine"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        errors="ignore",
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    command_line = completed.stdout.strip()
    if completed.returncode != 0 or not command_line:
        raise ActivationError(
            f"Cannot verify the Visuino process command line for PID {process_id}."
        )
    return command_line


class ActivationService:
    def __init__(
        self,
        paths: AppPaths,
        *,
        yaml_path: Path | None = None,
        executable: Path | None = None,
        registry: VisuinoRegistryBackend | None = None,
        running_check: Callable[[], bool] = is_visuino_running,
        launcher: Callable[[list[str]], ProcessHandle] = launch_process,
        command_line_reader: Callable[[int], str] = read_process_command_line,
        sleep: Callable[[float], None] = time.sleep,
        cache_timeout: float = 180.0,
        startup_wait: float = 2.0,
    ) -> None:
        self.paths = paths
        self.yaml_path = yaml_path or default_yaml_path()
        self.executable = executable
        self.registry = registry or WindowsVisuinoRegistry()
        self.running_check = running_check
        self.launcher = launcher
        self.command_line_reader = command_line_reader
        self.sleep = sleep
        self.cache_timeout = cache_timeout
        self.startup_wait = startup_wait
        self.setup_service = SetupService()

    @property
    def default_snapshot_exists(self) -> bool:
        return (
            (self.paths.default_snapshot / "state.json").is_file()
            and (self.paths.default_snapshot / "arduino-cli.yaml").is_file()
        )

    def default_library_candidates(self) -> tuple[Path, ...]:
        raw_candidates: list[str | Path] = []
        if self.default_snapshot_exists:
            try:
                snapshot = self._load_snapshot(self.paths.default_snapshot)
                if snapshot.registry.value:
                    raw_candidates.append(snapshot.registry.value)
                snapshot_user = read_directories_user(
                    snapshot.yaml_bytes.decode("utf-8-sig")
                )
                if snapshot_user:
                    raw_candidates.append(snapshot_user)
            except (ActivationError, UnicodeDecodeError, ConfigurationError):
                pass
        try:
            current = self.registry.read()
            if current.value:
                raw_candidates.append(current.value)
        except ConfigurationError:
            pass
        if self.yaml_path.is_file():
            try:
                current_user = read_directories_user(
                    self.yaml_path.read_text(encoding="utf-8-sig")
                )
                if current_user:
                    raw_candidates.append(current_user)
            except (OSError, ConfigurationError):
                pass
        raw_candidates.append(Path.home() / "Documents" / "Arduino" / "libraries")

        candidates: list[Path] = []
        seen: set[str] = set()
        for raw in raw_candidates:
            value = str(raw).strip().rstrip("\\/")
            if not value:
                continue
            candidate = Path(os.path.expandvars(value)).expanduser().resolve(
                strict=False
            )
            key = str(candidate).casefold()
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
        return tuple(candidates)

    def find_executable(self) -> Path:
        candidates: list[Path] = []
        if self.executable:
            candidates.append(self.executable)
        configured = os.environ.get("VISUINO_PRO_EXE")
        if configured:
            candidates.append(Path(configured))
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(variable)
            if base:
                candidates.append(
                    Path(base) / "Mitov" / "Visuino Pro" / "VisuinoPro.exe"
                )
        candidates.append(
            Path(r"C:\Program Files (x86)\Mitov\Visuino Pro\VisuinoPro.exe")
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise ActivationError(
            "VisuinoPro.exe was not found. Set VISUINO_PRO_EXE to its full path."
        )

    def activate(self, setup_id: str, raw_setup_path: str | Path) -> ActivationResult:
        if self.running_check():
            raise ActivationError("Close Visuino Pro before activating a setup.")

        validation = self.setup_service.validate(raw_setup_path)
        if not validation.is_valid:
            raise ActivationError(" ".join(validation.warnings))
        setup_path = resolve_safe_directory(validation.setup_path, must_exist=True)
        executable = self.find_executable()
        cache_path = (self.paths.caches / setup_id).resolve()
        cache_path.mkdir(parents=True, exist_ok=True)

        backup = self._snapshot_current(
            label="pre-activation",
            details={"setupId": setup_id, "targetPath": str(setup_path)},
        )
        self._ensure_default_snapshot(backup)

        process: ProcessHandle | None = None
        try:
            self._write_target(setup_path)
            process = self.launcher(
                [
                    str(executable),
                    f"-CACHE{cache_path}",
                    "-REBUILD_CACHE",
                ]
            )
            self.sleep(self.startup_wait)
            if process.poll() is not None:
                raise ActivationError("Visuino exited before startup verification.")
            self._verify_launch_command(process.pid, cache_path)
            self._verify_cache(cache_path, setup_path, process)
        except Exception as error:
            if process is not None and process.poll() is None:
                self._stop_owned_process(process)
            rollback_error: Exception | None = None
            try:
                self._restore_snapshot(backup)
            except Exception as restore_error:
                rollback_error = restore_error
            if rollback_error:
                raise ActivationError(
                    f"Activation failed and automatic rollback also failed. "
                    f"Activation error: {error}. Rollback error: {rollback_error}. "
                    f"Backup: {backup.directory}"
                ) from error
            if isinstance(error, ActivationError):
                raise
            raise ActivationError(
                f"Activation failed and the previous configuration was restored: {error}"
            ) from error

        return ActivationResult(
            setup_path=setup_path,
            cache_path=cache_path,
            backup_path=backup.directory,
            process_id=process.pid,
            message="Visuino Pro started with the selected setup and verified cache.",
        )

    def restore_default(self) -> RestoreResult:
        if self.running_check():
            raise ActivationError("Close Visuino Pro before restoring the default setup.")
        if not self.default_snapshot_exists:
            raise ActivationError(
                "No default snapshot exists yet. It is captured before the first activation."
            )
        executable = self.find_executable()
        current_backup = self._snapshot_current(
            label="pre-default-restore",
            details={"target": "default"},
        )
        default_snapshot = self._load_snapshot(self.paths.default_snapshot)
        process: ProcessHandle | None = None
        try:
            self._restore_snapshot(default_snapshot)
            process = self.launcher([str(executable)])
            self.sleep(self.startup_wait)
            if process.poll() is not None:
                raise ActivationError("Visuino exited before restore verification.")
        except Exception as error:
            if process is not None and process.poll() is None:
                self._stop_owned_process(process)
            rollback_error: Exception | None = None
            try:
                self._restore_snapshot(current_backup)
            except Exception as restore_error:
                rollback_error = restore_error
            if rollback_error:
                raise ActivationError(
                    f"Default restore failed and rollback also failed. "
                    f"Restore error: {error}. Rollback error: {rollback_error}. "
                    f"Backup: {current_backup.directory}"
                ) from error
            if isinstance(error, ActivationError):
                raise
            raise ActivationError(
                f"Default restore failed and the previous configuration was restored: {error}"
            ) from error

        return RestoreResult(
            backup_path=current_backup.directory,
            process_id=process.pid,
            restored_registry_path=default_snapshot.registry.value or "",
            message="The recorded default Visuino configuration was restored and started.",
        )

    def _write_target(self, setup_path: Path) -> None:
        libraries_path = self.setup_service.libraries_path(setup_path)
        registry_path = f"{str(libraries_path).rstrip('/\\')}\\"
        try:
            self.registry.write(registry_path)
            write_directories_user(self.yaml_path, str(setup_path))
            actual_registry = self.registry.read()
            yaml_text = self.yaml_path.read_text(encoding="utf-8-sig")
            actual_yaml = read_directories_user(yaml_text)
        except (OSError, ConfigurationError) as error:
            raise ActivationError(f"Cannot write Visuino configuration: {error}") from error

        if actual_registry.value is None or (
            actual_registry.value.rstrip("\\/").casefold()
            != str(libraries_path).rstrip("\\/").casefold()
        ):
            raise ActivationError(
                "Visuino registry read-back did not match the setup libraries."
            )
        if actual_yaml.rstrip("\\/").casefold() != str(setup_path).rstrip("\\/").casefold():
            raise ActivationError("Arduino15 YAML read-back did not match the setup.")

    def _snapshot_current(self, *, label: str, details: dict[str, str]) -> Snapshot:
        if not self.yaml_path.is_file():
            raise ActivationError(f"Visuino Arduino CLI YAML was not found: {self.yaml_path}")
        try:
            registry_value = self.registry.read()
            yaml_bytes = self.yaml_path.read_bytes()
        except (OSError, ConfigurationError) as error:
            raise ActivationError(f"Cannot back up Visuino configuration: {error}") from error

        operation_id = (
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{label}-{uuid.uuid4().hex[:8]}"
        )
        directory = self.paths.backups / operation_id
        directory.mkdir(parents=True, exist_ok=False)
        metadata = {
            "schemaVersion": 1,
            "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "label": label,
            "yamlPath": str(self.yaml_path),
            "registryValue": registry_value.value,
            "registryKind": registry_value.kind,
            "details": details,
        }
        atomic_write_bytes(directory / "arduino-cli.yaml", yaml_bytes)
        atomic_write_bytes(
            directory / "state.json",
            (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        )
        return Snapshot(directory, registry_value, yaml_bytes)

    def _ensure_default_snapshot(self, source: Snapshot) -> None:
        if self.default_snapshot_exists:
            return
        if self.paths.default_snapshot.exists():
            raise ActivationError(
                f"The default snapshot is incomplete: {self.paths.default_snapshot}"
            )
        self.paths.default_snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix="default.", dir=str(self.paths.default_snapshot.parent)
            )
        )
        try:
            shutil.copy2(source.directory / "arduino-cli.yaml", temporary)
            shutil.copy2(source.directory / "state.json", temporary)
            self._load_snapshot(temporary)
            os.replace(temporary, self.paths.default_snapshot)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def _load_snapshot(self, directory: Path) -> Snapshot:
        try:
            metadata = json.loads((directory / "state.json").read_text(encoding="utf-8"))
            yaml_bytes = (directory / "arduino-cli.yaml").read_bytes()
            registry = RegistryValue(
                metadata.get("registryValue"), metadata.get("registryKind")
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ActivationError(f"Invalid configuration snapshot {directory}: {error}") from error
        return Snapshot(directory, registry, yaml_bytes)

    def _restore_snapshot(self, snapshot: Snapshot) -> None:
        try:
            self.registry.restore(snapshot.registry)
            atomic_write_bytes(self.yaml_path, snapshot.yaml_bytes)
            actual_registry = self.registry.read()
            actual_yaml = self.yaml_path.read_bytes()
        except (OSError, ConfigurationError) as error:
            raise ActivationError(f"Cannot restore configuration snapshot: {error}") from error
        if actual_registry != snapshot.registry:
            raise ActivationError("Registry restore verification failed.")
        if actual_yaml != snapshot.yaml_bytes:
            raise ActivationError("YAML restore verification failed.")

    def _verify_cache(
        self, cache_path: Path, setup_path: Path, process: ProcessHandle
    ) -> None:
        definitions = cache_path / "DynamicDefinitions.txt"
        libraries_path = self.setup_service.libraries_path(setup_path)
        expected_paths = [
            str(libraries_path / "Mitov").replace("/", "\\").casefold()
        ]
        if (libraries_path / "VisuinoPro").is_dir():
            expected_paths.append(
                str(libraries_path / "VisuinoPro")
                .replace("/", "\\")
                .casefold()
            )
        deadline = time.monotonic() + self.cache_timeout
        last_size = -1
        stable_reads = 0

        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ActivationError("Visuino exited while rebuilding the setup cache.")
            if definitions.is_file():
                try:
                    content = (
                        self._read_definition_text(definitions)
                        .replace("/", "\\")
                        .casefold()
                    )
                    size = definitions.stat().st_size
                except OSError:
                    content = ""
                    size = -1
                if size == last_size and size > 0:
                    stable_reads += 1
                else:
                    stable_reads = 0
                last_size = size
                if stable_reads >= 1 and all(
                    expected in content for expected in expected_paths
                ):
                    return
            self.sleep(0.5)
        expected_names = (
            "Mitov and optional VisuinoPro"
            if len(expected_paths) == 2
            else "Mitov"
        )
        raise ActivationError(
            f"Visuino started, but its setup cache did not verify {expected_names} "
            f"within {self.cache_timeout:.0f} seconds."
        )

    def _verify_launch_command(self, process_id: int, cache_path: Path) -> None:
        command_line = self.command_line_reader(process_id).casefold()
        expected_cache = f"-cache{cache_path}".casefold()
        if expected_cache not in command_line:
            raise ActivationError(
                "The launched Visuino process did not use the selected setup cache."
            )
        if "-rebuild_cache" not in command_line:
            raise ActivationError(
                "The launched Visuino process did not request a cache rebuild."
            )

    @staticmethod
    def _read_definition_text(path: Path) -> str:
        raw = path.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16", errors="ignore")
        if raw.count(b"\x00") > len(raw) // 8:
            return raw.decode("utf-16-le", errors="ignore")
        return raw.decode("utf-8", errors="ignore")

    @staticmethod
    def _stop_owned_process(process: ProcessHandle) -> None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
