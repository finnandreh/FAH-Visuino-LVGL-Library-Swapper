from __future__ import annotations

import ctypes
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from send2trash import send2trash


CLEAR_CONTENTS = "clear_contents"
DELETE_WITH_FOLDER = "delete_with_folder"
CLEANUP_ACTIONS = {CLEAR_CONTENTS, DELETE_WITH_FOLDER}


class ProfileCleanupError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        rollback_attempted: bool = False,
        rollback_succeeded: bool = False,
        rollback_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rollback_attempted = rollback_attempted
        self.rollback_succeeded = rollback_succeeded
        self.rollback_error = rollback_error


@dataclass(frozen=True)
class CleanupInventory:
    file_count: int
    folder_count: int
    total_bytes: int


@dataclass(frozen=True)
class ProfileCleanupPlan:
    client_id: str
    project_id: str
    setup_id: str
    setup_name: str
    setup_path: Path
    action: str
    inventory: CleanupInventory
    confirmation_phrase: str


@dataclass(frozen=True)
class ProfileCleanupResult:
    client_id: str
    project_id: str
    setup_id: str
    setup_name: str
    setup_path: Path
    action: str
    inventory: CleanupInventory
    profile_removed: bool


class ProfileCleanupService:
    def __init__(
        self,
        *,
        trash: Callable[[str], None] = send2trash,
        workspace_root: str | Path | None = None,
        application_data_root: str | Path | None = None,
        protected_paths: Iterable[str | Path] = (),
    ) -> None:
        self._trash = trash
        self._workspace_root = self._normalize_optional(workspace_root)
        self._application_data_root = self._normalize_optional(
            application_data_root
        )
        self._additional_protected = tuple(
            Path(item).expanduser().resolve(strict=False)
            for item in protected_paths
        )

    @staticmethod
    def _normalize_optional(value: str | Path | None) -> Path | None:
        if value is None:
            return None
        return Path(value).expanduser().resolve(strict=False)

    def preview(
        self,
        *,
        client_id: str,
        project_id: str,
        setup_id: str,
        setup_name: str,
        setup_path: str | Path,
        action: str,
        active_setup_id: str | None,
        visuino_running: bool,
        registered_setup_paths: Iterable[tuple[str, str | Path]],
    ) -> ProfileCleanupPlan:
        if action not in CLEANUP_ACTIONS:
            raise ProfileCleanupError(f"Unknown cleanup action: {action}")
        if setup_id == active_setup_id:
            raise ProfileCleanupError(
                "Nothing changed. Restore the default setup before changing "
                "the active profile's folder."
            )
        if visuino_running:
            raise ProfileCleanupError(
                "Nothing changed. Close Visuino Pro before clearing or "
                "recycling a setup folder."
            )

        target = self._validate_target(setup_path)
        self._validate_registered_overlap(
            target,
            setup_id,
            registered_setup_paths,
        )
        inventory = self._inventory(target)
        return ProfileCleanupPlan(
            client_id=client_id,
            project_id=project_id,
            setup_id=setup_id,
            setup_name=setup_name,
            setup_path=target,
            action=action,
            inventory=inventory,
            confirmation_phrase=f"DELETE {setup_name}",
        )

    def execute(
        self,
        plan: ProfileCleanupPlan,
        *,
        confirmation: str,
        setup_name: str,
        setup_path: str | Path,
        active_setup_id: str | None,
        visuino_running: bool,
        registered_setup_paths: Iterable[tuple[str, str | Path]],
    ) -> ProfileCleanupResult:
        if confirmation != plan.confirmation_phrase:
            raise ProfileCleanupError(
                f"Nothing changed. Type exactly: {plan.confirmation_phrase}"
            )
        if setup_name != plan.setup_name:
            raise ProfileCleanupError(
                "Nothing changed. The selected profile was renamed after the preview."
            )

        current = self.preview(
            client_id=plan.client_id,
            project_id=plan.project_id,
            setup_id=plan.setup_id,
            setup_name=setup_name,
            setup_path=setup_path,
            action=plan.action,
            active_setup_id=active_setup_id,
            visuino_running=visuino_running,
            registered_setup_paths=registered_setup_paths,
        )
        if current.setup_path != plan.setup_path:
            raise ProfileCleanupError(
                "Nothing changed. The selected folder path changed after the preview."
            )
        if current.inventory != plan.inventory:
            raise ProfileCleanupError(
                "Nothing changed. The folder contents changed after the preview. "
                "Preview the action again."
            )

        target = current.setup_path
        staged = target.parent / (
            f".lvgl-library-swapper-{plan.setup_id}-{uuid.uuid4().hex}"
        )
        if staged.exists():
            raise ProfileCleanupError(
                "Nothing changed. A unique staging folder could not be prepared."
            )

        try:
            os.replace(target, staged)
        except OSError as error:
            raise ProfileCleanupError(
                f"Nothing changed. The setup folder could not be staged: {error}"
            ) from error

        replacement_created = False
        try:
            if plan.action == CLEAR_CONTENTS:
                target.mkdir()
                (target / "libraries").mkdir()
                replacement_created = True
            self._trash(str(staged))
        except Exception as error:
            rollback_succeeded, rollback_error = self._rollback(
                target=target,
                staged=staged,
                replacement_created=replacement_created,
            )
            if rollback_succeeded:
                message = (
                    "Nothing changed. Windows could not move the selected folder "
                    "to the Recycle Bin, so the original folder was restored."
                )
            else:
                message = (
                    "The Recycle Bin operation failed and automatic restoration "
                    "could not finish. The audit log contains the exact staging path."
                )
            raise ProfileCleanupError(
                message,
                rollback_attempted=True,
                rollback_succeeded=rollback_succeeded,
                rollback_error=rollback_error or str(error),
            ) from error

        return ProfileCleanupResult(
            client_id=plan.client_id,
            project_id=plan.project_id,
            setup_id=plan.setup_id,
            setup_name=plan.setup_name,
            setup_path=target,
            action=plan.action,
            inventory=plan.inventory,
            profile_removed=plan.action == DELETE_WITH_FOLDER,
        )

    def _validate_target(self, raw_path: str | Path) -> Path:
        raw_text = os.path.expandvars(os.path.expanduser(str(raw_path).strip()))
        if not raw_text:
            raise ProfileCleanupError("Nothing changed. The setup path is empty.")
        if raw_text.startswith(("\\\\", "//")):
            raise ProfileCleanupError(
                "Nothing changed. Network and UNC folders cannot be recycled here."
            )

        candidate = Path(os.path.abspath(raw_text))
        if not candidate.exists():
            raise ProfileCleanupError(
                "Nothing changed. The selected setup folder does not exist. "
                "Use Remove Profile if only the saved profile should be removed."
            )
        if not candidate.is_dir():
            raise ProfileCleanupError(
                "Nothing changed. The selected setup path is not a folder."
            )

        self._assert_no_reparse_path_components(candidate)
        target = candidate.resolve(strict=True)
        if not target.anchor or self._same_path(target, Path(target.anchor)):
            raise ProfileCleanupError(
                "Nothing changed. A drive root cannot be used as a setup folder."
            )
        self._assert_local_drive(target)
        self._assert_not_protected(target)
        self._assert_not_reparse(target)
        return target

    def _assert_not_protected(self, target: Path) -> None:
        home = Path.home().resolve(strict=False)
        exact_roots = [
            home,
            home / "Desktop",
            home / "Documents",
            home / "Downloads",
        ]
        system_trees: list[Path] = []
        for variable in ("WINDIR", "ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(variable)
            if value:
                system_trees.append(Path(value).resolve(strict=False))

        for protected in exact_roots:
            if self._same_or_parent(target, protected):
                raise ProfileCleanupError(
                    f"Nothing changed. The selected path is protected: {target}"
                )
        for protected in system_trees:
            if self._paths_overlap(target, protected):
                raise ProfileCleanupError(
                    f"Nothing changed. The selected path is protected: {target}"
                )

        protected_trees = list(self._additional_protected)
        if self._workspace_root is not None:
            protected_trees.append(self._workspace_root)
        if self._application_data_root is not None:
            protected_trees.append(self._application_data_root)
        for protected in protected_trees:
            if self._paths_overlap(target, protected):
                raise ProfileCleanupError(
                    f"Nothing changed. The selected path overlaps protected "
                    f"application storage: {protected}"
                )

    @staticmethod
    def _assert_local_drive(target: Path) -> None:
        if os.name != "nt":
            return
        drive_root = target.anchor
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(drive_root))
        if drive_type not in (2, 3):
            raise ProfileCleanupError(
                "Nothing changed. Only a local fixed or removable drive is supported."
            )

    @classmethod
    def _assert_no_reparse_path_components(cls, target: Path) -> None:
        current = Path(target.anchor)
        for part in target.parts[1:]:
            current /= part
            if current.exists():
                cls._assert_not_reparse(current)

    @staticmethod
    def _assert_not_reparse(path: Path) -> None:
        try:
            metadata = path.lstat()
        except OSError as error:
            raise ProfileCleanupError(
                f"Nothing changed. The path could not be inspected safely: {path}"
            ) from error
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if path.is_symlink() or bool(attributes & reparse_flag):
            raise ProfileCleanupError(
                "Nothing changed. The folder contains a junction, mount point, "
                f"or symbolic link: {path}"
            )

    @classmethod
    def _inventory(cls, root: Path) -> CleanupInventory:
        file_count = 0
        folder_count = 0
        total_bytes = 0
        pending = [root]
        while pending:
            current = pending.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        entry_path = Path(entry.path)
                        cls._assert_not_reparse(entry_path)
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                folder_count += 1
                                pending.append(entry_path)
                            elif entry.is_file(follow_symlinks=False):
                                metadata = entry.stat(follow_symlinks=False)
                                file_count += 1
                                total_bytes += metadata.st_size
                            else:
                                raise ProfileCleanupError(
                                    "Nothing changed. The folder contains an "
                                    f"unsupported filesystem entry: {entry_path}"
                                )
                        except OSError as error:
                            raise ProfileCleanupError(
                                "Nothing changed. A folder entry could not be "
                                f"inspected safely: {entry_path}"
                            ) from error
            except ProfileCleanupError:
                raise
            except OSError as error:
                raise ProfileCleanupError(
                    f"Nothing changed. The folder could not be read safely: {current}"
                ) from error
        return CleanupInventory(file_count, folder_count, total_bytes)

    @classmethod
    def _validate_registered_overlap(
        cls,
        target: Path,
        setup_id: str,
        registered_setup_paths: Iterable[tuple[str, str | Path]],
    ) -> None:
        for other_id, raw_other in registered_setup_paths:
            if other_id == setup_id:
                continue
            other = Path(raw_other).expanduser().resolve(strict=False)
            if cls._paths_overlap(target, other):
                raise ProfileCleanupError(
                    "Nothing changed. The selected folder overlaps another "
                    f"registered setup: {other}"
                )

    @staticmethod
    def _path_key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    @classmethod
    def _same_path(cls, first: Path, second: Path) -> bool:
        return cls._path_key(first) == cls._path_key(second)

    @classmethod
    def _same_or_parent(cls, parent: Path, child: Path) -> bool:
        parent_key = cls._path_key(parent)
        child_key = cls._path_key(child)
        try:
            return os.path.commonpath((parent_key, child_key)) == parent_key
        except ValueError:
            return False

    @classmethod
    def _paths_overlap(cls, first: Path, second: Path) -> bool:
        return cls._same_or_parent(first, second) or cls._same_or_parent(
            second,
            first,
        )

    @staticmethod
    def _rollback(
        *,
        target: Path,
        staged: Path,
        replacement_created: bool,
    ) -> tuple[bool, str | None]:
        try:
            if replacement_created:
                libraries = target / "libraries"
                libraries.rmdir()
                target.rmdir()
            if not staged.exists():
                raise OSError(
                    "The staged folder is no longer available for restoration."
                )
            os.replace(staged, target)
            return True, None
        except OSError as error:
            return False, str(error)
