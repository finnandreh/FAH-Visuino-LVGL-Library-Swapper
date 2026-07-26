from __future__ import annotations

import copy
import json
import os
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol


PROJECT_MANIFEST_NAME = "fah-project.json"
PROJECT_MANIFEST_SCHEMA_VERSION = 1
LINK_REGISTRY_SCHEMA_VERSION = 1
VAULT_DIRECTORY_NAME = "FAH LVGL"
CLIENTS_DIRECTORY_NAME = "Clients"
LIBRARY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
STABLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")


class ProjectVaultError(RuntimeError):
    """Raised when a project-vault or managed-junction operation is unsafe."""


class JunctionBackend(Protocol):
    def create(self, target: Path, link: Path) -> None:
        ...

    def is_junction(self, path: Path) -> bool:
        ...

    def target(self, path: Path) -> Path:
        ...

    def remove(self, path: Path) -> None:
        ...


class WindowsJunctionBackend:
    """Create and remove NTFS directory junction entries without a shell."""

    def create(self, target: Path, link: Path) -> None:
        if os.name != "nt":
            raise ProjectVaultError("Directory junctions require Windows.")
        if os.path.lexists(link):
            raise ProjectVaultError(f"The junction destination already exists: {link}")
        if not target.is_dir():
            raise ProjectVaultError(f"The junction target is not a directory: {target}")
        try:
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        except OSError as error:
            raise ProjectVaultError(
                f"Cannot create the directory junction {link}: {error}"
            ) from error

    @staticmethod
    def is_junction(path: Path) -> bool:
        return os.path.isjunction(path)

    def target(self, path: Path) -> Path:
        if not self.is_junction(path):
            raise ProjectVaultError(f"The path is not a directory junction: {path}")
        try:
            return path.resolve(strict=True)
        except OSError as error:
            raise ProjectVaultError(
                f"Cannot resolve the directory junction target for {path}: {error}"
            ) from error

    def remove(self, path: Path) -> None:
        if not self.is_junction(path):
            raise ProjectVaultError(f"Refusing to remove a non-junction path: {path}")
        try:
            os.rmdir(path)
        except OSError as error:
            raise ProjectVaultError(
                f"Cannot remove the directory junction {path}: {error}"
            ) from error


@dataclass(frozen=True)
class ProjectRevision:
    manifest_path: Path
    revision_path: Path
    client_id: str
    client_name: str
    project_id: str
    project_name: str
    revision_id: str
    library_name: str
    library_path: Path
    root_ino_path: Path
    project_meta_path: Path
    ui_elements_path: Path
    lvgl_version: str
    lvgl_storage: str

    @property
    def display_path(self) -> str:
        return (
            f"{self.client_name} / {self.project_name} / "
            f"{self.revision_id} / {self.library_name}"
        )


@dataclass(frozen=True)
class VaultIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class VaultInventory:
    root: Path
    revisions: tuple[ProjectRevision, ...]
    issues: tuple[VaultIssue, ...]


@dataclass(frozen=True)
class JunctionPlan:
    action: str
    library_name: str
    link_path: Path
    target_path: Path
    current_target: Path | None
    status: str
    message: str
    previous_library_name: str | None = None


@dataclass(frozen=True)
class JunctionResult:
    action: str
    library_name: str
    link_path: Path
    target_path: Path
    state_path: Path
    message: str
    previous_library_name: str | None = None
    linked_at: str | None = None


@dataclass(frozen=True)
class ActiveProjectLink:
    library_name: str
    link_path: Path
    target_path: Path
    client_id: str
    project_id: str
    revision_id: str
    linked_at: str
    verified: bool
    message: str


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectVaultError(f"{label} must be a non-empty string.")
    return value.strip()


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectVaultError(f"{label} must be an object.")
    return value


def _require_stable_id(value: Any, label: str) -> str:
    stable_id = _require_string(value, label)
    if not STABLE_ID_PATTERN.fullmatch(stable_id):
        raise ProjectVaultError(
            f"{label} must use only letters, numbers, underscores, and dashes "
            "and must be at most 63 characters."
        )
    return stable_id


def _require_library_name(value: Any) -> str:
    library_name = _require_string(value, "Library name")
    if not LIBRARY_NAME_PATTERN.fullmatch(library_name):
        raise ProjectVaultError(
            "Library name must start with a letter or number, use only letters, "
            "numbers, underscores, dots, and dashes, and be at most 63 characters."
        )
    return library_name


def _resolved_child(
    root: Path,
    raw_relative_path: Any,
    label: str,
    *,
    must_exist: bool,
) -> Path:
    relative_text = _require_string(raw_relative_path, label)
    relative = Path(relative_text)
    if relative.is_absolute() or relative.drive or relative.anchor:
        raise ProjectVaultError(f"{label} must be a relative path.")
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ProjectVaultError(f"{label} escapes the project revision.") from error
    if must_exist and not candidate.exists():
        raise ProjectVaultError(f"{label} does not exist: {candidate}")
    return candidate


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectVaultError(f"Cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProjectVaultError(f"{label} must contain a JSON object: {path}")
    return value


class ProjectVaultService:
    def __init__(self, vault_root: str | Path) -> None:
        self.root = Path(vault_root).expanduser().resolve(strict=False)
        if self.root.name != VAULT_DIRECTORY_NAME:
            raise ProjectVaultError(
                f"The project vault folder must be named {VAULT_DIRECTORY_NAME}."
            )

    @property
    def clients_root(self) -> Path:
        return self.root / CLIENTS_DIRECTORY_NAME

    def initialize(self) -> Path:
        self.clients_root.mkdir(parents=True, exist_ok=True)
        return self.root

    def scan(self) -> VaultInventory:
        revisions: list[ProjectRevision] = []
        issues: list[VaultIssue] = []
        if not self.root.exists():
            return VaultInventory(self.root, (), ())
        if not self.root.is_dir():
            return VaultInventory(
                self.root,
                (),
                (VaultIssue(self.root, "The configured vault root is not a directory."),),
            )
        if not self.clients_root.exists():
            return VaultInventory(self.root, (), ())

        for manifest_path in sorted(
            self.clients_root.glob(
                f"*/Projects/*/Revisions/*/{PROJECT_MANIFEST_NAME}"
            ),
            key=lambda item: str(item).casefold(),
        ):
            try:
                revisions.append(self.load_revision(manifest_path))
            except ProjectVaultError as error:
                issues.append(VaultIssue(manifest_path, str(error)))
        return VaultInventory(self.root, tuple(revisions), tuple(issues))

    def load_revision(self, manifest_path: str | Path) -> ProjectRevision:
        path = Path(manifest_path).expanduser().resolve(strict=False)
        if path.name != PROJECT_MANIFEST_NAME or not path.is_file():
            raise ProjectVaultError(
                f"Project manifest was not found as {PROJECT_MANIFEST_NAME}: {path}"
            )
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ProjectVaultError(
                f"Project manifest is outside the configured vault: {path}"
            ) from error

        data = _read_json_object(path, "project manifest")
        if data.get("schemaVersion") != PROJECT_MANIFEST_SCHEMA_VERSION:
            raise ProjectVaultError("Unsupported project manifest schema version.")

        revision_data = _require_object(data.get("revision"), "Revision")
        client_data = _require_object(data.get("client"), "Client")
        project_data = _require_object(data.get("project"), "Project")
        library_data = _require_object(data.get("library"), "Library")
        handoff_data = _require_object(data.get("handoff"), "Handoff")
        lvgl_data = _require_object(library_data.get("lvgl"), "Library LVGL")

        revision_id = _require_stable_id(revision_data.get("id"), "Revision ID")
        if revision_data.get("immutable") is not True:
            raise ProjectVaultError("Project revision must be marked immutable.")
        client_id = _require_stable_id(client_data.get("id"), "Client ID")
        project_id = _require_stable_id(project_data.get("id"), "Project ID")
        client_name = _require_string(client_data.get("name"), "Client name")
        project_name = _require_string(project_data.get("name"), "Project name")
        library_name = _require_library_name(library_data.get("name"))
        if library_data.get("selfContained") is not True:
            raise ProjectVaultError("Project library must be marked selfContained.")

        revision_path = path.parent.resolve(strict=True)
        expected_relative = Path("libraries") / library_name
        configured_relative_text = _require_string(
            library_data.get("relativePath"), "Library relativePath"
        )
        configured_relative = Path(configured_relative_text)
        if configured_relative != expected_relative:
            raise ProjectVaultError(
                f"Library relativePath must be {expected_relative.as_posix()}."
            )
        library_path = _resolved_child(
            revision_path,
            configured_relative_text,
            "Library relativePath",
            must_exist=True,
        )
        if not library_path.is_dir():
            raise ProjectVaultError(
                f"Project library target is not a directory: {library_path}"
            )
        if library_path.name != library_name:
            raise ProjectVaultError(
                "Project library folder name does not match the manifest."
            )
        if not (library_path / "library.properties").is_file():
            raise ProjectVaultError(
                f"Project library is missing library.properties: {library_path}"
            )
        source_path = library_path / "src"
        if not source_path.is_dir():
            raise ProjectVaultError(
                f"Project library is missing its src directory: {library_path}"
            )
        if not (source_path / f"{library_name}.h").is_file():
            raise ProjectVaultError(
                f"Project library is missing its public {library_name}.h header."
            )

        lvgl_version = _require_string(lvgl_data.get("version"), "LVGL version")
        lvgl_storage = _require_string(lvgl_data.get("storage"), "LVGL storage")
        if lvgl_storage != "vendored":
            raise ProjectVaultError(
                "Project Vault currently permits only vendored immutable LVGL storage."
            )
        vendored_lvgl = source_path / "vendor" / "lvgl"
        if not vendored_lvgl.is_dir():
            raise ProjectVaultError(
                f"Vendored LVGL directory was not found: {vendored_lvgl}"
            )

        root_ino_path = _resolved_child(
            revision_path,
            handoff_data.get("rootIno"),
            "Handoff rootIno",
            must_exist=True,
        )
        if root_ino_path.parent != revision_path or root_ino_path.suffix.casefold() != ".ino":
            raise ProjectVaultError("Handoff rootIno must be one root INO file.")
        root_ino_files = tuple(revision_path.glob("*.ino"))
        if len(root_ino_files) != 1 or root_ino_files[0].resolve() != root_ino_path:
            raise ProjectVaultError(
                "Project revision must contain exactly one root INO matching handoff.rootIno."
            )

        project_meta_path = _resolved_child(
            revision_path,
            handoff_data.get("projectMeta"),
            "Handoff projectMeta",
            must_exist=True,
        )
        ui_elements_path = _resolved_child(
            revision_path,
            handoff_data.get("uiElements"),
            "Handoff uiElements",
            must_exist=True,
        )
        _read_json_object(project_meta_path, "project metadata")
        _read_json_object(ui_elements_path, "UI element metadata")

        hierarchy = revision_path.relative_to(self.clients_root).parts
        expected_hierarchy = (
            client_id,
            "Projects",
            project_id,
            "Revisions",
            revision_id,
        )
        if hierarchy != expected_hierarchy:
            raise ProjectVaultError(
                "Manifest IDs do not match the Client/Project/Revision directory hierarchy."
            )

        return ProjectRevision(
            manifest_path=path,
            revision_path=revision_path,
            client_id=client_id,
            client_name=client_name,
            project_id=project_id,
            project_name=project_name,
            revision_id=revision_id,
            library_name=library_name,
            library_path=library_path,
            root_ino_path=root_ino_path,
            project_meta_path=project_meta_path,
            ui_elements_path=ui_elements_path,
            lvgl_version=lvgl_version,
            lvgl_storage=lvgl_storage,
        )


def empty_link_registry() -> dict[str, Any]:
    return {"schemaVersion": LINK_REGISTRY_SCHEMA_VERSION, "links": []}


def validate_link_registry(
    data: Any,
    *,
    vault_root: Path,
    libraries_path: Path,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectVaultError("Managed-link registry must be a JSON object.")
    if data.get("schemaVersion") != LINK_REGISTRY_SCHEMA_VERSION:
        raise ProjectVaultError("Unsupported managed-link registry schema version.")
    links = data.get("links")
    if not isinstance(links, list):
        raise ProjectVaultError("Managed-link registry links must be a list.")

    names: set[str] = set()
    for entry in links:
        if not isinstance(entry, dict):
            raise ProjectVaultError("Managed-link entries must be objects.")
        name = _require_library_name(entry.get("name"))
        if name.casefold() in names:
            raise ProjectVaultError(f"Duplicate managed-link name: {name}")
        names.add(name.casefold())
        target = Path(_require_string(entry.get("target"), "Managed-link target"))
        if not target.is_absolute():
            raise ProjectVaultError("Managed-link target must be absolute.")
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(vault_root)
        except ValueError as error:
            raise ProjectVaultError(
                f"Managed-link target is outside the project vault: {target}"
            ) from error
        link = Path(_require_string(entry.get("link"), "Managed-link path"))
        expected_link = libraries_path / name
        if (
            link.name != expected_link.name
            or link.parent.resolve(strict=False)
            != expected_link.parent.resolve(strict=False)
        ):
            raise ProjectVaultError(
                f"Managed-link path must be the direct library child {expected_link}."
            )
        _require_stable_id(entry.get("clientId"), "Managed-link client ID")
        _require_stable_id(entry.get("projectId"), "Managed-link project ID")
        _require_stable_id(entry.get("revisionId"), "Managed-link revision ID")
        _require_string(entry.get("linkedAt"), "Managed-link linkedAt")
    return data


class LinkRegistryRepository:
    def __init__(
        self,
        path: Path,
        previous_path: Path,
        *,
        vault_root: Path,
        libraries_path: Path,
    ) -> None:
        self.path = path
        self.previous_path = previous_path
        self.vault_root = vault_root
        self.libraries_path = libraries_path
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return empty_link_registry()
            try:
                return self._read_valid(self.path)
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ProjectVaultError,
            ) as current_error:
                if self.previous_path.exists():
                    try:
                        return self._read_valid(self.previous_path)
                    except (
                        OSError,
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                        ProjectVaultError,
                    ):
                        pass
                raise ProjectVaultError(
                    "The managed-link registry is invalid and no valid previous "
                    f"copy is available: {current_error}"
                ) from current_error

    def _read_valid(self, path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return validate_link_registry(
            data,
            vault_root=self.vault_root,
            libraries_path=self.libraries_path,
        )

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            validate_link_registry(
                data,
                vault_root=self.vault_root,
                libraries_path=self.libraries_path,
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(
                f"{self.path.name}.{uuid.uuid4().hex}.tmp"
            )
            try:
                temporary.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                self._read_valid(temporary)
                if self.path.exists():
                    self._read_valid(self.path)
                    shutil.copy2(self.path, self.previous_path)
                os.replace(temporary, self.path)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise


class ManagedJunctionService:
    def __init__(
        self,
        *,
        libraries_path: str | Path,
        vault_root: str | Path,
        state_path: str | Path,
        previous_state_path: str | Path | None = None,
        backend: JunctionBackend | None = None,
        running_check: Callable[[], bool] = lambda: False,
    ) -> None:
        self.libraries_path = Path(libraries_path).expanduser().resolve(strict=False)
        self.vault_root = Path(vault_root).expanduser().resolve(strict=False)
        self.state_path = Path(state_path).expanduser().resolve(strict=False)
        self.previous_state_path = (
            Path(previous_state_path).expanduser().resolve(strict=False)
            if previous_state_path is not None
            else self.state_path.with_name(f"{self.state_path.stem}.previous.json")
        )
        self.backend = backend or WindowsJunctionBackend()
        self.running_check = running_check
        self._lock = threading.RLock()
        self._validate_roots()
        self.repository = LinkRegistryRepository(
            self.state_path,
            self.previous_state_path,
            vault_root=self.vault_root,
            libraries_path=self.libraries_path,
        )

    def _validate_roots(self) -> None:
        if self.libraries_path.name.casefold() != "libraries":
            raise ProjectVaultError(
                "Managed junctions require the normal sketchbook libraries folder."
            )
        if self.vault_root.name != VAULT_DIRECTORY_NAME:
            raise ProjectVaultError(
                f"The project vault folder must be named {VAULT_DIRECTORY_NAME}."
            )
        if self.libraries_path.parent != self.vault_root.parent:
            raise ProjectVaultError(
                "The project vault must be a sibling of the normal libraries folder."
            )
        if (
            self.libraries_path.drive.casefold()
            != self.vault_root.drive.casefold()
        ):
            raise ProjectVaultError(
                "The project vault and libraries folder must use the same local volume."
            )

    def initialize(self) -> None:
        self.libraries_path.mkdir(parents=True, exist_ok=True)
        (self.vault_root / CLIENTS_DIRECTORY_NAME).mkdir(parents=True, exist_ok=True)

    def plan(self, revision: ProjectRevision) -> JunctionPlan:
        self._validate_revision_target(revision)
        link_path = self.libraries_path / revision.library_name
        state = self.repository.load()
        owned = self._owned_entry(state, revision.library_name)
        other_entries = [
            entry
            for entry in state["links"]
            if entry["name"].casefold() != revision.library_name.casefold()
        ]
        invalid_active = [
            active
            for active in self._active_links(state)
            if not active.verified
            and active.library_name.casefold()
            != revision.library_name.casefold()
        ]
        if invalid_active:
            invalid_names = ", ".join(
                active.library_name for active in invalid_active
            )
            return JunctionPlan(
                action="blocked",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=None,
                status="broken",
                message=(
                    "The recorded active junction state is not safe to switch. "
                    f"Resolve the managed link first: {invalid_names}"
                ),
            )
        previous_library_name = (
            other_entries[0]["name"] if len(other_entries) == 1 else None
        )

        if not os.path.lexists(link_path):
            status = "broken" if owned is not None else "inactive"
            return JunctionPlan(
                action="switch" if other_entries else "create",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=None,
                status=status,
                message=(
                    "Recreate the missing FAH-owned junction."
                    if owned is not None
                    else (
                        "Switch the one active Project Vault revision to this "
                        "library."
                        if other_entries
                        else "Activate this Project Vault revision."
                    )
                ),
                previous_library_name=previous_library_name,
            )

        if not self.backend.is_junction(link_path):
            return JunctionPlan(
                action="blocked",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=None,
                status="conflict",
                message=(
                    "A real folder, file, symbolic link, or foreign reparse point "
                    "blocks this library name."
                ),
            )

        try:
            current_target = self.backend.target(link_path)
        except ProjectVaultError:
            current_target = None
        if owned is None:
            return JunctionPlan(
                action="blocked",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=current_target,
                status="conflict",
                message="The existing junction is not owned by FAH.",
            )
        expected_owned_target = Path(owned["target"]).resolve(strict=False)
        if current_target is None or current_target != expected_owned_target:
            return JunctionPlan(
                action="blocked",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=current_target,
                status="broken",
                message="The FAH ownership record and current junction target disagree.",
            )
        if current_target != revision.library_path:
            return JunctionPlan(
                action="blocked",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=current_target,
                status="conflict",
                message=(
                    "This FAH library name is already linked to another immutable "
                    "revision."
                ),
            )
        if other_entries:
            return JunctionPlan(
                action="switch",
                library_name=revision.library_name,
                link_path=link_path,
                target_path=revision.library_path,
                current_target=current_target,
                status="active",
                message=(
                    "Make this the only active Project Vault revision and remove "
                    "the other verified FAH-owned junctions."
                ),
                previous_library_name=previous_library_name,
            )
        return JunctionPlan(
            action="unchanged",
            library_name=revision.library_name,
            link_path=link_path,
            target_path=revision.library_path,
            current_target=current_target,
            status="active",
            message="The project-library junction is already active and verified.",
        )

    def status(self, revision: ProjectRevision) -> str:
        return self.plan(revision).status

    def active_links(self) -> tuple[ActiveProjectLink, ...]:
        return self._active_links(self.repository.load())

    def activate(self, revision: ProjectRevision) -> JunctionResult:
        with self._lock:
            if self.running_check():
                raise ProjectVaultError(
                    "Close Visuino before switching the active Project Vault revision."
                )
            self.initialize()
            plan = self.plan(revision)
            if plan.action == "blocked":
                raise ProjectVaultError(plan.message)
            state = self.repository.load()
            owned = self._owned_entry(state, revision.library_name)
            if plan.action == "unchanged":
                return JunctionResult(
                    action="unchanged",
                    library_name=revision.library_name,
                    link_path=plan.link_path,
                    target_path=plan.target_path,
                    state_path=self.state_path,
                    message=plan.message,
                    linked_at=owned["linkedAt"] if owned is not None else None,
                )

            if owned is not None:
                expected_target = Path(owned["target"]).resolve(strict=False)
                if expected_target != revision.library_path:
                    raise ProjectVaultError(
                        "The existing FAH ownership record targets another revision."
                    )

            previous_entries = [
                copy.deepcopy(entry)
                for entry in state["links"]
                if entry["name"].casefold() != revision.library_name.casefold()
            ]
            for entry in previous_entries:
                self._require_verified_entry(entry)

            target_already_active = (
                plan.current_target == revision.library_path
                and self.backend.is_junction(plan.link_path)
            )
            created_target = False
            removed_entries: list[dict[str, Any]] = []
            linked_at = _now_iso()
            try:
                if not target_already_active:
                    self.backend.create(revision.library_path, plan.link_path)
                    created_target = True
                if not self.backend.is_junction(plan.link_path):
                    raise ProjectVaultError(
                        "The created path did not verify as a directory junction."
                    )
                actual_target = self.backend.target(plan.link_path)
                if actual_target != revision.library_path:
                    raise ProjectVaultError(
                        "The created junction target did not match the project revision."
                    )
                for entry in previous_entries:
                    previous_link, previous_target = self._require_verified_entry(
                        entry
                    )
                    self.backend.remove(previous_link)
                    removed_entries.append(entry)
                    if not previous_target.is_dir():
                        raise ProjectVaultError(
                            "A previous project target was not preserved during "
                            "the active-revision switch."
                        )
                new_state = {
                    "schemaVersion": LINK_REGISTRY_SCHEMA_VERSION,
                    "links": [
                    {
                        "name": revision.library_name,
                        "link": str(plan.link_path),
                        "target": str(revision.library_path),
                        "clientId": revision.client_id,
                        "projectId": revision.project_id,
                        "revisionId": revision.revision_id,
                        "linkedAt": linked_at,
                    }
                    ],
                }
                self.repository.save(new_state)
            except Exception as error:
                recovery_errors: list[str] = []
                if created_target:
                    try:
                        if self.backend.is_junction(plan.link_path):
                            actual_target = self.backend.target(plan.link_path)
                            if actual_target == revision.library_path:
                                self.backend.remove(plan.link_path)
                    except Exception as recovery_error:
                        recovery_errors.append(
                            f"new link cleanup failed: {recovery_error}"
                        )
                for entry in reversed(removed_entries):
                    try:
                        previous_link = Path(entry["link"])
                        previous_target = Path(entry["target"]).resolve(strict=False)
                        if not os.path.lexists(previous_link):
                            self.backend.create(previous_target, previous_link)
                        restored_link, restored_target = self._require_verified_entry(
                            entry
                        )
                        if (
                            restored_link != previous_link
                            or restored_target != previous_target
                        ):
                            raise ProjectVaultError(
                                "The restored junction did not match its record."
                            )
                    except Exception as recovery_error:
                        recovery_errors.append(
                            f"{entry['name']} restore failed: {recovery_error}"
                        )
                if recovery_errors:
                    raise ProjectVaultError(
                        "The active-revision switch failed and rollback was "
                        "incomplete. "
                        + " | ".join(recovery_errors)
                    ) from error
                raise ProjectVaultError(
                    "The active-revision switch failed. The previous verified "
                    "junction and immutable project targets were restored."
                ) from error

            previous_library_name = (
                previous_entries[0]["name"] if len(previous_entries) == 1 else None
            )
            action = "switched" if previous_entries else "created"
            return JunctionResult(
                action=action,
                library_name=revision.library_name,
                link_path=plan.link_path,
                target_path=revision.library_path,
                state_path=self.state_path,
                message=(
                    "The active Project Vault revision was switched and verified."
                    if previous_entries
                    else "The Project Vault revision was activated and verified."
                ),
                previous_library_name=previous_library_name,
                linked_at=linked_at,
            )

    def deactivate(self, library_name: str) -> JunctionResult:
        with self._lock:
            if self.running_check():
                raise ProjectVaultError(
                    "Close Visuino before removing a project-library junction."
                )
            name = _require_library_name(library_name)
            state = self.repository.load()
            owned = self._owned_entry(state, name)
            if owned is None:
                raise ProjectVaultError(
                    f"The library junction is not owned by FAH: {name}"
                )
            link_path = self.libraries_path / name
            target_path = Path(owned["target"]).resolve(strict=False)
            if not self.backend.is_junction(link_path):
                raise ProjectVaultError(
                    "The owned link is missing or no longer a directory junction."
                )
            actual_target = self.backend.target(link_path)
            if actual_target != target_path:
                raise ProjectVaultError(
                    "The junction target changed after it was recorded; removal is blocked."
                )
            self.backend.remove(link_path)
            try:
                new_state = copy.deepcopy(state)
                new_state["links"] = [
                    entry
                    for entry in new_state["links"]
                    if entry["name"].casefold() != name.casefold()
                ]
                self.repository.save(new_state)
            except Exception:
                self.backend.create(target_path, link_path)
                raise
            if not target_path.is_dir():
                raise ProjectVaultError(
                    "The project target was not preserved after link removal."
                )
            return JunctionResult(
                action="removed",
                library_name=name,
                link_path=link_path,
                target_path=target_path,
                state_path=self.state_path,
                message="The FAH junction was removed and its project target was preserved.",
            )

    def _validate_revision_target(self, revision: ProjectRevision) -> None:
        if not revision.library_path.is_dir():
            raise ProjectVaultError(
                f"Project library target does not exist: {revision.library_path}"
            )
        try:
            revision.library_path.relative_to(self.vault_root)
        except ValueError as error:
            raise ProjectVaultError(
                "Project library target is outside the configured vault."
            ) from error
        if revision.library_path.name != revision.library_name:
            raise ProjectVaultError(
                "Project library target name does not match the manifest."
            )

    def _active_links(
        self, state: dict[str, Any]
    ) -> tuple[ActiveProjectLink, ...]:
        active_links: list[ActiveProjectLink] = []
        for entry in state["links"]:
            link_path = Path(entry["link"])
            target_path = Path(entry["target"]).resolve(strict=False)
            verified = False
            message = "The recorded junction is missing."
            if os.path.lexists(link_path):
                if not self.backend.is_junction(link_path):
                    message = "The recorded path is not a directory junction."
                else:
                    try:
                        actual_target = self.backend.target(link_path)
                    except ProjectVaultError as error:
                        message = str(error)
                    else:
                        if actual_target != target_path:
                            message = (
                                "The recorded junction target does not match "
                                "the active-link manifest."
                            )
                        elif not target_path.is_dir():
                            message = "The immutable project target is missing."
                        else:
                            verified = True
                            message = "The active project-library junction is verified."
            active_links.append(
                ActiveProjectLink(
                    library_name=entry["name"],
                    link_path=link_path,
                    target_path=target_path,
                    client_id=entry["clientId"],
                    project_id=entry["projectId"],
                    revision_id=entry["revisionId"],
                    linked_at=entry["linkedAt"],
                    verified=verified,
                    message=message,
                )
            )
        return tuple(active_links)

    def _require_verified_entry(
        self, entry: dict[str, Any]
    ) -> tuple[Path, Path]:
        link_path = Path(entry["link"])
        target_path = Path(entry["target"]).resolve(strict=False)
        if not self.backend.is_junction(link_path):
            raise ProjectVaultError(
                f"The previous managed link is missing or unsafe: {link_path}"
            )
        actual_target = self.backend.target(link_path)
        if actual_target != target_path:
            raise ProjectVaultError(
                f"The previous managed link target changed: {link_path}"
            )
        if not target_path.is_dir():
            raise ProjectVaultError(
                f"The previous immutable project target is missing: {target_path}"
            )
        return link_path, target_path

    @staticmethod
    def _owned_entry(
        state: dict[str, Any], library_name: str
    ) -> dict[str, Any] | None:
        return next(
            (
                entry
                for entry in state["links"]
                if entry["name"].casefold() == library_name.casefold()
            ),
            None,
        )
