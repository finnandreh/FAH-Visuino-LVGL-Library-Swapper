from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from lvgl_visuino_setup_manager.project_vault import (
    ManagedJunctionService,
    ProjectVaultService,
)


def _write_probe(sketchbook: Path) -> Path:
    revision = (
        sketchbook
        / "FAH LVGL"
        / "Clients"
        / "client_probe"
        / "Projects"
        / "project_junction"
        / "Revisions"
        / "r001"
    )
    library_name = "FAH_Vault_Junction_Probe_r001"
    library = revision / "libraries" / library_name
    source = library / "src"
    (source / "vendor" / "lvgl").mkdir(parents=True)

    (library / "library.properties").write_text(
        "\n".join(
            (
                f"name={library_name}",
                "version=1.0.0",
                "author=FAH",
                "maintainer=FAH",
                "sentence=FAH Project Vault junction compilation probe.",
                "paragraph=Validates Arduino CLI discovery through an NTFS junction.",
                "category=Other",
                "architectures=*",
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    (source / f"{library_name}.h").write_text(
        "#pragma once\nint fah_vault_probe_value();\n",
        encoding="utf-8",
        newline="\n",
    )
    (source / f"{library_name}.cpp").write_text(
        f'#include "{library_name}.h"\n'
        "int fah_vault_probe_value() { return 43; }\n",
        encoding="utf-8",
        newline="\n",
    )
    (source / "vendor" / "lvgl" / "README.txt").write_text(
        "Vendored LVGL placeholder for the link-discovery proof.\n",
        encoding="utf-8",
        newline="\n",
    )
    (revision / "r001.ino").write_text(
        f"#include <{library_name}.h>\n"
        "void setup() { Serial.begin(115200); }\n"
        "void loop() { Serial.println(fah_vault_probe_value()); }\n",
        encoding="utf-8",
        newline="\n",
    )
    (revision / "project-meta.json").write_text(
        json.dumps({"name": "Junction Probe"}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (revision / "ui-elements.json").write_text(
        json.dumps({"elements": []}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schemaVersion": 1,
        "revision": {"id": "r001", "immutable": True},
        "client": {"id": "client_probe", "name": "Probe Client"},
        "project": {"id": "project_junction", "name": "Junction Probe"},
        "library": {
            "name": library_name,
            "relativePath": f"libraries/{library_name}",
            "selfContained": True,
            "lvgl": {"version": "probe", "storage": "vendored"},
        },
        "handoff": {
            "rootIno": "r001.ino",
            "projectMeta": "project-meta.json",
            "uiElements": "ui-elements.json",
        },
    }
    (revision / "fah-project.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return revision


def prove(cli: Path, fqbn: str) -> None:
    with tempfile.TemporaryDirectory(prefix="fah-vault-arduino-") as temporary:
        sketchbook = Path(temporary) / "Arduino"
        revision_path = _write_probe(sketchbook)
        vault = ProjectVaultService(sketchbook / "FAH LVGL")
        inventory = vault.scan()
        if inventory.issues or len(inventory.revisions) != 1:
            raise RuntimeError(
                f"Probe manifest validation failed: {inventory.issues}"
            )
        service = ManagedJunctionService(
            libraries_path=sketchbook / "libraries",
            vault_root=sketchbook / "FAH LVGL",
            state_path=Path(temporary) / "state" / "project-vault-links.json",
        )
        revision = inventory.revisions[0]
        result = service.activate(revision)
        try:
            completed = subprocess.run(
                [
                    str(cli),
                    "compile",
                    "--fqbn",
                    fqbn,
                    "--libraries",
                    str(service.libraries_path),
                    "--build-path",
                    str(Path(temporary) / "build"),
                    str(revision_path),
                ],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "Arduino CLI junction compilation failed.\n"
                    f"{completed.stdout}\n{completed.stderr}"
                )
            if not result.link_path.is_dir():
                raise RuntimeError("The project library junction disappeared.")
            print("PASS: Arduino CLI compiled a library through the managed junction.")
            print(f"FQBN: {fqbn}")
            print(f"Library: {revision.library_name}")
            print(f"Link: {result.link_path}")
            print(f"Target: {result.target_path}")
            print(completed.stdout.strip())
        finally:
            service.deactivate(revision.library_name)
            if not revision.library_path.is_dir():
                raise RuntimeError(
                    "The project target was not preserved after proof cleanup."
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile an isolated Arduino sketch through an FAH vault junction."
    )
    parser.add_argument("arduino_cli", type=Path)
    parser.add_argument("--fqbn", default="arduino:avr:uno")
    arguments = parser.parse_args()
    prove(arguments.arduino_cli.resolve(strict=True), arguments.fqbn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
