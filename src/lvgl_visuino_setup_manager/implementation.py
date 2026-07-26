from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .paths import AppPaths, resolve_safe_directory


HOOK_FILE_NAME = "visuino-custom-code.json"
SKETCH_FILE_NAME = "visuino-import.ino"
MANIFEST_FILE_NAME = "device-package.json"
IMPORT_FILE_NAME = "standalone-import.json"
UI_ELEMENTS_FILE_NAME = "ui-elements.json"
DEFAULT_LIBRARY_NAME = "VisuinoCustomImplementation"
MAX_SKETCH_BYTES = 1_000_000
MAX_UI_ELEMENTS_BYTES = 1_000_000
MAX_UI_ELEMENTS = 2_000
PROTECTED_BASELINE = {"mitov", "visuinopro"}
UI_ELEMENT_DIRECTIONS = {
    "ui_to_custom_code",
    "custom_code_to_ui",
    "bidirectional",
    "event",
}
UI_ELEMENT_VALUE_TYPES = {"bool", "int", "float", "string", "enum", "event"}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".pio",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDED_FILE_SUFFIXES = {
    ".a",
    ".dll",
    ".dylib",
    ".elf",
    ".exe",
    ".map",
    ".o",
    ".obj",
    ".pdb",
    ".pyc",
    ".so",
}
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".inc",
    ".ino",
    ".s",
}
ENTRYPOINT_NAMES = {"main.c", "main.cc", "main.cpp"}
PACKAGE_STATUS_VALUES = {"unknown", "valid", "invalid"}


class ImplementationError(RuntimeError):
    """Raised when a standalone implementation cannot be imported safely."""


@dataclass(frozen=True)
class CustomCodeHooks:
    includes: str = ""
    globals: str = ""
    setup: str = ""
    loop: str = ""

    def validate(self) -> None:
        for label, value in (
            ("Includes", self.includes),
            ("Globals", self.globals),
            ("Setup", self.setup),
            ("Loop", self.loop),
        ):
            if not isinstance(value, str):
                raise ImplementationError(f"{label} code must be text.")
            if len(value.encode("utf-8")) > 1_000_000:
                raise ImplementationError(f"{label} code is larger than 1 MB.")

    def as_dict(self) -> dict[str, str]:
        self.validate()
        return {
            "includes": self.includes,
            "globals": self.globals,
            "setup": self.setup,
            "loop": self.loop,
        }


@dataclass(frozen=True)
class UiElementVariable:
    id: str
    name: str
    screen: str
    type: str
    lvgl_object: str
    direction: str
    value_type: str
    description: str
    range_min: int | float | None = None
    range_max: int | float | None = None
    range_step: int | float | None = None
    unit: str = ""
    events: tuple[str, ...] = ()
    read_api: str = ""
    write_api: str = ""
    bridge_namespace: str = ""
    visuino_input_code: str = ""
    visuino_loop_code: str = ""

    @property
    def range_text(self) -> str:
        if self.range_min is None and self.range_max is None:
            return self.unit or "—"
        limits = f"{self.range_min}…{self.range_max}"
        step = (
            f", step {self.range_step}"
            if self.range_step is not None
            else ""
        )
        unit = f" {self.unit}" if self.unit else ""
        return f"{limits}{step}{unit}"

    @property
    def events_text(self) -> str:
        return ", ".join(self.events) if self.events else "—"

    @property
    def read_copy_text(self) -> str:
        return self.visuino_loop_code or self.read_api

    @property
    def write_copy_text(self) -> str:
        return self.visuino_input_code or self.write_api


@dataclass(frozen=True)
class PlannedFile:
    destination: Path
    source: Path | None
    content: bytes | None
    size: int
    action: str


@dataclass(frozen=True)
class ImportPlan:
    setup_id: str
    setup_path: Path
    source_path: Path
    mode: str
    library_name: str
    files: tuple[PlannedFile, ...]
    target_roots: tuple[str, ...]
    warnings: tuple[str, ...]
    arduino_sketch: str
    sketch_origin: str
    ui_elements: tuple[UiElementVariable, ...]
    ui_elements_origin: str

    @property
    def add_count(self) -> int:
        return sum(item.action == "add" for item in self.files)

    @property
    def replace_count(self) -> int:
        return sum(item.action == "replace" for item in self.files)

    @property
    def unchanged_count(self) -> int:
        return sum(item.action == "unchanged" for item in self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    @property
    def changed(self) -> bool:
        return self.add_count + self.replace_count > 0


@dataclass(frozen=True)
class ImportResult:
    setup_id: str
    setup_path: Path
    source_path: Path
    mode: str
    library_name: str
    library_path: Path
    manifest_path: Path
    hooks_path: Path
    sketch_path: Path
    backup_path: Path
    file_count: int
    warnings: tuple[str, ...]
    imported_at: str


@dataclass(frozen=True)
class ImplementationValidation:
    status: str
    setup_path: Path
    library_name: str | None
    manifest_path: Path | None
    checked_files: int
    warnings: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


def _safe_library_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise ImplementationError("The implementation library name is empty.")
    if cleaned.casefold() in PROTECTED_BASELINE:
        raise ImplementationError(
            "Mitov and VisuinoPro are protected baseline library names."
        )
    return cleaned


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _format_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def _iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ImplementationService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def plan_import(
        self,
        setup_id: str,
        setup_path: str | Path,
        source_path: str | Path,
        library_name: str = DEFAULT_LIBRARY_NAME,
    ) -> ImportPlan:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        source = resolve_safe_directory(source_path, must_exist=True)
        library = _safe_library_name(library_name)
        if source == setup or _is_relative_to(source, setup):
            raise ImplementationError(
                "The import source cannot be the selected setup or a folder inside it."
            )

        mode = self._detect_mode(source)
        mapped: dict[Path, tuple[Path | None, bytes | None]] = {}
        warnings: list[str] = []

        libraries_root = self._find_libraries_root(source)
        if libraries_root is not None:
            self._map_library_root(
                libraries_root,
                setup,
                mapped,
                warnings,
            )
        elif (source / "library.properties").is_file():
            self._map_tree(source, setup / source.name, mapped)
        else:
            self._map_dependency_directories(source, setup, mapped, warnings)

        self._map_loose_project(source, setup, library, mapped)
        self._add_generated_library_files(setup, library, mapped)
        arduino_sketch, sketch_origin = self._prepare_arduino_sketch(
            source,
        )
        ui_elements, ui_elements_origin = self._prepare_ui_elements(source)
        ui_elements_source = source / UI_ELEMENTS_FILE_NAME
        if ui_elements_source.is_file():
            self._map_file(
                ui_elements_source,
                setup / library / "extras" / UI_ELEMENTS_FILE_NAME,
                mapped,
            )
        else:
            warnings.append(
                "No ui-elements.json was found; UI Element Variables will be empty."
            )
        self._map_content(
            arduino_sketch.encode("utf-8"),
            setup / library / "extras" / SKETCH_FILE_NAME,
            mapped,
        )

        planned_files: list[PlannedFile] = []
        for destination in sorted(mapped, key=lambda item: str(item).casefold()):
            source_file, content = mapped[destination]
            if content is None:
                if source_file is None:
                    raise ImplementationError("An import file has no source or content.")
                file_size = source_file.stat().st_size
            else:
                file_size = len(content)

            if destination.is_file():
                if source_file is not None:
                    unchanged = filecmp.cmp(
                        source_file,
                        destination,
                        shallow=False,
                    )
                elif content is not None:
                    unchanged = destination.read_bytes() == content
                else:
                    unchanged = False
                action = "unchanged" if unchanged else "replace"
            elif destination.exists():
                raise ImplementationError(
                    f"A directory blocks an imported file: {destination}"
                )
            else:
                action = "add"
            planned_files.append(
                PlannedFile(
                    destination=destination,
                    source=source_file,
                    content=content,
                    size=file_size,
                    action=action,
                )
            )

        target_roots = sorted(
            {
                item.destination.relative_to(setup).parts[0]
                for item in planned_files
            },
            key=str.casefold,
        )
        return ImportPlan(
            setup_id=setup_id,
            setup_path=setup,
            source_path=source,
            mode=mode,
            library_name=library,
            files=tuple(planned_files),
            target_roots=tuple(target_roots),
            warnings=tuple(warnings),
            arduino_sketch=arduino_sketch,
            sketch_origin=sketch_origin,
            ui_elements=ui_elements,
            ui_elements_origin=ui_elements_origin,
        )

    def install(self, plan: ImportPlan) -> ImportResult:
        setup = resolve_safe_directory(plan.setup_path, must_exist=True)
        source = resolve_safe_directory(plan.source_path, must_exist=True)
        if setup != plan.setup_path or source != plan.source_path:
            raise ImplementationError("Import paths changed after the dry run.")

        operation = f"{_format_timestamp()}_{plan.setup_id}_{uuid.uuid4().hex[:8]}"
        # Keep staging on the setup volume so the final os.replace operations
        # remain atomic even when a linked setup lives on another drive.
        stage_root = setup / f".lvgl-visuino-staging-{operation}"
        backup_root = self.paths.backups / "implementations" / operation
        stage_root.mkdir(parents=True, exist_ok=False)
        backup_root.mkdir(parents=True, exist_ok=False)
        previous_paths: dict[str, Path] = {}
        installed_roots: list[str] = []

        existing_hooks = self._read_hooks_if_present(
            setup / plan.library_name / "extras" / HOOK_FILE_NAME
        )

        try:
            for planned in plan.files:
                relative = planned.destination.relative_to(setup)
                staged = stage_root / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                if planned.content is not None:
                    staged.write_bytes(planned.content)
                elif planned.source is not None:
                    shutil.copy2(planned.source, staged)
                else:
                    raise ImplementationError(f"No source for {relative}")
                if not staged.is_file() or staged.stat().st_size != planned.size:
                    raise ImplementationError(
                        f"Staged file is missing or has the wrong size: {relative}"
                    )

            hooks_stage = (
                stage_root
                / plan.library_name
                / "extras"
                / HOOK_FILE_NAME
            )
            if existing_hooks is not None:
                self._write_json_atomic(hooks_stage, existing_hooks)

            imported_at = _iso_timestamp()
            manifest_relative = (
                Path(plan.library_name) / "extras" / MANIFEST_FILE_NAME
            )
            manifest_stage = stage_root / manifest_relative
            manifest = {
                "schemaVersion": 1,
                "packageId": "external_standalone",
                "revision": "1",
                "libraryFolder": plan.library_name,
                "sourcePath": str(source),
                "mode": plan.mode,
                "importedAt": imported_at,
                "files": [
                    {
                        "path": str(item.destination.relative_to(setup)),
                        "size": item.size,
                    }
                    for item in plan.files
                    if item.destination.name != SKETCH_FILE_NAME
                ],
                "warnings": list(plan.warnings),
            }
            self._write_json_atomic(manifest_stage, manifest)
            self._write_json_atomic(
                stage_root / plan.library_name / "extras" / IMPORT_FILE_NAME,
                {
                    "schemaVersion": 1,
                    "sourcePath": str(source),
                    "mode": plan.mode,
                    "targetRoots": list(plan.target_roots),
                    "arduinoSketch": str(
                        Path(plan.library_name) / "extras" / SKETCH_FILE_NAME
                    ),
                    "sketchOrigin": plan.sketch_origin,
                    "importedAt": imported_at,
                },
            )

            for root_name in plan.target_roots:
                target = setup / root_name
                if target.exists():
                    backup_target = backup_root / root_name
                    self._copy_path(target, backup_target)
                    self._verify_copy_inventory(target, backup_target)

            for root_name in plan.target_roots:
                target = setup / root_name
                staged = stage_root / root_name
                previous = setup / f".{root_name}.{uuid.uuid4().hex}.previous"
                if target.exists():
                    os.replace(target, previous)
                    previous_paths[root_name] = previous
                os.replace(staged, target)
                installed_roots.append(root_name)

            validation = self.validate(setup, plan.library_name)
            if not validation.is_valid:
                raise ImplementationError(
                    "Installed implementation failed verification: "
                    + " ".join(validation.warnings)
                )

            for previous in previous_paths.values():
                self._remove_path(previous)

            return ImportResult(
                setup_id=plan.setup_id,
                setup_path=setup,
                source_path=source,
                mode=plan.mode,
                library_name=plan.library_name,
                library_path=setup / plan.library_name,
                manifest_path=setup / manifest_relative,
                hooks_path=setup / plan.library_name / "extras" / HOOK_FILE_NAME,
                sketch_path=(
                    setup / plan.library_name / "extras" / SKETCH_FILE_NAME
                ),
                backup_path=backup_root,
                file_count=len(plan.files),
                warnings=plan.warnings,
                imported_at=imported_at,
            )
        except Exception:
            for root_name in reversed(installed_roots):
                target = setup / root_name
                if target.exists():
                    self._remove_path(target)
                previous = previous_paths.get(root_name)
                if previous is not None and previous.exists():
                    os.replace(previous, target)
            for root_name, previous in previous_paths.items():
                target = setup / root_name
                if previous.exists() and not target.exists():
                    os.replace(previous, target)
            raise
        finally:
            if stage_root.exists():
                self._remove_path(stage_root)

    def validate(
        self, setup_path: str | Path, library_name: str | None
    ) -> ImplementationValidation:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        if not library_name:
            return ImplementationValidation(
                status="invalid",
                setup_path=setup,
                library_name=None,
                manifest_path=None,
                checked_files=0,
                warnings=("No implementation library is registered.",),
            )
        library = _safe_library_name(library_name)
        manifest_path = setup / library / "extras" / MANIFEST_FILE_NAME
        warnings: list[str] = []
        checked = 0
        if not manifest_path.is_file():
            warnings.append(f"Implementation manifest is missing: {manifest_path}")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("schemaVersion") != 1:
                    warnings.append("Implementation manifest schema is unsupported.")
                files = manifest.get("files")
                if not isinstance(files, list):
                    warnings.append("Implementation manifest files must be a list.")
                else:
                    for entry in files:
                        if not isinstance(entry, dict):
                            warnings.append("Implementation manifest has an invalid file entry.")
                            continue
                        relative = Path(str(entry.get("path", "")))
                        if relative.is_absolute() or ".." in relative.parts:
                            warnings.append("Implementation manifest contains an unsafe path.")
                            continue
                        target = (setup / relative).resolve(strict=False)
                        if not _is_relative_to(target, setup):
                            warnings.append("Implementation file resolves outside the setup.")
                            continue
                        if not target.is_file():
                            warnings.append(f"Imported file is missing: {relative}")
                            continue
                        checked += 1
                        expected_size = entry.get("size")
                        if (
                            not isinstance(expected_size, int)
                            or target.stat().st_size != expected_size
                        ):
                            warnings.append(
                                f"Imported file size changed: {relative}"
                            )
            except (OSError, json.JSONDecodeError) as error:
                warnings.append(f"Implementation manifest cannot be read: {error}")

        try:
            self.load_visuino_sketch(setup, library)
        except ImplementationError as error:
            warnings.append(str(error))
        try:
            self.load_ui_elements(setup, library)
        except ImplementationError as error:
            warnings.append(str(error))
        return ImplementationValidation(
            status="valid" if not warnings else "invalid",
            setup_path=setup,
            library_name=library,
            manifest_path=manifest_path,
            checked_files=checked,
            warnings=tuple(warnings),
        )

    def load_ui_elements(
        self,
        setup_path: str | Path,
        library_name: str,
    ) -> tuple[UiElementVariable, ...]:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        library = _safe_library_name(library_name)
        path = setup / library / "extras" / UI_ELEMENTS_FILE_NAME
        if not path.is_file():
            return ()
        return self._read_ui_elements(path)

    def load_hooks(
        self, setup_path: str | Path, library_name: str
    ) -> CustomCodeHooks:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        library = _safe_library_name(library_name)
        path = setup / library / "extras" / HOOK_FILE_NAME
        if not path.is_file():
            return CustomCodeHooks()
        document = self._read_hooks_if_present(path)
        if document is None:
            return CustomCodeHooks()
        hooks = document.get("hooks")
        if not isinstance(hooks, dict):
            raise ImplementationError("Custom Code hook document is invalid.")
        result = CustomCodeHooks(
            includes=hooks.get("includes", ""),
            globals=hooks.get("globals", ""),
            setup=hooks.get("setup", ""),
            loop=hooks.get("loop", ""),
        )
        result.validate()
        return result

    def save_hooks(
        self,
        setup_path: str | Path,
        library_name: str,
        hooks: CustomCodeHooks,
    ) -> Path:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        library = _safe_library_name(library_name)
        hooks.validate()
        library_path = setup / library
        self._ensure_metadata_library(library_path, library)
        path = library_path / "extras" / HOOK_FILE_NAME
        self._write_json_atomic(
            path,
            {
                "schemaVersion": 1,
                "updatedAt": _iso_timestamp(),
                "hooks": hooks.as_dict(),
            },
        )
        sketch = self._compose_legacy_hooks(hooks, library)
        self.save_visuino_sketch(setup, library, sketch)
        manifest_path = library_path / "extras" / MANIFEST_FILE_NAME
        if not manifest_path.exists():
            self._write_json_atomic(
                manifest_path,
                {
                    "schemaVersion": 1,
                    "packageId": "manual_custom_code",
                    "revision": "1",
                    "libraryFolder": library,
                    "sourcePath": "manual",
                    "mode": "manual",
                    "importedAt": _iso_timestamp(),
                    "files": [],
                    "warnings": [],
                },
            )
        return path

    def load_visuino_sketch(
        self,
        setup_path: str | Path,
        library_name: str,
    ) -> str:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        library = _safe_library_name(library_name)
        path = setup / library / "extras" / SKETCH_FILE_NAME
        if path.is_file():
            try:
                sketch = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as error:
                raise ImplementationError(
                    f"Visuino Arduino sketch cannot be read: {error}"
                ) from error
            return self._validate_sketch(sketch)

        hooks = self.load_hooks(setup, library)
        if any(hooks.as_dict().values()):
            return self._compose_legacy_hooks(hooks, library)
        return self._default_arduino_sketch(library)

    def save_visuino_sketch(
        self,
        setup_path: str | Path,
        library_name: str,
        sketch: str,
    ) -> Path:
        setup = resolve_safe_directory(setup_path, must_exist=True)
        library = _safe_library_name(library_name)
        validated = self._validate_sketch(sketch)
        library_path = setup / library
        self._ensure_metadata_library(library_path, library)
        path = library_path / "extras" / SKETCH_FILE_NAME
        self._write_text_atomic(path, validated)
        manifest_path = library_path / "extras" / MANIFEST_FILE_NAME
        if not manifest_path.exists():
            self._write_json_atomic(
                manifest_path,
                {
                    "schemaVersion": 1,
                    "packageId": "manual_arduino_sketch",
                    "revision": "1",
                    "libraryFolder": library,
                    "sourcePath": "manual",
                    "mode": "manual",
                    "importedAt": _iso_timestamp(),
                    "files": [],
                    "warnings": [],
                },
            )
        return path

    def _prepare_arduino_sketch(
        self,
        source: Path,
    ) -> tuple[str, str]:
        candidates = sorted(
            (
                item
                for item in source.iterdir()
                if item.is_file() and item.suffix.casefold() == ".ino"
            ),
            key=lambda item: item.name.casefold(),
        )
        if len(candidates) != 1:
            names = ", ".join(item.name for item in candidates) or "none"
            raise ImplementationError(
                "The selected source folder must contain exactly one .ino file "
                f"at its root; found {len(candidates)} ({names})."
            )

        selected = candidates[0]
        try:
            sketch = selected.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            raise ImplementationError(
                f"Source Arduino sketch cannot be read: {selected}: {error}"
            ) from error
        return self._validate_sketch(sketch), f"source:{selected.name}"

    def _prepare_ui_elements(
        self,
        source: Path,
    ) -> tuple[tuple[UiElementVariable, ...], str]:
        path = source / UI_ELEMENTS_FILE_NAME
        if not path.is_file():
            return (), "missing"
        return self._read_ui_elements(path), f"source:{path.name}"

    @staticmethod
    def _read_ui_elements(path: Path) -> tuple[UiElementVariable, ...]:
        try:
            if path.stat().st_size > MAX_UI_ELEMENTS_BYTES:
                raise ImplementationError(
                    f"UI element registry is larger than 1 MB: {path}"
                )
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except ImplementationError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ImplementationError(
                f"UI element registry cannot be read: {path}: {error}"
            ) from error

        if not isinstance(document, dict):
            raise ImplementationError(
                "ui-elements.json must contain one JSON object."
            )
        if document.get("schemaVersion") != 1:
            raise ImplementationError(
                "ui-elements.json schemaVersion must be 1."
            )
        project = document.get("project")
        if not isinstance(project, str) or not project.strip():
            raise ImplementationError(
                "ui-elements.json project must be non-empty text."
            )
        bridge_namespace = document.get("bridgeNamespace", "")
        if not isinstance(bridge_namespace, str):
            raise ImplementationError(
                "ui-elements.json bridgeNamespace must be text."
            )
        bridge_namespace = bridge_namespace.strip()
        namespace_pattern = (
            r"[A-Za-z_][A-Za-z0-9_]*"
            r"(?:::[A-Za-z_][A-Za-z0-9_]*)*"
        )
        if (
            bridge_namespace
            and not re.fullmatch(namespace_pattern, bridge_namespace)
        ):
            raise ImplementationError(
                "ui-elements.json bridgeNamespace must be a valid C++ namespace."
            )
        raw_elements = document.get("elements")
        if not isinstance(raw_elements, list):
            raise ImplementationError(
                "ui-elements.json elements must be a list."
            )
        if len(raw_elements) > MAX_UI_ELEMENTS:
            raise ImplementationError(
                f"ui-elements.json contains more than {MAX_UI_ELEMENTS} elements."
            )

        def required_text(
            entry: dict[str, Any],
            field: str,
            index: int,
            maximum: int = 500,
        ) -> str:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ImplementationError(
                    f"UI element {index} field {field} must be non-empty text."
                )
            value = value.strip()
            if len(value) > maximum:
                raise ImplementationError(
                    f"UI element {index} field {field} is too long."
                )
            return value

        def optional_text(
            entry: dict[str, Any],
            field: str,
            index: int,
            maximum: int = 1_000,
        ) -> str:
            value = entry.get(field, "")
            if not isinstance(value, str):
                raise ImplementationError(
                    f"UI element {index} field {field} must be text."
                )
            value = value.strip()
            if len(value) > maximum:
                raise ImplementationError(
                    f"UI element {index} field {field} is too long."
                )
            return value

        def number_or_none(
            value: Any,
            field: str,
            index: int,
        ) -> int | float | None:
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ImplementationError(
                    f"UI element {index} range {field} must be a number."
                )
            return value

        result: list[UiElementVariable] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_elements, start=1):
            if not isinstance(raw, dict):
                raise ImplementationError(
                    f"UI element {index} must be a JSON object."
                )
            element_id = required_text(raw, "id", index, 128)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", element_id):
                raise ImplementationError(
                    f"UI element {index} id is not a safe stable identifier."
                )
            folded_id = element_id.casefold()
            if folded_id in seen_ids:
                raise ImplementationError(
                    f"ui-elements.json contains duplicate id: {element_id}"
                )
            seen_ids.add(folded_id)

            element_type = required_text(raw, "type", index, 64)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", element_type):
                raise ImplementationError(
                    f"UI element {index} type is not a safe identifier."
                )
            lvgl_object = required_text(raw, "lvglObject", index, 128)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", lvgl_object):
                raise ImplementationError(
                    f"UI element {index} lvglObject must be a C/C++ identifier."
                )
            direction = required_text(raw, "direction", index, 64)
            if direction not in UI_ELEMENT_DIRECTIONS:
                raise ImplementationError(
                    f"UI element {index} direction is unsupported: {direction}"
                )
            value_type = required_text(raw, "valueType", index, 32)
            if value_type not in UI_ELEMENT_VALUE_TYPES:
                raise ImplementationError(
                    f"UI element {index} valueType is unsupported: {value_type}"
                )

            raw_range = raw.get("range")
            if raw_range is not None and not isinstance(raw_range, dict):
                raise ImplementationError(
                    f"UI element {index} range must be an object."
                )
            range_document = raw_range or {}
            range_min = number_or_none(range_document.get("min"), "min", index)
            range_max = number_or_none(range_document.get("max"), "max", index)
            range_step = number_or_none(
                range_document.get("step"),
                "step",
                index,
            )
            if (
                range_min is not None
                and range_max is not None
                and range_min > range_max
            ):
                raise ImplementationError(
                    f"UI element {index} range min cannot exceed max."
                )
            if range_step is not None and range_step <= 0:
                raise ImplementationError(
                    f"UI element {index} range step must be greater than zero."
                )
            unit = range_document.get("unit", "")
            if not isinstance(unit, str) or len(unit.strip()) > 64:
                raise ImplementationError(
                    f"UI element {index} range unit must be short text."
                )

            raw_events = raw.get("events", [])
            if not isinstance(raw_events, list) or len(raw_events) > 32:
                raise ImplementationError(
                    f"UI element {index} events must be a list of at most 32 values."
                )
            events: list[str] = []
            for event in raw_events:
                if (
                    not isinstance(event, str)
                    or not event.strip()
                    or len(event.strip()) > 128
                ):
                    raise ImplementationError(
                        f"UI element {index} has an invalid event."
                    )
                events.append(event.strip())

            result.append(
                UiElementVariable(
                    id=element_id,
                    name=required_text(raw, "name", index),
                    screen=required_text(raw, "screen", index, 128),
                    type=element_type,
                    lvgl_object=lvgl_object,
                    direction=direction,
                    value_type=value_type,
                    description=required_text(raw, "description", index, 2_000),
                    range_min=range_min,
                    range_max=range_max,
                    range_step=range_step,
                    unit=unit.strip(),
                    events=tuple(events),
                    read_api=optional_text(raw, "readApi", index),
                    write_api=optional_text(raw, "writeApi", index),
                    bridge_namespace=bridge_namespace,
                    visuino_input_code=optional_text(
                        raw,
                        "visuinoInputCode",
                        index,
                        2_000,
                    ),
                    visuino_loop_code=optional_text(
                        raw,
                        "visuinoLoopCode",
                        index,
                        2_000,
                    ),
                )
            )
        return tuple(result)

    @staticmethod
    def _default_arduino_sketch(library: str) -> str:
        return (
            f"#include <{library}.h>\n\n"
            "void setup() {\n"
            "  // Add setup-local device initialization here.\n"
            "}\n\n"
            "void loop() {\n"
            "  // Add the setup-local device update call here.\n"
            "}\n"
        )

    @classmethod
    def _compose_legacy_hooks(
        cls,
        hooks: CustomCodeHooks,
        library: str,
    ) -> str:
        values = hooks.as_dict()

        def indented(value: str) -> str:
            lines = value.strip().splitlines()
            return "\n".join(f"  {line}" if line else "" for line in lines)

        includes = values["includes"].strip() or f"#include <{library}.h>"
        globals_code = values["globals"].strip()
        setup_code = indented(values["setup"])
        loop_code = indented(values["loop"])
        parts = [includes]
        if globals_code:
            parts.extend(("", globals_code))
        parts.extend(
            (
                "",
                "void setup() {",
                setup_code,
                "}",
                "",
                "void loop() {",
                loop_code,
                "}",
                "",
            )
        )
        return cls._validate_sketch("\n".join(parts))

    @staticmethod
    def _validate_sketch(sketch: str) -> str:
        if not isinstance(sketch, str):
            raise ImplementationError("Visuino Arduino sketch must be text.")
        size = len(sketch.encode("utf-8"))
        if size > MAX_SKETCH_BYTES:
            raise ImplementationError("Visuino Arduino sketch is larger than 1 MB.")
        if not sketch.strip():
            raise ImplementationError("Visuino Arduino sketch is empty.")
        if not re.search(r"\bvoid\s+setup\s*\(", sketch):
            raise ImplementationError(
                "Visuino Arduino sketch must contain void setup()."
            )
        if not re.search(r"\bvoid\s+loop\s*\(", sketch):
            raise ImplementationError(
                "Visuino Arduino sketch must contain void loop()."
            )
        return sketch if sketch.endswith("\n") else f"{sketch}\n"

    @staticmethod
    def _detect_mode(source: Path) -> str:
        if ImplementationService._find_libraries_root(source) is not None:
            return "libraries_directory"
        if (source / "library.properties").is_file():
            return "arduino_library"
        return "loose_source"

    @staticmethod
    def _find_libraries_root(source: Path) -> Path | None:
        for candidate in (
            source / "libraries",
            source / "Arduino" / "libraries",
        ):
            if candidate.is_dir():
                return candidate
        return None

    def _map_library_root(
        self,
        libraries_root: Path,
        setup: Path,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
        warnings: list[str],
    ) -> None:
        for child in sorted(libraries_root.iterdir(), key=lambda item: item.name.casefold()):
            if child.name.startswith("."):
                continue
            target = setup / child.name
            if (
                child.name.casefold() in PROTECTED_BASELINE
                and target.exists()
            ):
                warnings.append(
                    f"Protected existing baseline library was not replaced: {child.name}"
                )
                continue
            if child.is_dir():
                self._map_tree(child, target, mapped)
            elif child.is_file():
                self._map_file(child, target, mapped)

    def _map_dependency_directories(
        self,
        source: Path,
        setup: Path,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
        warnings: list[str],
    ) -> None:
        dependency_roots: list[Path] = []
        if (source / "lib").is_dir():
            dependency_roots.append(source / "lib")

        libdeps = source / ".pio" / "libdeps"
        if libdeps.is_dir():
            environments = sorted(
                (item for item in libdeps.iterdir() if item.is_dir()),
                key=lambda item: item.name.casefold(),
            )
            if environments:
                dependency_roots.append(environments[0])
                warnings.append(
                    f"Imported cached PlatformIO dependencies from environment: "
                    f"{environments[0].name}"
                )

        for root in dependency_roots:
            for child in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                target = setup / child.name
                if child.name.casefold() in PROTECTED_BASELINE and target.exists():
                    warnings.append(
                        f"Protected existing baseline library was not replaced: {child.name}"
                    )
                    continue
                self._map_tree(child, target, mapped)

    def _map_loose_project(
        self,
        source: Path,
        setup: Path,
        library: str,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
    ) -> None:
        library_root = setup / library
        source_root = library_root / "src"
        original_root = library_root / "extras" / "original"

        for folder_name in ("src", "include", "ui"):
            folder = source / folder_name
            if not folder.is_dir():
                continue
            for file in self._iter_files(folder):
                relative = file.relative_to(folder)
                if file.name.casefold() == "lv_conf.h":
                    self._map_file(file, setup / "lv_conf.h", mapped)
                elif (
                    folder_name == "src"
                    and relative.parent == Path(".")
                    and file.name.casefold() in ENTRYPOINT_NAMES
                ) or file.suffix.casefold() == ".ino":
                    self._map_file(
                        file,
                        original_root / folder_name / relative,
                        mapped,
                    )
                else:
                    destination = (
                        source_root / "ui" / relative
                        if folder_name == "ui"
                        else source_root / relative
                    )
                    self._map_file(file, destination, mapped)

        for file in sorted(
            (item for item in source.iterdir() if item.is_file()),
            key=lambda item: item.name.casefold(),
        ):
            if file.name.casefold() == "lv_conf.h":
                self._map_file(file, setup / "lv_conf.h", mapped)
            elif file.suffix.casefold() == ".ino" or file.name.casefold() in ENTRYPOINT_NAMES:
                self._map_file(file, original_root / file.name, mapped)
            elif file.name.casefold() == "readme.md":
                self._map_file(file, library_root / "extras" / "README.md", mapped)
            elif file.suffix.casefold() in SOURCE_SUFFIXES:
                self._map_file(file, source_root / file.name, mapped)
            elif file.name.casefold() in {"platformio.ini", "partitions.csv"}:
                self._map_file(file, original_root / file.name, mapped)

    def _add_generated_library_files(
        self,
        setup: Path,
        library: str,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
    ) -> None:
        properties = (
            f"name={library}\n"
            "version=1.0.0\n"
            "author=Local setup manager\n"
            "maintainer=Local setup manager\n"
            "sentence=Imported standalone Arduino and LVGL implementation.\n"
            "paragraph=Generated as a setup-local library for a Visuino Arduino import sketch.\n"
            "category=Display\n"
            "architectures=esp32\n"
            f"includes={library}.h\n"
        ).encode("utf-8")
        header = (
            "#pragma once\n\n"
            "// Setup-local implementation bridge. The complete Visuino Arduino\n"
            "// import sketch is stored under this library's extras directory.\n"
        ).encode("utf-8")
        self._map_content(
            properties,
            setup / library / "library.properties",
            mapped,
        )
        self._map_content(
            header,
            setup / library / "src" / f"{library}.h",
            mapped,
        )

    def _map_tree(
        self,
        source: Path,
        destination: Path,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
    ) -> None:
        for file in self._iter_files(source):
            self._map_file(file, destination / file.relative_to(source), mapped)

    def _iter_files(self, root: Path) -> Iterable[Path]:
        for current, directory_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in directory_names:
                directory = current_path / name
                if directory.is_symlink():
                    raise ImplementationError(
                        f"Symbolic links are not allowed in imports: {directory}"
                    )
            directory_names[:] = [
                name
                for name in directory_names
                if name.casefold() not in EXCLUDED_DIRECTORY_NAMES
                and not (
                    current_path.name.casefold() == ".pio"
                    and name.casefold() == "build"
                )
            ]
            for name in sorted(file_names, key=str.casefold):
                path = current_path / name
                if path.is_symlink():
                    raise ImplementationError(
                        f"Symbolic links are not allowed in imports: {path}"
                    )
                if path.suffix.casefold() in EXCLUDED_FILE_SUFFIXES:
                    continue
                yield path

    @staticmethod
    def _map_file(
        source: Path,
        destination: Path,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
    ) -> None:
        existing = mapped.get(destination)
        if existing is not None:
            existing_source, _ = existing
            if existing_source is not None and filecmp.cmp(
                existing_source,
                source,
                shallow=False,
            ):
                return
            raise ImplementationError(
                f"Multiple source files map to the same destination: {destination}"
            )
        mapped[destination] = (source, None)

    @staticmethod
    def _map_content(
        content: bytes,
        destination: Path,
        mapped: dict[Path, tuple[Path | None, bytes | None]],
    ) -> None:
        existing = mapped.get(destination)
        if existing is not None:
            existing_source, existing_content = existing
            if existing_content == content:
                return
            if (
                existing_source is not None
                and existing_source.read_bytes() == content
            ):
                return
            raise ImplementationError(
                f"Generated content conflicts with imported file: {destination}"
            )
        mapped[destination] = (None, content)

    @staticmethod
    def _copy_path(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    @staticmethod
    def _verify_copy_inventory(source: Path, destination: Path) -> None:
        if source.is_file():
            if (
                not destination.is_file()
                or source.stat().st_size != destination.stat().st_size
            ):
                raise ImplementationError(f"Backup verification failed: {source}")
            return
        source_files = {
            str(path.relative_to(source)): path.stat().st_size
            for path in source.rglob("*")
            if path.is_file()
        }
        destination_files = {
            str(path.relative_to(destination)): path.stat().st_size
            for path in destination.rglob("*")
            if path.is_file()
        }
        if source_files != destination_files:
            raise ImplementationError(f"Backup verification failed: {source}")

    @staticmethod
    def _remove_path(path: Path) -> None:
        resolved = path.resolve(strict=False)
        if resolved.anchor and resolved == Path(resolved.anchor):
            raise ImplementationError("Refusing to remove a filesystem root.")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            json.loads(temporary.read_text(encoding="utf-8"))
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _write_text_atomic(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.read_text(encoding="utf-8")
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _read_hooks_if_present(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ImplementationError(f"Custom Code hooks cannot be read: {error}") from error
        if not isinstance(document, dict) or document.get("schemaVersion") != 1:
            raise ImplementationError("Custom Code hook document schema is unsupported.")
        return document

    def _ensure_metadata_library(self, path: Path, library: str) -> None:
        if path.exists() and not path.is_dir():
            raise ImplementationError(f"Implementation library path is not a folder: {path}")
        path.mkdir(parents=True, exist_ok=True)
        properties = path / "library.properties"
        header = path / "src" / f"{library}.h"
        if not properties.exists():
            properties.write_text(
                f"name={library}\n"
                "version=1.0.0\n"
                "sentence=Setup-local Visuino Arduino import bridge.\n"
                "paragraph=Stores a complete .ino sketch and imported helper sources.\n"
                "category=Display\n"
                "architectures=esp32\n"
                f"includes={library}.h\n",
                encoding="utf-8",
                newline="\n",
            )
        if not header.exists():
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("#pragma once\n", encoding="utf-8", newline="\n")
