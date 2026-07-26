from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from lvgl_visuino_setup_manager.project_vault import (
    ManagedJunctionService,
    ProjectVaultService,
)
from lvgl_visuino_setup_manager.project_vault_import import (
    ProjectVaultImportRequest,
    ProjectVaultImportService,
)


DEFAULT_ARDUINO_CLI = Path(
    r"C:\Program Files (x86)\Mitov\Visuino Pro\ArduinoCLI\arduino-cli.exe"
)
DEFAULT_FQBN = (
    "esp32:esp32:esp32s3:"
    "USBMode=hwcdc,CDCOnBoot=cdc,CPUFreq=240,FlashMode=qio,"
    "FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi,"
    "LoopCore=1,EventsCore=1"
)


def prove(source: Path, cli: Path, fqbn: str) -> None:
    source = source.resolve(strict=True)
    cli = cli.resolve(strict=True)
    arduino_data = (
        Path.home() / "AppData" / "Local" / "Arduino15"
    ).resolve(strict=True)

    with tempfile.TemporaryDirectory(
        prefix="fah-waveshare-vault-proof-"
    ) as temporary:
        root = Path(temporary)
        sketchbook = root / "Arduino"
        vault = ProjectVaultService(sketchbook / "FAH LVGL")
        importer = ProjectVaultImportService(vault)
        request = ProjectVaultImportRequest(
            source_path=source,
            client_id="client_fah",
            client_name="FAH",
            project_id="project_waveshare43b_demo",
            project_name="Waveshare 4.3B Demo",
            revision_id="r001",
            library_name="FAH_Waveshare43B_Demo_r001",
        )
        result = importer.execute(importer.plan(request))
        junctions = ManagedJunctionService(
            libraries_path=sketchbook / "libraries",
            vault_root=vault.root,
            state_path=root / "state" / "project-vault-links.json",
        )
        link = junctions.activate(result.revision)
        config = root / "arduino-cli.yaml"
        config.write_text(
            "directories:\n"
            f"  data: {arduino_data.as_posix()}\n"
            f"  downloads: {(arduino_data / 'staging').as_posix()}\n"
            f"  user: {sketchbook.as_posix()}\n"
            "logging:\n"
            "  level: info\n",
            encoding="utf-8",
            newline="\n",
        )
        try:
            completed = subprocess.run(
                [
                    str(cli),
                    "compile",
                    "--config-file",
                    str(config),
                    "--fqbn",
                    fqbn,
                    "--libraries",
                    str(junctions.libraries_path),
                    "--build-path",
                    str(root / "build"),
                    str(result.revision.revision_path),
                ],
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "The isolated Waveshare project-vault compile failed."
                )
            print("PASS: imported and compiled the self-contained Waveshare revision.")
            print(f"Files: {result.file_count}")
            print(f"Bytes: {result.total_bytes}")
            print(f"Library: {result.revision.library_name}")
            print(f"Link: {link.link_path}")
            print(f"Target: {link.target_path}")
        finally:
            junctions.deactivate(result.revision.library_name)
            if not result.revision.library_path.is_dir():
                raise RuntimeError(
                    "The temporary proof removed or damaged the vault target."
                )


def main() -> int:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Import and compile the Waveshare project in an otherwise empty "
            "temporary Arduino sketchbook through a managed junction."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=workspace / "source-import" / "Waveshare-4.3B-Example",
    )
    parser.add_argument(
        "--arduino-cli",
        type=Path,
        default=DEFAULT_ARDUINO_CLI,
    )
    parser.add_argument("--fqbn", default=DEFAULT_FQBN)
    arguments = parser.parse_args()
    prove(arguments.source, arguments.arduino_cli, arguments.fqbn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
