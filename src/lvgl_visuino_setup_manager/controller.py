from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .activation import ActivationResult, ActivationService, RestoreResult
from .audit import AuditRepository
from .implementation import (
    DEFAULT_LIBRARY_NAME,
    CustomCodeHooks,
    ImplementationError,
    ImplementationService,
    ImplementationValidation,
    ImportPlan,
    ImportResult,
    UiElementVariable,
)
from .registry import RegistryService
from .profile_cleanup import (
    CLEAR_CONTENTS,
    ProfileCleanupError,
    ProfileCleanupPlan,
    ProfileCleanupResult,
    ProfileCleanupService,
)
from .project_vault import (
    ActiveProjectLink,
    JunctionPlan,
    JunctionResult,
    ManagedJunctionService,
    ProjectRevision,
    ProjectVaultError,
    ProjectVaultService,
    VaultInventory,
)
from .project_vault_import import (
    ProjectVaultImportPlan,
    ProjectVaultImportRequest,
    ProjectVaultImportResult,
    ProjectVaultImportService,
)
from .setup_service import (
    BaselineRepairError,
    BaselineRepairPlan,
    BaselineRepairResult,
    SetupService,
    ValidationResult,
)


class ApplicationController:
    def __init__(
        self,
        registry: RegistryService,
        setup_service: SetupService,
        implementation_service: ImplementationService,
        activation_service: ActivationService,
        audit: AuditRepository,
        profile_cleanup_service: ProfileCleanupService | None = None,
        project_vault_service: ProjectVaultService | None = None,
        managed_junction_service: ManagedJunctionService | None = None,
        project_vault_import_service: ProjectVaultImportService | None = None,
    ) -> None:
        self.registry = registry
        self.setup_service = setup_service
        self.implementation_service = implementation_service
        self.activation_service = activation_service
        self.audit = audit
        self.profile_cleanup_service = (
            profile_cleanup_service or ProfileCleanupService()
        )
        self.project_vault_service = project_vault_service
        self.managed_junction_service = managed_junction_service
        self.project_vault_import_service = (
            project_vault_import_service
            or (
                ProjectVaultImportService(project_vault_service)
                if project_vault_service is not None
                else None
            )
        )

    def initialize_project_vault(self) -> Path:
        project_vault, managed_junctions = self._project_vault_services()
        try:
            root = project_vault.initialize()
            managed_junctions.initialize()
        except Exception as error:
            self.audit.record(
                event="project_vault.initialize",
                result="failed",
                details={"error": str(error)},
            )
            raise
        self.audit.record(
            event="project_vault.initialize",
            result="success",
            details={
                "vaultRoot": str(root),
                "librariesPath": str(managed_junctions.libraries_path),
            },
        )
        return root

    def project_vault_inventory(self) -> VaultInventory:
        project_vault, _managed_junctions = self._project_vault_services()
        return project_vault.scan()

    def project_vault_locations(self) -> tuple[Path, Path]:
        project_vault, managed_junctions = self._project_vault_services()
        return project_vault.root, managed_junctions.libraries_path

    def project_vault_link_plan(self, revision: ProjectRevision) -> JunctionPlan:
        _project_vault, managed_junctions = self._project_vault_services()
        return managed_junctions.plan(revision)

    def project_vault_active_links(self) -> tuple[ActiveProjectLink, ...]:
        _project_vault, managed_junctions = self._project_vault_services()
        return managed_junctions.active_links()

    def plan_project_vault_import(
        self,
        request: ProjectVaultImportRequest,
    ) -> ProjectVaultImportPlan:
        importer = self._project_vault_importer()
        return importer.plan(request)

    def import_project_vault_revision(
        self,
        plan: ProjectVaultImportPlan,
    ) -> ProjectVaultImportResult:
        importer = self._project_vault_importer()
        try:
            result = importer.execute(plan)
        except Exception as error:
            self.audit.record(
                event="project_vault.revision.import",
                result="failed",
                details={
                    "sourcePath": str(plan.source_path),
                    "revisionPath": str(plan.revision_path),
                    "libraryName": plan.request.library_name,
                    "error": str(error),
                },
            )
            raise
        self.audit.record(
            event="project_vault.revision.import",
            result="success",
            details={
                "sourcePath": str(result.source_path),
                "revisionPath": str(result.revision.revision_path),
                "libraryName": result.revision.library_name,
                "fileCount": result.file_count,
                "totalBytes": result.total_bytes,
                "sourcePreserved": True,
                "immutable": True,
            },
        )
        return result

    def activate_project_vault_revision(
        self, revision: ProjectRevision
    ) -> JunctionResult:
        _project_vault, managed_junctions = self._project_vault_services()
        try:
            result = managed_junctions.activate(revision)
        except Exception as error:
            self.audit.record(
                event="project_vault.link.activate",
                result="failed",
                details={
                    "libraryName": revision.library_name,
                    "targetPath": str(revision.library_path),
                    "error": str(error),
                },
            )
            raise
        self.audit.record(
            event="project_vault.link.activate",
            result="success",
            details={
                "action": result.action,
                "libraryName": result.library_name,
                "linkPath": str(result.link_path),
                "targetPath": str(result.target_path),
                "previousLibraryName": result.previous_library_name,
                "linkedAt": result.linked_at,
                "singleActive": True,
            },
        )
        return result

    def deactivate_project_vault_library(
        self, library_name: str
    ) -> JunctionResult:
        _project_vault, managed_junctions = self._project_vault_services()
        try:
            result = managed_junctions.deactivate(library_name)
        except Exception as error:
            self.audit.record(
                event="project_vault.link.deactivate",
                result="failed",
                details={"libraryName": library_name, "error": str(error)},
            )
            raise
        self.audit.record(
            event="project_vault.link.deactivate",
            result="success",
            details={
                "action": result.action,
                "libraryName": result.library_name,
                "linkPath": str(result.link_path),
                "targetPath": str(result.target_path),
                "targetPreserved": True,
            },
        )
        return result

    def open_project_vault_folder(self) -> Path:
        project_vault, _managed_junctions = self._project_vault_services()
        if not project_vault.root.is_dir():
            raise ProjectVaultError(
                "Initialize FAH Project Vault before opening its folder."
            )
        self.setup_service.open_folder(project_vault.root)
        return project_vault.root

    def _project_vault_services(
        self,
    ) -> tuple[ProjectVaultService, ManagedJunctionService]:
        if (
            self.project_vault_service is None
            or self.managed_junction_service is None
        ):
            raise ProjectVaultError("FAH Project Vault is not configured.")
        return self.project_vault_service, self.managed_junction_service

    def _project_vault_importer(self) -> ProjectVaultImportService:
        if self.project_vault_import_service is None:
            raise ProjectVaultError("FAH Project Vault import is not configured.")
        return self.project_vault_import_service

    def create_client(self, name: str) -> str:
        client_id = self.registry.create_client(name)
        self.audit.record(event="client.create", result="success", details={"id": client_id})
        return client_id

    def rename_client(self, client_id: str, name: str) -> None:
        self.registry.rename_client(client_id, name)
        self.audit.record(event="client.rename", result="success", details={"id": client_id})

    def create_project(self, client_id: str, name: str) -> str:
        project_id = self.registry.create_project(client_id, name)
        self.audit.record(
            event="project.create",
            result="success",
            details={"id": project_id, "clientId": client_id},
        )
        return project_id

    def rename_project(self, client_id: str, project_id: str, name: str) -> None:
        self.registry.rename_project(client_id, project_id, name)
        self.audit.record(
            event="project.rename",
            result="success",
            details={"id": project_id, "clientId": client_id},
        )

    def create_setup(
        self,
        client_id: str,
        project_id: str,
        name: str,
        parent_folder: str | Path,
    ) -> str:
        path = self.setup_service.create_setup_folder(parent_folder, name)
        setup_id = self.registry.create_setup(client_id, project_id, name, path)
        self.audit.record(
            event="setup.create",
            result="success",
            setup_id=setup_id,
            setup_path=str(path),
        )
        return setup_id

    def link_setup(
        self,
        client_id: str,
        project_id: str,
        name: str,
        folder: str | Path,
    ) -> str:
        path = self.setup_service.link_setup_folder(folder)
        setup_id = self.registry.create_setup(client_id, project_id, name, path)
        self.audit.record(
            event="setup.link",
            result="success",
            setup_id=setup_id,
            setup_path=str(path),
        )
        return setup_id

    def rename_setup(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
        name: str,
    ) -> None:
        self.registry.rename_setup(client_id, project_id, setup_id, name)
        setup = self.registry.find_setup(setup_id)
        self.audit.record(
            event="setup.rename",
            result="success",
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={
                "clientId": client_id,
                "projectId": project_id,
                "name": setup["name"],
            },
        )

    def remove_setup(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
    ) -> Path:
        removed = self.registry.remove_setup(client_id, project_id, setup_id)
        preserved_path = Path(removed["folderPath"])
        self.audit.record(
            event="setup.remove",
            result="success",
            setup_id=setup_id,
            setup_path=str(preserved_path),
            details={
                "clientId": client_id,
                "projectId": project_id,
                "name": removed["name"],
                "folderPreserved": True,
            },
        )
        return preserved_path

    def plan_profile_cleanup(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
        action: str,
    ) -> ProfileCleanupPlan:
        setup = self._setup_in_context(client_id, project_id, setup_id)
        snapshot = self.registry.snapshot()
        registered_paths = self._registered_setup_paths(snapshot)
        try:
            plan = self.profile_cleanup_service.preview(
                client_id=client_id,
                project_id=project_id,
                setup_id=setup_id,
                setup_name=setup["name"],
                setup_path=setup["folderPath"],
                action=action,
                active_setup_id=snapshot.get("activeSetupId"),
                visuino_running=self.activation_service.running_check(),
                registered_setup_paths=registered_paths,
            )
        except Exception as error:
            self.audit.record(
                event="setup.cleanup.preview",
                result="failed",
                setup_id=setup_id,
                setup_path=setup["folderPath"],
                details={
                    "action": action,
                    "clientId": client_id,
                    "projectId": project_id,
                    "error": str(error),
                },
            )
            raise
        self.audit.record(
            event="setup.cleanup.preview",
            result="success",
            setup_id=setup_id,
            setup_path=str(plan.setup_path),
            details={
                "action": action,
                "clientId": client_id,
                "projectId": project_id,
                "files": plan.inventory.file_count,
                "folders": plan.inventory.folder_count,
                "bytes": plan.inventory.total_bytes,
                "safetyGates": "passed",
            },
        )
        return plan

    def execute_profile_cleanup(
        self,
        plan: ProfileCleanupPlan,
        confirmation: str,
    ) -> ProfileCleanupResult:
        setup = self._setup_in_context(
            plan.client_id,
            plan.project_id,
            plan.setup_id,
        )
        snapshot = self.registry.snapshot()
        event = (
            "setup.cleanup.clear"
            if plan.action == CLEAR_CONTENTS
            else "setup.cleanup.delete_with_folder"
        )
        try:
            result = self.profile_cleanup_service.execute(
                plan,
                confirmation=confirmation,
                setup_name=setup["name"],
                setup_path=setup["folderPath"],
                active_setup_id=snapshot.get("activeSetupId"),
                visuino_running=self.activation_service.running_check(),
                registered_setup_paths=self._registered_setup_paths(snapshot),
            )
        except Exception as error:
            self.audit.record(
                event=event,
                result="failed",
                setup_id=plan.setup_id,
                setup_path=str(plan.setup_path),
                details={
                    **self._cleanup_details(plan),
                    "error": str(error),
                    "rollbackAttempted": bool(
                        getattr(error, "rollback_attempted", False)
                    ),
                    "rollbackSucceeded": bool(
                        getattr(error, "rollback_succeeded", False)
                    ),
                    "rollbackError": getattr(error, "rollback_error", None),
                },
            )
            if getattr(error, "rollback_attempted", False):
                self.audit.record(
                    event="setup.cleanup.rollback",
                    result=(
                        "success"
                        if getattr(error, "rollback_succeeded", False)
                        else "failed"
                    ),
                    setup_id=plan.setup_id,
                    setup_path=str(plan.setup_path),
                    details={
                        **self._cleanup_details(plan),
                        "error": getattr(error, "rollback_error", None),
                    },
                )
            raise

        try:
            if result.profile_removed:
                self.registry.remove_setup(
                    plan.client_id,
                    plan.project_id,
                    plan.setup_id,
                )
            else:
                self.registry.reset_setup_content_state(plan.setup_id)
        except Exception as error:
            self.audit.record(
                event=event,
                result="registry_update_failed",
                setup_id=plan.setup_id,
                setup_path=str(plan.setup_path),
                details={
                    **self._cleanup_details(plan),
                    "filesystemCompleted": True,
                    "error": str(error),
                },
            )
            raise ProfileCleanupError(
                "The folder operation completed, but the profile registry could "
                "not be updated. The folder remains recoverable in the Windows "
                "Recycle Bin and the previous registry copy was preserved."
            ) from error

        self.audit.record(
            event=event,
            result="success",
            setup_id=plan.setup_id,
            setup_path=str(result.setup_path),
            details={
                **self._cleanup_details(plan),
                "profileRemoved": result.profile_removed,
                "recycleBin": True,
            },
        )
        return result

    def _setup_in_context(
        self,
        client_id: str,
        project_id: str,
        setup_id: str,
    ) -> dict[str, Any]:
        project = self.registry.find_project(client_id, project_id)
        setup = next(
            (item for item in project["setups"] if item["id"] == setup_id),
            None,
        )
        if setup is None:
            raise ProfileCleanupError(
                "Nothing changed. The selected profile no longer exists in "
                "this client and project."
            )
        return setup

    @staticmethod
    def _registered_setup_paths(
        snapshot: dict[str, Any],
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            (setup["id"], setup["folderPath"])
            for client in snapshot["clients"]
            for project in client["projects"]
            for setup in project["setups"]
        )

    @staticmethod
    def _cleanup_details(plan: ProfileCleanupPlan) -> dict[str, Any]:
        return {
            "action": plan.action,
            "clientId": plan.client_id,
            "projectId": plan.project_id,
            "name": plan.setup_name,
            "files": plan.inventory.file_count,
            "folders": plan.inventory.folder_count,
            "bytes": plan.inventory.total_bytes,
            "safetyGates": "passed",
        }

    def validate_setup(self, setup_id: str) -> ValidationResult:
        setup = self.registry.find_setup(setup_id)
        result = self.setup_service.validate(setup["folderPath"])
        self.registry.update_validation(
            setup_id,
            status=result.status,
            checked_at=result.checked_at,
            warnings=list(result.warnings),
        )
        self.audit.record(
            event="setup.validate",
            result=result.status,
            setup_id=setup_id,
            setup_path=str(result.setup_path),
            details={
                "librariesPath": str(result.libraries_path),
                "librariesCreated": result.libraries_created,
                "legacyEntriesCopied": list(result.legacy_entries_copied),
                "mitovPresent": result.mitov_present,
                "visuinoProPresent": result.visuino_pro_present,
                "warnings": list(result.warnings),
            },
        )
        return result

    def find_default_baseline_source(self, setup_id: str) -> Path | None:
        setup = self.registry.find_setup(setup_id)
        setup_path = Path(setup["folderPath"]).resolve(strict=False)
        libraries_path = self.setup_service.libraries_path(setup_path)
        mitov_missing = not (libraries_path / "Mitov").is_dir()
        visuino_pro_missing = not (libraries_path / "VisuinoPro").is_dir()
        if not mitov_missing and not visuino_pro_missing:
            return None
        for candidate in self.activation_service.default_library_candidates():
            try:
                source = self.setup_service.normalize_baseline_source(candidate)
            except (OSError, ValueError):
                continue
            if source == libraries_path:
                continue
            if mitov_missing and (source / "Mitov").is_dir():
                return source
            if (
                not mitov_missing
                and visuino_pro_missing
                and (source / "VisuinoPro").is_dir()
            ):
                return source
        return None

    def plan_baseline_repair(
        self,
        setup_id: str,
        source_path: str | Path,
    ) -> BaselineRepairPlan:
        setup = self.registry.find_setup(setup_id)
        try:
            plan = self.setup_service.plan_baseline_repair(
                setup_id,
                setup["folderPath"],
                source_path,
            )
        except Exception as error:
            self.audit.record(
                event="setup.baseline.plan",
                result="failed",
                setup_id=setup_id,
                setup_path=setup["folderPath"],
                details={"sourcePath": str(source_path), "error": str(error)},
            )
            raise
        self.audit.record(
            event="setup.baseline.plan",
            result="success",
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={
                "sourcePath": str(plan.source_path),
                "copy": [item.name for item in plan.copies],
                "retained": list(plan.retained),
                "unavailable": list(plan.unavailable),
                "files": plan.file_count,
                "bytes": plan.total_bytes,
            },
        )
        return plan

    def repair_setup_baseline(
        self, plan: BaselineRepairPlan
    ) -> BaselineRepairResult:
        setup = self.registry.find_setup(plan.setup_id)
        try:
            active_setup_id = self.registry_snapshot().get("activeSetupId")
            if (
                active_setup_id == plan.setup_id
                and self.activation_service.running_check()
            ):
                raise BaselineRepairError(
                    "Close Visuino before repairing the currently active setup."
                )
            result = self.setup_service.repair_baseline(plan)
        except Exception as error:
            self.audit.record(
                event="setup.baseline.repair",
                result="failed",
                setup_id=plan.setup_id,
                setup_path=setup["folderPath"],
                details={
                    "sourcePath": str(plan.source_path),
                    "copy": [item.name for item in plan.copies],
                    "error": str(error),
                },
            )
            raise
        self.audit.record(
            event="setup.baseline.repair",
            result="success",
            setup_id=plan.setup_id,
            setup_path=str(result.setup_path),
            details={
                "sourcePath": str(result.source_path),
                "copied": list(result.copied),
                "files": result.file_count,
                "bytes": result.total_bytes,
            },
        )
        return result

    def plan_implementation_import(
        self,
        setup_id: str,
        source_path: str | Path,
        library_name: str = DEFAULT_LIBRARY_NAME,
    ) -> ImportPlan:
        setup = self.registry.find_setup(setup_id)
        libraries_path = self.setup_service.libraries_path(
            setup["folderPath"]
        )
        try:
            plan = self.implementation_service.plan_import(
                setup_id,
                libraries_path,
                source_path,
                library_name,
            )
        except Exception as error:
            self.audit.record(
                event="implementation.plan",
                result="failed",
                setup_id=setup_id,
                setup_path=setup["folderPath"],
                details={"sourcePath": str(source_path), "error": str(error)},
            )
            raise
        self.audit.record(
            event="implementation.plan",
            result="success",
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={
                "sourcePath": str(plan.source_path),
                "mode": plan.mode,
                "libraryName": plan.library_name,
                "files": len(plan.files),
                "add": plan.add_count,
                "replace": plan.replace_count,
                "unchanged": plan.unchanged_count,
                "warnings": list(plan.warnings),
            },
        )
        return plan

    def install_implementation(self, plan: ImportPlan) -> ImportResult:
        setup = self.registry.find_setup(plan.setup_id)
        try:
            if self.activation_service.running_check():
                raise ImplementationError(
                    "Close Visuino Pro before installing a standalone implementation."
                )
            result = self.implementation_service.install(plan)
        except Exception as error:
            self.audit.record(
                event="implementation.install",
                result="failed",
                setup_id=plan.setup_id,
                setup_path=setup["folderPath"],
                details={
                    "sourcePath": str(plan.source_path),
                    "libraryName": plan.library_name,
                    "error": str(error),
                },
            )
            raise
        self.registry.set_device_package(
            plan.setup_id,
            self._device_package_record(
                package_id="external_standalone",
                result_status="valid",
                library_name=result.library_name,
                manifest_path=result.manifest_path,
                setup_path=Path(setup["folderPath"]),
                source_path=result.source_path,
                imported_at=result.imported_at,
                warnings=list(result.warnings),
            ),
        )
        self.audit.record(
            event="implementation.install",
            result="success",
            setup_id=plan.setup_id,
            setup_path=str(result.setup_path),
            details={
                "sourcePath": str(result.source_path),
                "mode": result.mode,
                "libraryName": result.library_name,
                "manifestPath": str(result.manifest_path),
                "sketchPath": str(result.sketch_path),
                "backupPath": str(result.backup_path),
                "files": result.file_count,
                "warnings": list(result.warnings),
            },
        )
        return result

    def validate_implementation(self, setup_id: str) -> ImplementationValidation:
        setup = self.registry.find_setup(setup_id)
        package = setup.get("devicePackage")
        library_name = package.get("libraryFolder") if package else None
        result = self.implementation_service.validate(
            self.setup_service.libraries_path(setup["folderPath"]),
            library_name,
        )
        if package:
            updated = dict(package)
            updated["status"] = result.status
            updated["warnings"] = list(result.warnings)
            self.registry.set_device_package(setup_id, updated)
        self.audit.record(
            event="implementation.validate",
            result=result.status,
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={
                "libraryName": library_name,
                "manifestPath": (
                    str(result.manifest_path) if result.manifest_path else None
                ),
                "checkedFiles": result.checked_files,
                "warnings": list(result.warnings),
            },
        )
        return result

    def load_custom_code_hooks(
        self,
        setup_id: str,
        library_name: str | None = None,
    ) -> CustomCodeHooks:
        setup = self.registry.find_setup(setup_id)
        package = setup.get("devicePackage")
        selected_library = (
            library_name
            or (package.get("libraryFolder") if package else None)
            or DEFAULT_LIBRARY_NAME
        )
        return self.implementation_service.load_hooks(
            self.setup_service.libraries_path(setup["folderPath"]),
            selected_library,
        )

    def save_custom_code_hooks(
        self,
        setup_id: str,
        library_name: str,
        hooks: CustomCodeHooks,
    ) -> Path:
        setup = self.registry.find_setup(setup_id)
        path = self.implementation_service.save_hooks(
            self.setup_service.libraries_path(setup["folderPath"]),
            library_name,
            hooks,
        )
        package = setup.get("devicePackage")
        if package is None:
            manifest_path = (
                Path(setup["folderPath"])
                / "libraries"
                / library_name
                / "extras"
                / "device-package.json"
            )
            package = self._device_package_record(
                package_id="manual_custom_code",
                result_status="valid",
                library_name=library_name,
                manifest_path=manifest_path,
                setup_path=Path(setup["folderPath"]),
                source_path=Path("manual"),
                imported_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                warnings=[],
            )
            self.registry.set_device_package(setup_id, package)
        self.audit.record(
            event="custom_code.save",
            result="success",
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={"libraryName": library_name, "hooksPath": str(path)},
        )
        return path

    def load_visuino_arduino_code(
        self,
        setup_id: str,
        library_name: str | None = None,
    ) -> str:
        setup = self.registry.find_setup(setup_id)
        package = setup.get("devicePackage")
        selected_library = (
            library_name
            or (package.get("libraryFolder") if package else None)
            or DEFAULT_LIBRARY_NAME
        )
        return self.implementation_service.load_visuino_sketch(
            self.setup_service.libraries_path(setup["folderPath"]),
            selected_library,
        )

    def load_ui_element_variables(
        self,
        setup_id: str,
        library_name: str | None = None,
    ) -> tuple[UiElementVariable, ...]:
        setup = self.registry.find_setup(setup_id)
        package = setup.get("devicePackage")
        selected_library = (
            library_name
            or (package.get("libraryFolder") if package else None)
            or DEFAULT_LIBRARY_NAME
        )
        return self.implementation_service.load_ui_elements(
            self.setup_service.libraries_path(setup["folderPath"]),
            selected_library,
        )

    def save_visuino_arduino_code(
        self,
        setup_id: str,
        library_name: str,
        sketch: str,
    ) -> Path:
        setup = self.registry.find_setup(setup_id)
        path = self.implementation_service.save_visuino_sketch(
            self.setup_service.libraries_path(setup["folderPath"]),
            library_name,
            sketch,
        )
        package = setup.get("devicePackage")
        if package is None:
            manifest_path = (
                Path(setup["folderPath"])
                / "libraries"
                / library_name
                / "extras"
                / "device-package.json"
            )
            package = self._device_package_record(
                package_id="manual_arduino_sketch",
                result_status="valid",
                library_name=library_name,
                manifest_path=manifest_path,
                setup_path=Path(setup["folderPath"]),
                source_path=Path("manual"),
                imported_at=datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                warnings=[],
            )
            self.registry.set_device_package(setup_id, package)
        self.audit.record(
            event="custom_code.ino.save",
            result="success",
            setup_id=setup_id,
            setup_path=setup["folderPath"],
            details={"libraryName": library_name, "sketchPath": str(path)},
        )
        return path

    @staticmethod
    def _device_package_record(
        *,
        package_id: str,
        result_status: str,
        library_name: str,
        manifest_path: Path,
        setup_path: Path,
        source_path: Path,
        imported_at: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "id": package_id,
            "revision": "1",
            "libraryFolder": library_name,
            "manifestPath": str(manifest_path.relative_to(setup_path)),
            "sourcePath": str(source_path),
            "status": result_status,
            "lastImportedAt": imported_at,
            "warnings": warnings,
        }

    def activate_setup(self, setup_id: str) -> ActivationResult:
        setup = self.registry.find_setup(setup_id)
        try:
            result = self.activation_service.activate(setup_id, setup["folderPath"])
        except Exception as error:
            self.audit.record(
                event="setup.activate",
                result="failed",
                setup_id=setup_id,
                setup_path=setup["folderPath"],
                details={"error": str(error)},
            )
            raise
        self.registry.set_active_setup(setup_id)
        self.audit.record(
            event="setup.activate",
            result="success",
            setup_id=setup_id,
            setup_path=str(result.setup_path),
            details={
                "cachePath": str(result.cache_path),
                "backupPath": str(result.backup_path),
                "processId": result.process_id,
            },
        )
        return result

    def restore_default(self) -> RestoreResult:
        try:
            result = self.activation_service.restore_default()
        except Exception as error:
            self.audit.record(
                event="setup.restore_default",
                result="failed",
                details={"error": str(error)},
            )
            raise
        self.registry.set_active_setup(None)
        self.audit.record(
            event="setup.restore_default",
            result="success",
            details={
                "backupPath": str(result.backup_path),
                "processId": result.process_id,
                "restoredRegistryPath": result.restored_registry_path,
            },
        )
        return result

    def registry_snapshot(self) -> dict[str, Any]:
        return self.registry.snapshot()

    @staticmethod
    def validation_details(result: ValidationResult) -> dict[str, Any]:
        return asdict(result)
