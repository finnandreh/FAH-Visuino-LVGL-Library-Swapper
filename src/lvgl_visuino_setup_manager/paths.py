from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIRECTORY_NAME = "LVGLVisuinoLibrarySwap"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    registry: Path
    previous_registry: Path
    project_vault_links: Path
    previous_project_vault_links: Path
    audit_log: Path
    backups: Path
    caches: Path
    staging: Path
    default_snapshot: Path

    @classmethod
    def discover(cls, override: str | Path | None = None) -> "AppPaths":
        configured = override or os.environ.get("LVGL_VISUINO_DATA_DIR")
        if configured:
            root = Path(configured).expanduser().resolve()
        else:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                root = Path(local_app_data) / APP_DIRECTORY_NAME
            else:
                root = Path.home() / "AppData" / "Local" / APP_DIRECTORY_NAME
            root = root.resolve()

        return cls(
            root=root,
            registry=root / "registry.json",
            previous_registry=root / "registry.previous.json",
            project_vault_links=root / "project-vault-links.json",
            previous_project_vault_links=root / "project-vault-links.previous.json",
            audit_log=root / "audit.jsonl",
            backups=root / "backups",
            caches=root / "cache",
            staging=root / "staging",
            default_snapshot=root / "default",
        )

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.caches.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)


def resolve_safe_directory(raw_path: str | Path, *, must_exist: bool) -> Path:
    if not str(raw_path).strip():
        raise ValueError("The setup path is empty.")

    expanded = os.path.expandvars(os.path.expanduser(str(raw_path).strip()))
    path = Path(expanded).resolve(strict=False)
    anchor = Path(path.anchor).resolve(strict=False) if path.anchor else None
    if anchor is not None and path == anchor:
        raise ValueError("A filesystem root cannot be used as a setup folder.")
    if must_exist and not path.is_dir():
        raise ValueError(f"The setup folder does not exist: {path}")
    return path
