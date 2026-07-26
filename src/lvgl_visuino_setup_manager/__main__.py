from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME
from .activation import ActivationService
from .app import MainApplication
from .audit import AuditRepository
from .controller import ApplicationController
from .implementation import ImplementationService
from .paths import AppPaths
from .profile_cleanup import ProfileCleanupService
from .project_vault import ManagedJunctionService, ProjectVaultService
from .registry import RegistryRepository, RegistryService
from .setup_service import SetupService


def build_controller(
    data_dir: str | Path | None = None,
    *,
    sketchbook_root: str | Path | None = None,
) -> ApplicationController:
    paths = AppPaths.discover(data_dir)
    paths.ensure()
    repository = RegistryRepository(paths.registry, paths.previous_registry)
    registry = RegistryService(repository)
    activation_service = ActivationService(paths)
    normal_sketchbook = _normal_sketchbook_root(sketchbook_root)
    libraries_path = normal_sketchbook / "libraries"
    vault_root = normal_sketchbook / "FAH LVGL"
    return ApplicationController(
        registry=registry,
        setup_service=SetupService(),
        implementation_service=ImplementationService(paths),
        activation_service=activation_service,
        audit=AuditRepository(paths.audit_log),
        profile_cleanup_service=ProfileCleanupService(
            workspace_root=_application_workspace_root(),
            application_data_root=paths.root,
        ),
        project_vault_service=ProjectVaultService(vault_root),
        managed_junction_service=ManagedJunctionService(
            libraries_path=libraries_path,
            vault_root=vault_root,
            state_path=paths.project_vault_links,
            previous_state_path=paths.previous_project_vault_links,
            running_check=activation_service.running_check,
        ),
    )


def _normal_sketchbook_root(override: str | Path | None = None) -> Path:
    if override is not None and str(override).strip():
        return Path(override).expanduser().resolve(strict=False)
    return (Path.home() / "Documents" / "Arduino").resolve(strict=False)


def _application_workspace_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Override the local application data directory (useful for testing).",
    )
    parser.add_argument(
        "--sketchbook",
        type=Path,
        help="Override the normal Arduino sketchbook used by FAH Project Vault.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    controller = build_controller(
        arguments.data_dir,
        sketchbook_root=arguments.sketchbook,
    )
    application = MainApplication(controller)
    application.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
