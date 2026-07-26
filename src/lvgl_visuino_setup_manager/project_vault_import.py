from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .project_vault import (
    CLIENTS_DIRECTORY_NAME,
    LIBRARY_NAME_PATTERN,
    PROJECT_MANIFEST_NAME,
    PROJECT_MANIFEST_SCHEMA_VERSION,
    STABLE_ID_PATTERN,
    ProjectRevision,
    ProjectVaultError,
    ProjectVaultService,
)


PROJECT_META_NAME = "project-meta.json"
UI_ELEMENTS_NAME = "ui-elements.json"
LIBRARIES_DIRECTORY_NAME = "libraries"
PROJECT_SOURCE_DIRECTORIES = ("include", "src", "ui", "assets")
SOURCE_FILE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".inc",
    ".s",
}
HEADER_FILE_SUFFIXES = {".h", ".hh", ".hpp", ".inc"}
REJECTED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".pio",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
}
REJECTED_FILE_SUFFIXES = {
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
INO_INCLUDE_PATTERN = re.compile(
    r'^\s*#\s*include\s*[<"]([^">]+)[">]',
    flags=re.MULTILINE,
)


@dataclass(frozen=True)
class ProjectVaultImportRequest:
    source_path: Path
    client_id: str
    client_name: str
    project_id: str
    project_name: str
    revision_id: str
    library_name: str


@dataclass(frozen=True)
class ProjectVaultImportFile:
    relative_path: Path
    source_path: Path | None
    content: bytes | None
    size: int
    origin: str


@dataclass(frozen=True)
class ProjectVaultImportPlan:
    request: ProjectVaultImportRequest
    source_path: Path
    revision_path: Path
    library_path: Path
    root_ino_source: Path
    root_ino_name: str
    lvgl_version: str
    dependency_names: tuple[str, ...]
    files: tuple[ProjectVaultImportFile, ...]
    planned_at: str

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)


@dataclass(frozen=True)
class ProjectVaultImportResult:
    revision: ProjectRevision
    source_path: Path
    file_count: int
    total_bytes: int
    imported_at: str


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectVaultError(f"{label} must be non-empty text.")
    return value.strip()


def _require_stable_id(value: str, label: str) -> str:
    stable_id = _require_text(value, label)
    if not STABLE_ID_PATTERN.fullmatch(stable_id):
        raise ProjectVaultError(
            f"{label} must use only letters, numbers, underscores, and dashes "
            "and must be at most 63 characters."
        )
    return stable_id


def _require_library_name(value: str) -> str:
    library_name = _require_text(value, "Library name")
    if not LIBRARY_NAME_PATTERN.fullmatch(library_name):
        raise ProjectVaultError(
            "Library name must start with a letter or number, use only letters, "
            "numbers, underscores, dots, and dashes, and be at most 63 characters."
        )
    return library_name


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except AttributeError:
        attributes = 0
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _is_link_like(path: Path) -> bool:
    return (
        path.is_symlink()
        or (hasattr(os.path, "isjunction") and os.path.isjunction(path))
        or _is_reparse_point(path)
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectVaultError(f"Cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProjectVaultError(f"{label} must contain one JSON object: {path}")
    return value


def _read_library_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise ProjectVaultError(
            f"Cannot read Arduino library properties {path}: {error}"
        ) from error
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().casefold()] = value.strip()
    return values


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class ProjectVaultImportService:
    """Stage a standalone package as one immutable self-contained library."""

    def __init__(self, vault_service: ProjectVaultService) -> None:
        self.vault_service = vault_service

    def plan(self, request: ProjectVaultImportRequest) -> ProjectVaultImportPlan:
        source = Path(request.source_path).expanduser().resolve(strict=False)
        if not source.is_dir():
            raise ProjectVaultError(
                f"The standalone import folder does not exist: {source}"
            )
        if _is_link_like(source):
            raise ProjectVaultError(
                "The standalone import root cannot be a link or reparse point."
            )
        vault_root = self.vault_service.root
        if source == vault_root or _is_relative_to(source, vault_root):
            raise ProjectVaultError(
                "The standalone import source cannot be inside FAH Project Vault."
            )

        normalized_request = ProjectVaultImportRequest(
            source_path=source,
            client_id=_require_stable_id(request.client_id, "Client ID"),
            client_name=_require_text(request.client_name, "Client name"),
            project_id=_require_stable_id(request.project_id, "Project ID"),
            project_name=_require_text(request.project_name, "Project name"),
            revision_id=_require_stable_id(request.revision_id, "Revision ID"),
            library_name=_require_library_name(request.library_name),
        )
        self._validate_source_tree(source)

        revision_path = (
            self.vault_service.clients_root
            / normalized_request.client_id
            / "Projects"
            / normalized_request.project_id
            / "Revisions"
            / normalized_request.revision_id
        )
        if os.path.lexists(revision_path):
            raise ProjectVaultError(
                "The immutable project revision already exists and will not be "
                f"overwritten: {revision_path}"
            )
        library_path = (
            revision_path
            / LIBRARIES_DIRECTORY_NAME
            / normalized_request.library_name
        )

        root_inos = tuple(
            sorted(
                (
                    path
                    for path in source.iterdir()
                    if path.is_file() and path.suffix.casefold() == ".ino"
                ),
                key=lambda path: path.name.casefold(),
            )
        )
        if len(root_inos) != 1:
            raise ProjectVaultError(
                "The standalone import folder must contain exactly one root INO "
                f"file; found {len(root_inos)}."
            )
        root_ino = root_inos[0]
        project_meta = source / PROJECT_META_NAME
        ui_elements = source / UI_ELEMENTS_NAME
        _read_json_object(project_meta, "project metadata")
        _read_json_object(ui_elements, "UI element metadata")
        readme = source / "README.md"
        if not readme.is_file():
            raise ProjectVaultError("The standalone import is missing README.md.")
        try:
            readme.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ProjectVaultError(f"Cannot read README.md as UTF-8: {error}") from error

        libraries_root = source / LIBRARIES_DIRECTORY_NAME
        if not libraries_root.is_dir():
            raise ProjectVaultError(
                "The standalone import is missing its root libraries folder."
            )
        dependencies = tuple(
            sorted(
                (path for path in libraries_root.iterdir() if path.is_dir()),
                key=lambda path: path.name.casefold(),
            )
        )
        if not dependencies:
            raise ProjectVaultError(
                "The standalone import libraries folder contains no Arduino libraries."
            )

        planned: dict[str, ProjectVaultImportFile] = {}
        project_source_count = 0

        def add_source(
            source_path: Path,
            relative_path: Path,
            origin: str,
        ) -> None:
            self._add_planned_file(
                planned,
                ProjectVaultImportFile(
                    relative_path=relative_path,
                    source_path=source_path,
                    content=None,
                    size=source_path.stat().st_size,
                    origin=origin,
                ),
            )

        def add_content(relative_path: Path, content: bytes, origin: str) -> None:
            self._add_planned_file(
                planned,
                ProjectVaultImportFile(
                    relative_path=relative_path,
                    source_path=None,
                    content=content,
                    size=len(content),
                    origin=origin,
                ),
            )

        library_relative = (
            Path(LIBRARIES_DIRECTORY_NAME) / normalized_request.library_name
        )
        library_src_relative = library_relative / "src"
        root_ino_name = f"{normalized_request.revision_id}.ino"
        add_source(root_ino, Path(root_ino_name), "root INO")
        add_source(project_meta, Path(PROJECT_META_NAME), "project metadata")
        add_source(ui_elements, Path(UI_ELEMENTS_NAME), "UI element metadata")
        add_source(readme, Path("README.md"), "project README")
        compile_report = source / "compile-report.json"
        if compile_report.is_file():
            _read_json_object(compile_report, "compile report")
            add_source(
                compile_report,
                Path("compile-report.json"),
                "compile report",
            )

        for directory_name in PROJECT_SOURCE_DIRECTORIES:
            directory = source / directory_name
            if not directory.is_dir():
                continue
            target_prefix = (
                Path("ui")
                if directory_name == "ui"
                else Path("assets")
                if directory_name == "assets"
                else Path()
            )
            for item in self._regular_files(directory):
                project_source_count += 1
                add_source(
                    item,
                    library_src_relative
                    / target_prefix
                    / item.relative_to(directory),
                    f"project {directory_name}",
                )
        for item in sorted(source.iterdir(), key=lambda path: path.name.casefold()):
            if (
                item.is_file()
                and item != root_ino
                and item.name not in {PROJECT_META_NAME, UI_ELEMENTS_NAME, "README.md"}
                and item.suffix.casefold() in SOURCE_FILE_SUFFIXES
            ):
                project_source_count += 1
                add_source(
                    item,
                    library_src_relative / item.name,
                    "project root source",
                )

        lvgl_dependency: Path | None = None
        dependency_names: list[str] = []
        for dependency in dependencies:
            properties_path = dependency / "library.properties"
            dependency_src = dependency / "src"
            if not properties_path.is_file() or not dependency_src.is_dir():
                raise ProjectVaultError(
                    "Every dependency below libraries must contain "
                    f"library.properties and src: {dependency}"
                )
            properties = _read_library_properties(properties_path)
            dependency_name = properties.get("name") or dependency.name
            dependency_names.append(dependency_name)
            if dependency.name.casefold() == "lvgl" or dependency_name.casefold() == "lvgl":
                if lvgl_dependency is not None:
                    raise ProjectVaultError(
                        "The standalone import contains more than one LVGL library."
                    )
                lvgl_dependency = dependency
                continue
            for item in self._regular_files(dependency_src):
                add_source(
                    item,
                    library_src_relative / item.relative_to(dependency_src),
                    f"dependency {dependency_name}",
                )
            for item in sorted(
                (path for path in dependency.iterdir() if path.is_file()),
                key=lambda path: path.name.casefold(),
            ):
                if item.suffix.casefold() in HEADER_FILE_SUFFIXES:
                    add_source(
                        item,
                        library_src_relative / item.name,
                        f"dependency config {dependency_name}",
                    )

        if lvgl_dependency is None:
            raise ProjectVaultError(
                "The standalone import must contain one vendored LVGL library."
            )
        lvgl_properties = _read_library_properties(
            lvgl_dependency / "library.properties"
        )
        lvgl_version = _require_text(
            lvgl_properties.get("version", ""),
            "LVGL library version",
        )
        vendored_lvgl_relative = library_src_relative / "vendor" / "lvgl"
        for item in self._regular_files(lvgl_dependency / "src"):
            add_source(
                item,
                vendored_lvgl_relative
                / "src"
                / item.relative_to(lvgl_dependency / "src"),
                "vendored LVGL source",
            )
        for name in ("lvgl.h", "library.properties", "LICENCE.txt", "LICENSE.txt"):
            item = lvgl_dependency / name
            if item.is_file():
                add_source(
                    item,
                    vendored_lvgl_relative / name,
                    "vendored LVGL metadata",
                )
        if not (lvgl_dependency / "lvgl.h").is_file():
            raise ProjectVaultError("The LVGL dependency is missing its public lvgl.h.")

        ino_text = root_ino.read_text(encoding="utf-8-sig")
        include_match = INO_INCLUDE_PATTERN.search(ino_text)
        public_lines = [
            "#pragma once",
            "",
            "// Unique entry point for this immutable FAH Project Vault revision.",
        ]
        if include_match:
            public_lines.append(f'#include "{include_match.group(1)}"')
        public_lines.append("")
        public_header = "\n".join(public_lines).encode("utf-8")
        add_content(
            library_src_relative / f"{normalized_request.library_name}.h",
            public_header,
            "generated unique public header",
        )
        add_content(
            library_src_relative / "lvgl.h",
            b'#pragma once\n#include "vendor/lvgl/lvgl.h"\n',
            "generated project-local LVGL forwarding header",
        )
        library_properties = "\n".join(
            (
                f"name={normalized_request.library_name}",
                "version=1.0.0",
                "author=Finn Andre Hotvedt",
                "maintainer=Finn Andre Hotvedt",
                "sentence=Immutable FAH Visuino LVGL project revision.",
                (
                    "paragraph=Self-contained project library with project-local "
                    "display, touch, UI, bridge, dependencies, and LVGL sources."
                ),
                "category=Display",
                "url=https://finnandre.no",
                "architectures=esp32",
                f"includes={normalized_request.library_name}.h",
                "",
            )
        ).encode("utf-8")
        add_content(
            library_relative / "library.properties",
            library_properties,
            "generated Arduino library properties",
        )

        imported_at = _now_iso()
        manifest = {
            "schemaVersion": PROJECT_MANIFEST_SCHEMA_VERSION,
            "revision": {
                "id": normalized_request.revision_id,
                "immutable": True,
            },
            "client": {
                "id": normalized_request.client_id,
                "name": normalized_request.client_name,
            },
            "project": {
                "id": normalized_request.project_id,
                "name": normalized_request.project_name,
            },
            "library": {
                "name": normalized_request.library_name,
                "relativePath": library_relative.as_posix(),
                "selfContained": True,
                "lvgl": {
                    "version": lvgl_version,
                    "storage": "vendored",
                },
            },
            "handoff": {
                "rootIno": root_ino_name,
                "projectMeta": PROJECT_META_NAME,
                "uiElements": UI_ELEMENTS_NAME,
            },
            "import": {
                "sourceFolder": source.name,
                "sourceRootIno": root_ino.name,
                "importedAt": imported_at,
                "dependencies": dependency_names,
            },
        }
        add_content(
            Path(PROJECT_MANIFEST_NAME),
            _json_bytes(manifest),
            "generated immutable project manifest",
        )

        if project_source_count == 0:
            raise ProjectVaultError(
                "No project source files were mapped into the self-contained library."
            )

        return ProjectVaultImportPlan(
            request=normalized_request,
            source_path=source,
            revision_path=revision_path,
            library_path=library_path,
            root_ino_source=root_ino,
            root_ino_name=root_ino_name,
            lvgl_version=lvgl_version,
            dependency_names=tuple(dependency_names),
            files=tuple(
                sorted(
                    planned.values(),
                    key=lambda item: item.relative_path.as_posix().casefold(),
                )
            ),
            planned_at=imported_at,
        )

    def execute(self, plan: ProjectVaultImportPlan) -> ProjectVaultImportResult:
        fresh_plan = self.plan(plan.request)
        if self._plan_signature(fresh_plan) != self._plan_signature(plan):
            raise ProjectVaultError(
                "The standalone source changed after analysis. Analyze it again "
                "before importing."
            )
        final_revision = fresh_plan.revision_path
        if os.path.lexists(final_revision):
            raise ProjectVaultError(
                "The immutable project revision already exists and will not be "
                f"overwritten: {final_revision}"
            )

        self.vault_service.initialize()
        operation = uuid.uuid4().hex
        staging_container = self.vault_service.root / f".import-staging-{operation}"
        staging_vault = staging_container / self.vault_service.root.name
        staging_service = ProjectVaultService(staging_vault)
        staging_revision = (
            staging_service.clients_root
            / fresh_plan.request.client_id
            / "Projects"
            / fresh_plan.request.project_id
            / "Revisions"
            / fresh_plan.request.revision_id
        )
        placed = False
        try:
            for item in fresh_plan.files:
                destination = (staging_revision / item.relative_path).resolve(
                    strict=False
                )
                if not _is_relative_to(destination, staging_revision.resolve(strict=False)):
                    raise ProjectVaultError(
                        f"An import target escapes the staged revision: {item.relative_path}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if item.source_path is not None:
                    if (
                        not item.source_path.is_file()
                        or _is_link_like(item.source_path)
                        or item.source_path.stat().st_size != item.size
                    ):
                        raise ProjectVaultError(
                            "A planned source file changed or became unsafe: "
                            f"{item.source_path}"
                        )
                    shutil.copy2(item.source_path, destination)
                else:
                    if item.content is None:
                        raise ProjectVaultError(
                            f"A generated import file has no content: {item.relative_path}"
                        )
                    destination.write_bytes(item.content)
                if not destination.is_file() or destination.stat().st_size != item.size:
                    raise ProjectVaultError(
                        f"Staged file verification failed: {item.relative_path}"
                    )

            staged_revision = staging_service.load_revision(
                staging_revision / PROJECT_MANIFEST_NAME
            )
            if staged_revision.library_name != fresh_plan.request.library_name:
                raise ProjectVaultError("Staged library identity verification failed.")
            final_revision.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(final_revision):
                raise ProjectVaultError(
                    "The immutable destination appeared during staging and will "
                    f"not be overwritten: {final_revision}"
                )
            os.replace(staging_revision, final_revision)
            placed = True
            revision = self.vault_service.load_revision(
                final_revision / PROJECT_MANIFEST_NAME
            )
            return ProjectVaultImportResult(
                revision=revision,
                source_path=fresh_plan.source_path,
                file_count=fresh_plan.file_count,
                total_bytes=fresh_plan.total_bytes,
                imported_at=fresh_plan.planned_at,
            )
        except Exception:
            if placed and final_revision.exists():
                rollback_parent = staging_revision.parent
                rollback_parent.mkdir(parents=True, exist_ok=True)
                os.replace(final_revision, staging_revision)
            raise
        finally:
            if staging_container.exists():
                shutil.rmtree(staging_container)
            self._remove_empty_destination_parents(final_revision.parent)

    @staticmethod
    def _add_planned_file(
        planned: dict[str, ProjectVaultImportFile],
        item: ProjectVaultImportFile,
    ) -> None:
        if item.relative_path.is_absolute() or ".." in item.relative_path.parts:
            raise ProjectVaultError(
                f"An import destination is unsafe: {item.relative_path}"
            )
        key = item.relative_path.as_posix().casefold()
        existing = planned.get(key)
        if existing is not None:
            raise ProjectVaultError(
                "Two import files target the same case-insensitive path:\n"
                f"- {existing.origin}: {existing.relative_path}\n"
                f"- {item.origin}: {item.relative_path}"
            )
        planned[key] = item

    @staticmethod
    def _regular_files(root: Path) -> tuple[Path, ...]:
        return tuple(
            sorted(
                (path for path in root.rglob("*") if path.is_file()),
                key=lambda path: path.relative_to(root).as_posix().casefold(),
            )
        )

    @staticmethod
    def _validate_source_tree(source: Path) -> None:
        for current, directories, files in os.walk(source, followlinks=False):
            current_path = Path(current)
            directories.sort(key=str.casefold)
            files.sort(key=str.casefold)
            for name in tuple(directories):
                path = current_path / name
                if name.casefold() in REJECTED_DIRECTORY_NAMES:
                    raise ProjectVaultError(
                        f"The standalone import contains a generated folder: {path}"
                    )
                if _is_link_like(path):
                    raise ProjectVaultError(
                        f"The standalone import contains a link or reparse point: {path}"
                    )
            for name in files:
                path = current_path / name
                if _is_link_like(path):
                    raise ProjectVaultError(
                        f"The standalone import contains a link or reparse point: {path}"
                    )
                if path.suffix.casefold() in REJECTED_FILE_SUFFIXES:
                    raise ProjectVaultError(
                        f"The standalone import contains a generated binary: {path}"
                    )

    @staticmethod
    def _plan_signature(
        plan: ProjectVaultImportPlan,
    ) -> tuple[tuple[str, int, str], ...]:
        return tuple(
            (
                item.relative_path.as_posix().casefold(),
                item.size,
                str(item.source_path) if item.source_path else item.origin,
            )
            for item in plan.files
        )

    def _remove_empty_destination_parents(self, start: Path) -> None:
        current = start
        boundary = self.vault_service.clients_root
        while current != boundary and _is_relative_to(current, boundary):
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
