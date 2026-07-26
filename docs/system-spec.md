# FAH Visuino LVGL Library Swapper System Specification

## Status

- Product: `FAH Visuino LVGL Library Swapper`
- Version: `1.0.1`
- Platform: Windows
- Runtime: Python 3.12 and Tkinter
- Distribution: PyInstaller one-file executable
- State: implemented, tested, and packaged

## Purpose

The application keeps separate Arduino/LVGL library environments for Visuino
Pro projects. Profiles are organized by client, project, and setup so different
devices can retain different LVGL, display-driver, touch-driver, configuration,
and customer-specific library versions without manually replacing one shared
Arduino library directory.

The product is independently developed by Finn Andre Hotvedt and dedicated to
Visuino, created by Boian Mitov. Ron Cutts is recognized for extensive testing
and design contributions.

## Scope

In scope:

- local client/project/setup profile management;
- setup folder creation and linking;
- required `Mitov` and optional `VisuinoPro` validation;
- missing-only baseline repair;
- guarded Visuino Pro configuration and launch;
- setup-specific component caches;
- backup, rollback, default restoration, and audit logging;
- recoverable setup-folder cleanup through the Windows Recycle Bin;
- standalone LVGL/device implementation import;
- Visuino Custom Code INO handoff;
- manual UI widget binding through `ui-elements.json`;
- future device-import generation through the published shared GPT.

Out of scope:

- Arduino IDE configuration or launch;
- automatic editing of `.visuino` projects;
- cloud synchronization;
- permanent deletion of setup content;
- automatic download of arbitrary third-party libraries;
- executing imported source code inside the desktop application.

## Data Model

The atomic JSON registry stores:

```text
client
  project
    setup
      stable ID
      display name
      resolved sketchbook path
      validation state
      imported implementation metadata
```

The previous valid registry is retained for recovery. Runtime state, audit
records, cache data, and restore points live under
`%LOCALAPPDATA%\LVGLVisuinoLibrarySwap`.

## Setup Folder Contract

`folderPath` identifies the Arduino sketchbook root:

```text
<folderPath>\
  libraries\
    Mitov\
    VisuinoPro\                 # optional
    lvgl\
    ESP32_Display_Panel\
    ESP32_IO_Expander\
    <implementation library>\
```

Validation creates the `libraries` child when missing. Recognized legacy
libraries stored directly at the setup root are copied into `libraries` without
deleting their originals.

`Mitov` is required. `VisuinoPro` is optional and is copied only when available
from the trusted source. Existing destinations are never merged, synchronized,
or replaced by baseline repair.

## Activation Contract

Activation requires Visuino Pro to be closed and the selected setup to pass
validation.

The guarded transaction:

1. records the default configuration before the first activation;
2. creates a pre-activation backup;
3. writes Visuino Pro `ArduinoLibraryPath` to `<setup>\libraries\`;
4. writes Arduino15 `arduino-cli.yaml` `directories.user` to `<setup>`;
5. launches `VisuinoPro.exe -CACHE<setup-cache> -REBUILD_CACHE`;
6. verifies the launched command line;
7. verifies that `DynamicDefinitions.txt` contains the expected `Mitov` and
   optional `VisuinoPro` source paths;
8. records success or restores both configuration values on failure.

YAML-only, Pro-registry-only, shared-registry-only, Arduino-IDE-only, and
`-CLD` approaches are rejected. `-CLD` selects flat `.vcomp` definitions and is
not an Arduino library-directory override.

The current cache verifier uses a fixed 180-second deadline. Local evidence
shows one rebuild can exceed this while the next succeeds with the same setup.
This is a known maintenance item: replace the fixed deadline with progress-aware
waiting and richer timeout diagnostics.

## Standalone Import Contract

A selectable device project contains:

```text
<ProjectName>\
  <ProjectName>.ino             # exactly one root INO
  README.md
  project-meta.json
  ui-elements.json
  include\
  src\
  ui\
  libraries\
    <complete Arduino libraries>\
```

The importer:

- rejects zero or multiple root INO files;
- rejects unsafe paths and source-inside-target recursion;
- produces a dry-run add/replace/unchanged inventory;
- installs device libraries under the selected setup's `libraries` directory;
- creates a setup-local implementation bridge library;
- preserves the complete root sketch for the Visuino Arduino Code Import/Parser;
- validates file paths, presence, and sizes without content hashes;
- backs up replacements and rolls back failed installation;
- never executes imported code.

## UI Control Bridge

Every new device package must expose:

- buttons: retained state or count plus a one-shot event;
- sliders and other inputs: readable value, write API, and user-change event;
- indicators: write API and optional readback;
- a declared C++ bridge namespace;
- copy-ready Visuino Input and loop examples.

The Waveshare reference namespace is `waveshare43_example`. All bridge calls
must retain `waveshare43_example::`.

## Profile Cleanup Contract

`Remove Profile` changes only the registry and preserves the folder.

`Clear / Delete...` is the only content-removal surface. It:

- targets only the exact selected inactive setup;
- requires Visuino Pro to be closed;
- blocks protected, overlapping, network, root, reparse-point, and unsafe paths;
- shows a read-only file/folder/byte preview;
- requires the exact phrase `DELETE <profile name>`;
- revalidates the inventory before execution;
- uses same-volume staging and the Windows Recycle Bin;
- rolls back on failure and appends an audit event.

Permanent deletion is forbidden.

## Runtime And Packaging

Tkinter owns the UI thread. Recursive scans, copies, activation, cache
verification, and cleanup run in worker tasks with structured results.

The retained release is one ZIP under `dist-release`. PyInstaller build folders,
raw EXE output folders, extracted verification trees, test experiments,
screenshots, and old distributions are temporary and are not part of the
maintained source tree.

## Validation

A release requires:

- all automated tests passing;
- a responsive isolated-data EXE smoke test;
- clean ZIP structure validation;
- extraction followed by Standalone Import analysis;
- exactly one root INO in the device folder;
- valid `project-meta.json` and `ui-elements.json`;
- Arduino CLI compilation for the declared target;
- physical upload and touch/display validation for hardware changes.

## Extension Rule

For another display or board, create a new folder under `source-import`. Lock
the exact hardware, resolution, controller, pinout, Arduino core, LVGL version,
dependencies, board options, UI bridge, and validation evidence before
generation. Never overwrite the verified Waveshare 4.3B reference.
