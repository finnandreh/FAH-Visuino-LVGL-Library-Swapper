# Contributing

Thank you for helping improve FAH Visuino LVGL Library Swapper.

## Before opening a change

1. Open an issue for substantial behavior, storage, activation, or hardware
   changes so the safety boundary can be agreed first.
2. Keep each device implementation in its own standalone import folder.
3. Do not overwrite the verified Waveshare 4.3B reference package.
4. Do not include customer projects, credentials, private backups, generated
   builds, or local runtime data.

## Development setup

Use Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Run the application:

```powershell
python run_gui.py
```

Run the automated suite:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

## Pull-request expectations

- Keep project files, code, and documentation in English.
- Preserve dry-run, staging, backup, verification, audit, and rollback
  controls.
- Add or update tests for behavior changes.
- Update relevant code, tests, and human-readable documentation together.
- State which checks were run and which hardware behavior was not tested.
- Preserve existing copyright, SPDX, license, and third-party notices.

Hardware compilation is necessary but does not prove electrical behavior.
Changed device or UI bridge revisions must be verified on the exact target
hardware before they are described as hardware-tested.

By submitting a contribution, you agree that it may be distributed under the
Apache License 2.0 that covers this project.
