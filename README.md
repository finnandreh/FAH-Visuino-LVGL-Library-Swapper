# FAH Visuino LVGL Library Swapper

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D4.svg)
![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)

FAH Visuino LVGL Library Swapper is a Windows desktop application for keeping
separate Arduino/LVGL library environments per client, project, and device while
using Visuino Pro. It is independently developed by Finn Andre Hotvedt and
dedicated to Visuino, created by Boian Mitov. Ron Cutts is recognized for
extensive testing and design contributions.

Version 1.0.1 provides:

- client, project, and setup profiles with stable local IDs;
- required `Mitov` and optional `VisuinoPro` baseline validation;
- missing-only baseline repair without replacing selected library versions;
- guarded Visuino Pro activation, backup, rollback, cache verification, and
  default restoration;
- recoverable profile-folder clearing and deletion through the Windows Recycle
  Bin with dry-run inventory and typed confirmation;
- standalone Arduino/LVGL import with exactly one root INO;
- a complete Visuino Custom Code editor and clipboard handoff;
- UI Element Variables with namespace-qualified Visuino Input and loop examples;
- the published LVGL Library Swapper shared GPT as the device-project entry
  point.

Arduino IDE configuration and launching are outside this application's scope.

## Project Links

- Source: <https://github.com/finnandreh/FAH-Visuino-LVGL-Library-Swapper>
- Project demonstration video: <https://youtu.be/_ASeTbyNdpU>
- Temporary Project Vault preview:
  <https://drive.google.com/file/d/1vtdX2cEZDF1dwJxyfe7s69fFFerwvH8Q/view>
- Shared LVGL Library Swapper GPT:
  <https://chatgpt.com/g/g-6a63a706c35081918edae0ce7a6096f2-lvgl-library-swapper>
- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reports: [SECURITY.md](SECURITY.md)

## Project Vault On Main

The `main` branch includes the verified permanent project-library model. The
retained version 1.0.1 release archive still predates Project Vault; selecting
the next application version and producing a new release package remain
separate release steps.

The **FAH Project Vault** view:

- keeps generated revisions below
  `<normal Arduino sketchbook>\FAH LVGL\Clients`;
- browses Client → Project → Revision manifests;
- analyzes a complete standalone project before writing and atomically imports
  one new immutable revision without changing the source folder;
- validates one uniquely named, self-contained Arduino library per immutable
  revision;
- maintains exactly zero or one verified FAH-owned NTFS project-library
  junction directly below the normal `Arduino\libraries` folder;
- switches the active Client / Project / Revision with rollback while
  preserving every permanent project target;
- always shows the active revision, activation time, link verification, and
  library name;
- blocks real-folder, foreign-link, path-escape, and ownership conflicts;
- removes only a managed junction while preserving its permanent project
  target.

Source runs default to `%USERPROFILE%\Documents\Arduino`; use
`run_gui.py --sketchbook <path>` only when the normal sketchbook is stored
elsewhere. The selected vault and Arduino link paths are always shown in the
browser before any link action.

The maintained source retains the original isolated AVR junction proof. It also
imports the real Waveshare 4.3B package as one 715-file, self-contained library
with private LVGL 8.4.0 and compiles that library in an otherwise empty
ESP32-S3 sketchbook through the same junction model. The isolated build uses
708,174 program bytes and 73,972 global-variable bytes. The permanent `r001`
revision is stored below the normal sketchbook and its managed junction is
active as `Arduino\libraries\FAH_Waveshare43B_Demo_r001`. Arduino CLI discovered
the library through that normal live path, and Visuino Pro opened the retained
FAH demo and completed a full ESP32-S3 build through that exact path in
11 minutes 10 seconds. The compile reported `SUCCESS`. Visuino also displayed
two known, accepted component-image warnings from the unrelated `Ron` and
`Ron1` global libraries. They require no Project Vault action and are not a
release gate. The FAH project library has no Visuino component definitions and
is resolved by Arduino at compile time, so the live Visuino compile is the
relevant junction proof. Migration and versioned release packaging remain
separate approval gates. See [FAH Project Vault](docs/project-vault.md).

The single-active switch is covered by focused Windows junction tests. A
simulated state-persistence failure restores the previous junction and manifest
while preserving both immutable project targets.

## Current Release

Only the current portable delivery is retained:

```text
dist-release\FAH-Waveshare43-Demo-Package-2026-07-25.zip
```

Release size: 36,115,562 bytes

SHA-256: `0F43E334746B67D900EBFDAAD8F8AF91103F4853368E3173237274AFB0CD8812`

The ZIP root contains exactly:

```text
FAH-Visuino-LVGL-Library-Swapper.exe
FAH-Waveshare43-Demo.visuino
Waveshare-4.3B-Example\
```

The EXE is a one-file Windows application and does not require Python or an
`_internal` directory. The import folder contains the complete LVGL 8.4.0
Waveshare 4.3B implementation and exactly one INO.

## First Run And Demo Import

1. Choose **Extract All** on the release ZIP.
2. Start `FAH-Visuino-LVGL-Library-Swapper.exe`.
3. Create or select a client.
4. Create or select a project under that client.
5. Create a new setup/sketchbook folder or link an existing setup.
6. Choose **Validate Setup**. Add only missing `Mitov` and optional
   `VisuinoPro` when the repair dialog offers them.
7. Open **Device & Custom Code → Standalone Import**.
8. Select the extracted `Waveshare-4.3B-Example` folder, use `Waveshare43B` as
   the implementation library name, and choose **Analyze & Import**.
9. Review the dry run, close Visuino Pro, and confirm the import.
10. Validate and activate the setup.
11. Open `FAH-Waveshare43-Demo.visuino` in Visuino.

The complete root INO is also available under **Visuino Custom Code** for the
Visuino Arduino Code Import/Parser.

## Working UI Bridge

Keep the complete `waveshare43_example::` namespace prefix.

The Custom Code loop sends the touchscreen slider and retained pause state to
Visuino:

```cpp
waveshare43_example::loop();

if (waveshare43_example::take_test_slider_change()) {
  Integer1.Send(waveshare43_example::get_test_slider_value());
}

if (waveshare43_example::take_pause_state_change()) {
  Digital1.Send(waveshare43_example::get_pause_state());
}
```

Connect the Visuino sine-generator output to one Custom Code Integer Input:

```cpp
waveshare43_example::set_sine_gauge_value(AValue);
```

That single setter clamps the value to 0–100 and updates the gauge needle,
percentage label, and stored readback value together. Do not create a second
input for the percentage label.

Use amplitude `50` and offset `50` for a 0–100 Sine Integer Generator output.
A pause value of `true` means paused. Invert it when wiring to an `Enabled`
input.

See [Visuino UI Control Contract](docs/visuino-ui-control-contract.md) for the
complete API.

## Setup And Activation Contract

Each registered setup is an Arduino sketchbook root:

```text
<setup>\
  libraries\
    Mitov\
    VisuinoPro\       # optional
    lvgl\
    <device libraries>
```

Activation writes:

```text
Visuino Pro ArduinoLibraryPath = <setup>\libraries\
Arduino15 arduino-cli.yaml directories.user = <setup>
```

Visuino starts with:

```text
VisuinoPro.exe -CACHE<setup-cache> -REBUILD_CACHE
```

The current cache verifier has a fixed 180-second limit. A large first rebuild
can occasionally finish just after that limit even though Visuino started with
the correct cache arguments. If this occurs, let Visuino close or close it,
then retry activation. A future maintenance release should replace the fixed
deadline with progress-aware waiting.

## Local Application Data

Runtime data is stored outside this source folder under:

```text
%LOCALAPPDATA%\LVGLVisuinoLibrarySwap\
```

Important paths:

- `registry.json`: client/project/setup hierarchy;
- `registry.previous.json`: previous valid registry;
- `audit.jsonl`: operation history;
- `backups\`: configuration and implementation restore points;
- `cache\<setup-id>\`: setup-specific Visuino component cache;
- `default\`: recorded default Visuino configuration.

## Future Device Imports

Use **Device & Custom Code → Shared GPT** to open the published LVGL Library
Swapper assistant:

`https://chatgpt.com/g/g-6a63a706c35081918edae0ce7a6096f2-lvgl-library-swapper`

The current owner-maintained GPT Knowledge release is `2026-07-25.1`. Its
upload-ready file is
`gpt-knowledge\lvgl-library-swapper-gpt-prompt.md`; regenerate it with
`py -3.12 scripts\export_gpt_knowledge.py` after changing
`meta_prompt.py`.

Every new device project must be a separate top-level folder containing:

- exactly one root `.ino`;
- complete device-specific libraries below `libraries\`;
- project sources, UI sources, assets, and configuration;
- `project-meta.json`;
- `ui-elements.json` with stable LVGL objects, value direction, types, ranges,
  bridge namespace, and copy-ready Visuino examples;
- an English README with exact board settings and import instructions.

Do not overwrite `source-import\Waveshare-4.3B-Example`; use it as the verified
reference.

## Build And Test

Python 3.12 or newer is required for source development.

Run from source:

```powershell
python run_gui.py
```

Run the test suite:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

Build the one-file Windows executable:

```powershell
.\build_standalone.ps1
```

PyInstaller build and distribution folders are generated artifacts. Validate a
new EXE and release ZIP, retain only the final ZIP under `dist-release`, and
remove intermediate build folders afterward.

## Version Control

The maintained source tree uses branch `main`. The public repository is:

<https://github.com/finnandreh/FAH-Visuino-LVGL-Library-Swapper>

Generated builds, caches, runtime data, local environment files, and
documentation snapshots are excluded by `.gitignore`. The single verified ZIP
under `dist-release` is intentionally tracked with the source baseline.

## Open-Source License

Original project code and documentation are available under the
[Apache License 2.0](LICENSE). Copyright remains with Finn Andre Hotvedt.

Bundled LVGL, Espressif, Python, and build components retain their original
licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the license
files preserved in the vendored component directories.

Product and project names such as Visuino, Arduino, LVGL, Espressif, and
Waveshare belong to their respective owners. Compatibility statements do not
imply endorsement.

## Current Project Map

- `src\lvgl_visuino_setup_manager\`: application source.
- `tests\`: automated verification.
- `source-import\Waveshare-4.3B-Example\`: current reference import.
- `docs\system-spec.md`: current system contract.
- `docs\project-vault.md`: Project Vault behavior and safety contract.
- `docs\visuino-ui-control-contract.md`: widget bridge manual.
- `docs\waveshare-4.3b-firmware-spec.md`: current reference-device specification.
- `gpt-knowledge\`: public support knowledge used by the shared GPT.
- `scripts\`: product verification and knowledge-export utilities.
- `dist-release\`: the single retained release ZIP.
