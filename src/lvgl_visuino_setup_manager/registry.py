from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import resolve_safe_directory


VALIDATION_STATES = {"unknown", "valid", "invalid", "busy"}
DEVICE_PACKAGE_STATES = {"unknown", "valid", "invalid"}
SCHEMA_VERSION = 3


class RegistryError(RuntimeError):
    """Raised when the local registry is missing required structure or cannot be saved."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def empty_registry() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "activeSetupId": None,
        "defaultSetupId": None,
        "clients": [],
    }


def _require_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{label} must be a non-empty string.")
    return value.strip()


def migrate_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RegistryError("The registry root must be a JSON object.")
    version = data.get("schemaVersion")
    if version == SCHEMA_VERSION:
        return data
    if version not in {1, 2}:
        raise RegistryError("Unsupported registry schema version.")

    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = SCHEMA_VERSION
    clients = migrated.get("clients")
    if isinstance(clients, list):
        for client in clients:
            if not isinstance(client, dict):
                continue
            projects = client.get("projects")
            if not isinstance(projects, list):
                continue
            for project in projects:
                if not isinstance(project, dict):
                    continue
                setups = project.get("setups")
                if not isinstance(setups, list):
                    continue
                for setup in setups:
                    if isinstance(setup, dict):
                        setup.setdefault("devicePackage", None)
                        baseline = setup.get("baseline")
                        if isinstance(baseline, dict):
                            baseline["mitovRequired"] = True
                            baseline["visuinoProRequired"] = False
                            baseline["copyPolicy"] = "missing_only"
    return migrated


def validate_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RegistryError("The registry root must be a JSON object.")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise RegistryError("Unsupported registry schema version.")
    clients = data.get("clients")
    if not isinstance(clients, list):
        raise RegistryError("Registry clients must be a list.")

    ids: set[str] = set()
    setup_ids: set[str] = set()
    for client in clients:
        if not isinstance(client, dict):
            raise RegistryError("Each client must be an object.")
        client_id = _require_name(client.get("id"), "Client ID")
        if client_id in ids:
            raise RegistryError(f"Duplicate ID: {client_id}")
        ids.add(client_id)
        _require_name(client.get("name"), "Client name")
        projects = client.get("projects")
        if not isinstance(projects, list):
            raise RegistryError("Client projects must be a list.")

        for project in projects:
            if not isinstance(project, dict):
                raise RegistryError("Each project must be an object.")
            project_id = _require_name(project.get("id"), "Project ID")
            if project_id in ids:
                raise RegistryError(f"Duplicate ID: {project_id}")
            ids.add(project_id)
            _require_name(project.get("name"), "Project name")
            setups = project.get("setups")
            if not isinstance(setups, list):
                raise RegistryError("Project setups must be a list.")

            for setup in setups:
                if not isinstance(setup, dict):
                    raise RegistryError("Each setup must be an object.")
                setup_id = _require_name(setup.get("id"), "Setup ID")
                if setup_id in ids:
                    raise RegistryError(f"Duplicate ID: {setup_id}")
                ids.add(setup_id)
                setup_ids.add(setup_id)
                _require_name(setup.get("name"), "Setup name")
                folder_path = _require_name(setup.get("folderPath"), "Setup folderPath")
                resolve_safe_directory(folder_path, must_exist=False)

                baseline = setup.get("baseline")
                if not isinstance(baseline, dict):
                    raise RegistryError("Setup baseline must be an object.")
                if baseline.get("mitovRequired") is not True:
                    raise RegistryError("Mitov must be required for every setup.")
                if baseline.get("visuinoProRequired") is not False:
                    raise RegistryError(
                        "VisuinoPro must be optional for every setup."
                    )
                if baseline.get("copyPolicy") != "missing_only":
                    raise RegistryError(
                        "Setup baseline copyPolicy must be missing_only."
                    )

                validation = setup.get("validation")
                if not isinstance(validation, dict):
                    raise RegistryError("Setup validation must be an object.")
                if validation.get("status") not in VALIDATION_STATES:
                    raise RegistryError("Setup validation status is invalid.")
                warnings = validation.get("warnings")
                if not isinstance(warnings, list) or not all(
                    isinstance(item, str) for item in warnings
                ):
                    raise RegistryError("Setup validation warnings must be a string list.")

                device_package = setup.get("devicePackage")
                if device_package is not None:
                    if not isinstance(device_package, dict):
                        raise RegistryError("Setup devicePackage must be an object or null.")
                    for key, label in (
                        ("id", "Device package ID"),
                        ("revision", "Device package revision"),
                        ("libraryFolder", "Device package libraryFolder"),
                        ("manifestPath", "Device package manifestPath"),
                        ("sourcePath", "Device package sourcePath"),
                    ):
                        _require_name(device_package.get(key), label)
                    if device_package.get("status") not in DEVICE_PACKAGE_STATES:
                        raise RegistryError("Device package status is invalid.")
                    package_warnings = device_package.get("warnings")
                    if not isinstance(package_warnings, list) or not all(
                        isinstance(item, str) for item in package_warnings
                    ):
                        raise RegistryError(
                            "Device package warnings must be a string list."
                        )
                    imported_at = device_package.get("lastImportedAt")
                    if imported_at is not None:
                        _require_name(imported_at, "Device package lastImportedAt")
                _require_name(setup.get("createdAt"), "Setup createdAt")
                _require_name(setup.get("updatedAt"), "Setup updatedAt")

    active_id = data.get("activeSetupId")
    default_id = data.get("defaultSetupId")
    if active_id is not None and active_id not in setup_ids:
        raise RegistryError("activeSetupId does not reference a known setup.")
    if default_id is not None and default_id not in setup_ids:
        raise RegistryError("defaultSetupId does not reference a known setup.")
    return data


class RegistryRepository:
    def __init__(self, path: Path, previous_path: Path) -> None:
        self.path = path
        self.previous_path = previous_path
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return empty_registry()
            try:
                return self._read_valid(self.path)
            except (OSError, json.JSONDecodeError, RegistryError) as current_error:
                if self.previous_path.exists():
                    try:
                        return self._read_valid(self.previous_path)
                    except (OSError, json.JSONDecodeError, RegistryError):
                        pass
                raise RegistryError(
                    f"The registry is invalid and no valid previous copy is available: "
                    f"{current_error}"
                ) from current_error

    def _read_valid(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return validate_registry(migrate_registry(data))

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            validate_registry(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
            try:
                with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
                    json.dump(data, stream, indent=2, ensure_ascii=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                self._read_valid(temp_path)
                if self.path.exists():
                    self._read_valid(self.path)
                    shutil.copy2(self.path, self.previous_path)
                os.replace(temp_path, self.path)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise


class RegistryService:
    def __init__(self, repository: RegistryRepository) -> None:
        self.repository = repository
        self._lock = threading.RLock()
        self.data = repository.load()

    def reload(self) -> None:
        with self._lock:
            self.data = self.repository.load()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self.data)

    def _save(self) -> None:
        self.repository.save(self.data)

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _ensure_unique_name(records: list[dict[str, Any]], name: str, label: str) -> str:
        cleaned = _require_name(name, label)
        if any(item["name"].casefold() == cleaned.casefold() for item in records):
            raise RegistryError(f"{label} already exists: {cleaned}")
        return cleaned

    def create_client(self, name: str) -> str:
        with self._lock:
            cleaned = self._ensure_unique_name(self.data["clients"], name, "Client")
            client_id = self._new_id("client")
            self.data["clients"].append(
                {"id": client_id, "name": cleaned, "projects": []}
            )
            self._save()
            return client_id

    def rename_client(self, client_id: str, name: str) -> None:
        with self._lock:
            client = self.find_client(client_id)
            peers = [item for item in self.data["clients"] if item["id"] != client_id]
            client["name"] = self._ensure_unique_name(peers, name, "Client")
            self._save()

    def create_project(self, client_id: str, name: str) -> str:
        with self._lock:
            client = self.find_client(client_id)
            cleaned = self._ensure_unique_name(client["projects"], name, "Project")
            project_id = self._new_id("project")
            client["projects"].append(
                {"id": project_id, "name": cleaned, "setups": []}
            )
            self._save()
            return project_id

    def rename_project(self, client_id: str, project_id: str, name: str) -> None:
        with self._lock:
            client = self.find_client(client_id)
            project = self.find_project(client_id, project_id)
            peers = [item for item in client["projects"] if item["id"] != project_id]
            project["name"] = self._ensure_unique_name(peers, name, "Project")
            self._save()

    def create_setup(
        self, client_id: str, project_id: str, name: str, folder_path: str | Path
    ) -> str:
        with self._lock:
            project = self.find_project(client_id, project_id)
            cleaned = self._ensure_unique_name(project["setups"], name, "Setup")
            resolved = resolve_safe_directory(folder_path, must_exist=False)
            setup_id = self._new_id("setup")
            timestamp = now_iso()
            project["setups"].append(
                {
                    "id": setup_id,
                    "name": cleaned,
                    "folderPath": str(resolved),
                    "baseline": {
                        "mitovRequired": True,
                        "visuinoProRequired": False,
                        "copyPolicy": "missing_only",
                    },
                    "validation": {
                        "status": "unknown",
                        "lastValidatedAt": None,
                        "warnings": [],
                    },
                    "devicePackage": None,
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                }
            )
            self._save()
            return setup_id

    def rename_setup(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
        name: str,
    ) -> None:
        with self._lock:
            project = self.find_project(client_id, project_id)
            setup = next(
                (item for item in project["setups"] if item["id"] == setup_id),
                None,
            )
            if setup is None:
                raise RegistryError(f"Unknown setup ID: {setup_id}")
            peers = [item for item in project["setups"] if item["id"] != setup_id]
            setup["name"] = self._ensure_unique_name(peers, name, "Setup")
            setup["updatedAt"] = now_iso()
            self._save()

    def remove_setup(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            if self.data.get("activeSetupId") == setup_id:
                raise RegistryError(
                    "The active setup profile cannot be removed. "
                    "Restore the default setup first."
                )
            project = self.find_project(client_id, project_id)
            setup_index = next(
                (
                    index
                    for index, item in enumerate(project["setups"])
                    if item["id"] == setup_id
                ),
                None,
            )
            if setup_index is None:
                raise RegistryError(f"Unknown setup ID: {setup_id}")
            removed = project["setups"].pop(setup_index)
            if self.data.get("defaultSetupId") == setup_id:
                self.data["defaultSetupId"] = None
            self._save()
            return copy.deepcopy(removed)

    def update_validation(
        self,
        setup_id: str,
        *,
        status: str,
        checked_at: str,
        warnings: list[str],
    ) -> None:
        if status not in VALIDATION_STATES:
            raise RegistryError(f"Invalid validation status: {status}")
        with self._lock:
            setup = self.find_setup(setup_id)
            setup["validation"] = {
                "status": status,
                "lastValidatedAt": checked_at,
                "warnings": list(warnings),
            }
            setup["updatedAt"] = now_iso()
            self._save()

    def set_active_setup(self, setup_id: str | None) -> None:
        with self._lock:
            if setup_id is not None:
                self.find_setup(setup_id)
            self.data["activeSetupId"] = setup_id
            self._save()

    def set_device_package(
        self, setup_id: str, device_package: dict[str, Any] | None
    ) -> None:
        with self._lock:
            setup = self.find_setup(setup_id)
            setup["devicePackage"] = copy.deepcopy(device_package)
            setup["updatedAt"] = now_iso()
            self._save()

    def reset_setup_content_state(self, setup_id: str) -> None:
        with self._lock:
            setup = self.find_setup(setup_id)
            setup["validation"] = {
                "status": "unknown",
                "lastValidatedAt": None,
                "warnings": [],
            }
            setup["devicePackage"] = None
            setup["updatedAt"] = now_iso()
            self._save()

    def find_client(self, client_id: str) -> dict[str, Any]:
        for client in self.data["clients"]:
            if client["id"] == client_id:
                return client
        raise RegistryError(f"Unknown client ID: {client_id}")

    def find_project(self, client_id: str, project_id: str) -> dict[str, Any]:
        client = self.find_client(client_id)
        for project in client["projects"]:
            if project["id"] == project_id:
                return project
        raise RegistryError(f"Unknown project ID: {project_id}")

    def find_setup(self, setup_id: str) -> dict[str, Any]:
        for client in self.data["clients"]:
            for project in client["projects"]:
                for setup in project["setups"]:
                    if setup["id"] == setup_id:
                        return setup
        raise RegistryError(f"Unknown setup ID: {setup_id}")
