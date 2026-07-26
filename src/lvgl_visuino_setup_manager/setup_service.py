from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .paths import resolve_safe_directory


BASELINE_LIBRARY_NAMES = ("Mitov", "VisuinoPro")
REQUIRED_BASELINE_LIBRARY = "Mitov"
LIBRARIES_DIRECTORY_NAME = "libraries"
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class ValidationResult:
    status: str
    setup_path: Path
    libraries_path: Path
    exists: bool
    mitov_present: bool
    visuino_pro_present: bool
    libraries_created: bool
    legacy_entries_copied: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_at: str

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


class BaselineRepairError(RuntimeError):
    """Raised when a missing-only baseline copy cannot complete safely."""


class SetupLayoutError(RuntimeError):
    """Raised when the Arduino sketchbook/libraries layout is unsafe."""


@dataclass(frozen=True)
class SetupLayoutResult:
    setup_path: Path
    libraries_path: Path
    libraries_created: bool
    legacy_entries_copied: tuple[str, ...]


@dataclass(frozen=True)
class BaselineCopy:
    name: str
    source: Path
    destination: Path
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class BaselineRepairPlan:
    setup_id: str
    setup_path: Path
    source_path: Path
    copies: tuple[BaselineCopy, ...]
    retained: tuple[str, ...]
    unavailable: tuple[str, ...]

    @property
    def file_count(self) -> int:
        return sum(item.file_count for item in self.copies)

    @property
    def total_bytes(self) -> int:
        return sum(item.total_bytes for item in self.copies)

    @property
    def required_available(self) -> bool:
        return (
            REQUIRED_BASELINE_LIBRARY in self.retained
            or any(
                item.name == REQUIRED_BASELINE_LIBRARY for item in self.copies
            )
        )


@dataclass(frozen=True)
class BaselineRepairResult:
    setup_id: str
    setup_path: Path
    source_path: Path
    copied: tuple[str, ...]
    file_count: int
    total_bytes: int


class SetupService:
    def ensure_layout(self, raw_path: str | Path) -> SetupLayoutResult:
        setup = resolve_safe_directory(raw_path, must_exist=True)
        libraries = (setup / LIBRARIES_DIRECTORY_NAME).resolve(strict=False)
        if libraries.exists() and (
            not libraries.is_dir() or libraries.is_symlink()
        ):
            raise SetupLayoutError(
                f"The setup libraries path must be a normal folder: {libraries}"
            )

        legacy_entries = self._legacy_library_entries(setup)
        if (
            setup.name.casefold() == LIBRARIES_DIRECTORY_NAME
            and legacy_entries
            and not libraries.exists()
        ):
            raise SetupLayoutError(
                "The selected setup folder is already an Arduino libraries "
                "directory. Link its parent sketchbook folder instead."
            )

        missing_entries = tuple(
            entry
            for entry in legacy_entries
            if not (libraries / entry.name).exists()
        )
        if libraries.is_dir() and not missing_entries:
            return SetupLayoutResult(
                setup_path=setup,
                libraries_path=libraries,
                libraries_created=False,
                legacy_entries_copied=(),
            )

        operation = uuid.uuid4().hex
        stage = setup / f".lvgl-visuino-layout-staging-{operation}"
        staged_libraries = stage / LIBRARIES_DIRECTORY_NAME
        installed: list[Path] = []
        libraries_created = not libraries.exists()
        stage.mkdir(parents=False, exist_ok=False)
        staged_libraries.mkdir()
        try:
            for source in missing_entries:
                staged = staged_libraries / source.name
                if source.is_dir():
                    shutil.copytree(source, staged, copy_function=shutil.copy2)
                    if self._tree_stats(source) != self._tree_stats(staged):
                        raise SetupLayoutError(
                            "Legacy library file count or byte count changed "
                            f"during layout copy: {source.name}"
                        )
                else:
                    shutil.copy2(source, staged)
                    if (
                        not staged.is_file()
                        or staged.stat().st_size != source.stat().st_size
                    ):
                        raise SetupLayoutError(
                            f"Legacy setup file copy failed: {source.name}"
                        )

            if libraries_created:
                os.replace(staged_libraries, libraries)
            else:
                for source in missing_entries:
                    staged = staged_libraries / source.name
                    destination = libraries / source.name
                    if destination.exists():
                        raise SetupLayoutError(
                            "A library destination appeared during layout copy: "
                            f"{destination}"
                        )
                    os.replace(staged, destination)
                    installed.append(destination)
        except Exception:
            if libraries_created and libraries.exists():
                shutil.rmtree(libraries)
            else:
                for path in reversed(installed):
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.exists():
                        path.unlink()
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)

        return SetupLayoutResult(
            setup_path=setup,
            libraries_path=libraries,
            libraries_created=libraries_created,
            legacy_entries_copied=tuple(
                entry.name for entry in missing_entries
            ),
        )

    def validate(self, raw_path: str | Path) -> ValidationResult:
        checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            setup_path = resolve_safe_directory(raw_path, must_exist=False)
        except ValueError as error:
            fallback = Path(str(raw_path) or ".")
            return ValidationResult(
                status="invalid",
                setup_path=fallback,
                libraries_path=fallback / LIBRARIES_DIRECTORY_NAME,
                exists=False,
                mitov_present=False,
                visuino_pro_present=False,
                libraries_created=False,
                legacy_entries_copied=(),
                warnings=(str(error),),
                checked_at=checked_at,
            )

        exists = setup_path.is_dir()
        libraries_path = setup_path / LIBRARIES_DIRECTORY_NAME
        libraries_created = False
        legacy_entries_copied: tuple[str, ...] = ()
        layout_warning: str | None = None
        if exists:
            try:
                layout = self.ensure_layout(setup_path)
                libraries_path = layout.libraries_path
                libraries_created = layout.libraries_created
                legacy_entries_copied = layout.legacy_entries_copied
            except (OSError, SetupLayoutError, BaselineRepairError) as error:
                layout_warning = str(error)

        mitov_present = (
            (libraries_path / "Mitov").is_dir()
            if exists and layout_warning is None
            else False
        )
        visuino_pro_present = (
            (libraries_path / "VisuinoPro").is_dir()
            if exists and layout_warning is None
            else False
        )
        warnings: list[str] = []
        if not exists:
            warnings.append(f"Setup folder does not exist: {setup_path}")
        if layout_warning:
            warnings.append(layout_warning)
        if legacy_entries_copied:
            warnings.append(
                "Copied legacy flat-layout entries into libraries: "
                + ", ".join(legacy_entries_copied)
            )
        if exists and not mitov_present:
            warnings.append("Required Mitov folder is missing.")
        if exists and not visuino_pro_present:
            warnings.append("Optional VisuinoPro folder is not installed.")

        return ValidationResult(
            status=(
                "valid"
                if exists and layout_warning is None and mitov_present
                else "invalid"
            ),
            setup_path=setup_path,
            libraries_path=libraries_path,
            exists=exists,
            mitov_present=mitov_present,
            visuino_pro_present=visuino_pro_present,
            libraries_created=libraries_created,
            legacy_entries_copied=legacy_entries_copied,
            warnings=tuple(warnings),
            checked_at=checked_at,
        )

    def normalize_baseline_source(self, raw_path: str | Path) -> Path:
        source = resolve_safe_directory(raw_path, must_exist=True)
        nested = source / "libraries"
        if (
            not any((source / name).is_dir() for name in BASELINE_LIBRARY_NAMES)
            and nested.is_dir()
            and any((nested / name).is_dir() for name in BASELINE_LIBRARY_NAMES)
        ):
            return nested.resolve()
        return source

    def plan_baseline_repair(
        self,
        setup_id: str,
        raw_setup_path: str | Path,
        raw_source_path: str | Path,
    ) -> BaselineRepairPlan:
        setup = resolve_safe_directory(raw_setup_path, must_exist=True)
        libraries = self._require_libraries_path(setup)
        source = self.normalize_baseline_source(raw_source_path)
        if libraries == source:
            raise BaselineRepairError(
                "The baseline source cannot be the selected setup."
            )

        copies: list[BaselineCopy] = []
        retained: list[str] = []
        unavailable: list[str] = []
        for name in BASELINE_LIBRARY_NAMES:
            destination = libraries / name
            source_library = source / name
            if destination.exists():
                if destination.is_symlink():
                    raise BaselineRepairError(
                        f"Symbolic links are not allowed as baseline destinations: "
                        f"{destination}"
                    )
                if not destination.is_dir():
                    raise BaselineRepairError(
                        f"A file blocks the baseline library destination: {destination}"
                    )
                retained.append(name)
                continue
            if not source_library.is_dir():
                unavailable.append(name)
                continue
            if source_library.is_symlink():
                raise BaselineRepairError(
                    f"Symbolic links are not allowed as baseline sources: "
                    f"{source_library}"
                )
            file_count, total_bytes = self._tree_stats(source_library)
            copies.append(
                BaselineCopy(
                    name=name,
                    source=source_library.resolve(),
                    destination=destination.resolve(strict=False),
                    file_count=file_count,
                    total_bytes=total_bytes,
                )
            )

        return BaselineRepairPlan(
            setup_id=setup_id,
            setup_path=setup,
            source_path=source,
            copies=tuple(copies),
            retained=tuple(retained),
            unavailable=tuple(unavailable),
        )

    def repair_baseline(self, plan: BaselineRepairPlan) -> BaselineRepairResult:
        setup = resolve_safe_directory(plan.setup_path, must_exist=True)
        libraries = self._require_libraries_path(setup)
        source = self.normalize_baseline_source(plan.source_path)
        if setup != plan.setup_path or source != plan.source_path:
            raise BaselineRepairError(
                "Baseline repair paths changed after the dry run."
            )
        if not plan.copies:
            raise BaselineRepairError(
                "The baseline repair plan contains no missing libraries to copy."
            )
        if not plan.required_available:
            raise BaselineRepairError(
                "The selected source does not provide the required Mitov library."
            )

        operation = uuid.uuid4().hex
        stage = setup / f".lvgl-visuino-baseline-staging-{operation}"
        installed: list[BaselineCopy] = []
        stage.mkdir(parents=False, exist_ok=False)
        try:
            for item in plan.copies:
                if item.name not in BASELINE_LIBRARY_NAMES:
                    raise BaselineRepairError(
                        f"Unsupported baseline library in repair plan: {item.name}"
                    )
                if item.destination.exists():
                    raise BaselineRepairError(
                        f"Baseline destination appeared after the dry run: "
                        f"{item.destination}"
                    )
                expected = (
                    item.file_count,
                    item.total_bytes,
                )
                staged = stage / item.name
                shutil.copytree(item.source, staged, copy_function=shutil.copy2)
                staged_stats = self._tree_stats(staged)
                if staged_stats != expected:
                    raise BaselineRepairError(
                        f"Baseline file count or byte count changed during copy: "
                        f"{item.name}"
                    )

            for item in plan.copies:
                staged = stage / item.name
                if item.destination.exists():
                    raise BaselineRepairError(
                        f"Baseline destination appeared before installation: "
                        f"{item.destination}"
                    )
                os.replace(staged, item.destination)
                installed.append(item)

            for item in installed:
                if not item.destination.is_dir():
                    raise BaselineRepairError(
                        f"Installed baseline directory is missing: {item.name}"
                    )
        except Exception:
            for item in reversed(installed):
                self._remove_owned_baseline(item.destination, libraries)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)

        return BaselineRepairResult(
            setup_id=plan.setup_id,
            setup_path=setup,
            source_path=source,
            copied=tuple(item.name for item in installed),
            file_count=sum(item.file_count for item in installed),
            total_bytes=sum(item.total_bytes for item in installed),
        )

    @staticmethod
    def _tree_stats(root: Path) -> tuple[int, int]:
        file_count = 0
        total_bytes = 0
        for current, directory_names, file_names in os.walk(
            root, followlinks=False
        ):
            current_path = Path(current)
            directory_names.sort(key=str.casefold)
            file_names.sort(key=str.casefold)
            for name in directory_names:
                directory = current_path / name
                if directory.is_symlink():
                    raise BaselineRepairError(
                        f"Symbolic links are not allowed in baseline libraries: "
                        f"{directory}"
                    )
            for name in file_names:
                path = current_path / name
                if path.is_symlink():
                    raise BaselineRepairError(
                        f"Symbolic links are not allowed in baseline libraries: "
                        f"{path}"
                    )
                size = path.stat().st_size
                file_count += 1
                total_bytes += size
        return file_count, total_bytes

    @staticmethod
    def _remove_owned_baseline(path: Path, libraries: Path) -> None:
        resolved = path.resolve(strict=False)
        if (
            resolved.parent != libraries
            or resolved.name not in BASELINE_LIBRARY_NAMES
        ):
            raise BaselineRepairError(
                f"Refusing to roll back an unexpected path: {resolved}"
            )
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.exists():
            resolved.unlink()

    def create_setup_folder(self, parent: str | Path, setup_name: str) -> Path:
        parent_path = resolve_safe_directory(parent, must_exist=True)
        folder_name = self.safe_folder_name(setup_name)
        target = resolve_safe_directory(parent_path / folder_name, must_exist=False)
        if target.exists():
            raise FileExistsError(
                f"The setup folder already exists. Use Link Folder instead: {target}"
            )
        target.mkdir()
        (target / LIBRARIES_DIRECTORY_NAME).mkdir()
        return target

    def link_setup_folder(self, raw_path: str | Path) -> Path:
        return resolve_safe_directory(raw_path, must_exist=True)

    @staticmethod
    def safe_folder_name(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip())
        cleaned = cleaned.rstrip(" .")
        if not cleaned:
            raise ValueError("The setup name does not produce a valid folder name.")
        if cleaned.upper() in WINDOWS_RESERVED_NAMES:
            cleaned = f"{cleaned}_setup"
        return cleaned

    @staticmethod
    def open_folder(path: str | Path) -> None:
        resolved = resolve_safe_directory(path, must_exist=True)
        if os.name != "nt":
            raise RuntimeError("Open Folder is supported only on Windows.")
        os.startfile(str(resolved))  # type: ignore[attr-defined]

    @staticmethod
    def libraries_path(raw_setup_path: str | Path) -> Path:
        setup = resolve_safe_directory(raw_setup_path, must_exist=True)
        return (setup / LIBRARIES_DIRECTORY_NAME).resolve(strict=False)

    @classmethod
    def _require_libraries_path(cls, setup: Path) -> Path:
        libraries = (setup / LIBRARIES_DIRECTORY_NAME).resolve(strict=False)
        if not libraries.is_dir() or libraries.is_symlink():
            raise BaselineRepairError(
                "The setup libraries folder is missing or unsafe. "
                "Run Validate Setup first."
            )
        return libraries

    @staticmethod
    def _legacy_library_entries(setup: Path) -> tuple[Path, ...]:
        entries: list[Path] = []
        for child in sorted(setup.iterdir(), key=lambda item: item.name.casefold()):
            if (
                child.name.casefold() == LIBRARIES_DIRECTORY_NAME
                or child.name.startswith(".")
                or child.is_symlink()
            ):
                continue
            if child.is_file() and child.name.casefold() == "lv_conf.h":
                entries.append(child)
            elif child.is_dir() and (
                (child / "library.properties").is_file()
                or child.name in BASELINE_LIBRARY_NAMES
            ):
                entries.append(child)
        return tuple(entries)
