# FAH Project Vault

## Status

- Branch: `main`
- Operating mode: integrated architecture upgrade and controlled import
- Baseline: retained version 1.0.1 release archive
- Classification: integration-hub upgrade
- Release effect: integrated in source; new version and release package pending

## Interpreted Intent

Keep Visuino and Arduino pointed at the normal Arduino sketchbook while FAH
stores generated device projects permanently under one browsable client and
project hierarchy. Each generated project revision owns one uniquely named,
self-contained Arduino library. The normal sketchbook `libraries` folder
contains a managed NTFS directory junction to that permanent library.

The project library must be self-contained:

- one public FAH project header;
- display, touch, UI, assets, configuration, and bridge source;
- the exact project LVGL revision under its own `src/vendor/lvgl` tree;
- one unchanged root INO for the Visuino Arduino Code Import/Parser;
- `project-meta.json` and `ui-elements.json`.

The project may initially contain a physical LVGL copy. A nested junction to an
immutable shared LVGL revision is an optimization only after Arduino CLI and
Visuino compilation prove that nested junction traversal is reliable.

## Confirmed Requirements

- The vault root is a sibling of `libraries` under the normal Arduino
  sketchbook and is named `FAH LVGL`.
- The hierarchy is Client → Project → Revision.
- Generated projects remain available for later recompilation.
- The GUI provides a browser for the vault.
- Arduino and Visuino continue to use the normal Arduino library directory.
- Project links are real directory junctions, not Windows `.lnk` files.
- Exactly zero or one Project Vault revision is active globally at a time.
- Switching revisions preserves every permanent target and restores the
  previous verified junction if the switch cannot complete.
- The browser always identifies the active Client / Project / Revision,
  activation time, and verified link.
- Existing version 1.0.1 behavior remains available on `main`.
- The real Waveshare source has been imported without modification as the
  immutable `client_fah / project_waveshare43b_demo / r001` revision.

## Assumptions And Open Gates

- The current implementation targets local NTFS storage only.
- One project revision exposes one uniquely named Arduino library.
- `Mitov` and optional `VisuinoPro` remain normal baseline libraries.
- Junction traversal by Windows is proven locally.
- Arduino CLI discovery and compilation through the junction are proven with an
  isolated `arduino:avr:uno` probe.
- The first production-shaped import is the verified Waveshare 4.3B standalone
  package, stored as `client_fah / project_waveshare43b_demo / r001` with the
  unique library name `FAH_Waveshare43B_Demo_r001`.
- The real project junction is active in the normal Arduino `libraries`
  directory. Arduino CLI discovered it through that live path, and Visuino Pro
  opened `FAH-Waveshare43-Demo.visuino` without changing the configured normal
  sketchbook.
- Visuino Pro completed a full ESP32-S3 build in 11 minutes 10 seconds and
  reported `SUCCESS`. Its final library table resolved
  `FAH_Waveshare43B_Demo_r001` from the exact managed path below the normal
  Arduino `libraries` directory.
- A controlled Visuino rebuild completed its in-memory load, sort, and register
  cycle but did not persist the external cache. The main Errors view identified
  two known and accepted global component definitions without images in `Ron`
  and `Ron1`: `TArduinoLevel` and `TArduinobatterytest`. They require no action
  for this project and are not a release gate. The project library contains no
  Visuino component definitions, so it is resolved by Arduino at compile time
  and is not expected in the component cache.
- GPT Knowledge and the public GPT remain unchanged until a separately
  approved versioned release requires an update.

## Scope Lock

### MVP In Scope

- Resolve and initialize `<sketchbook>\FAH LVGL`.
- Validate the Client → Project → Revision hierarchy.
- Read and validate `fah-project.json`.
- Require one self-contained Arduino library per revision.
- Preview, create, verify, and remove only FAH-owned directory junctions.
- Preserve junction targets when a managed link is removed.
- Store an atomic active-link manifest under application data.
- Browse vault clients, projects, revisions, libraries, and link status.
- Analyze a standalone import folder before writing, reject unsafe filesystem
  entries and destination collisions, and show the exact immutable destination.
- Stage and atomically place a newly confirmed revision without overwriting an
  existing client/project/revision target.
- Flatten project code and non-LVGL dependency `src` trees into the one project
  library only when their case-insensitive target paths do not collide.
- Vendor only the compilable LVGL source tree and required public metadata under
  `src/vendor/lvgl`, with a project-local `lvgl.h` forwarding header.
- Keep all operations local and audit relevant write operations.

### Out Of Scope For The Current Source Integration

- Replacing the released setup workflow.
- Migrating existing setup folders automatically.
- Updating the public GPT.
- Publishing a new EXE or release ZIP.
- Sharing one writable LVGL source tree between customer locks.
- Network, UNC, FAT, exFAT, cloud-synced, or removable vault storage.
- Allowing Arduino Library Manager to modify FAH-owned project revisions.

## Runtime Layout

```text
<Arduino sketchbook>\
  libraries\
    FAH_Client_Project_r001\       # managed junction
  FAH LVGL\
    Clients\
      <client-id>\
        client.json
        Projects\
          <project-id>\
            project.json
            Revisions\
              r001\
                fah-project.json
                <Project>.ino
                project-meta.json
                ui-elements.json
                libraries\
                  FAH_Client_Project_r001\
                    library.properties
                    src\
                      FAH_Client_Project_r001.h
                      vendor\
                        lvgl\
```

Human display names live in manifests. Filesystem segments use stable,
sanitized IDs and never depend on later renames.

## Subsystem Map

| Stable ID | Owner | Responsibility |
| --- | --- | --- |
| `project_vault` | `project_vault_service` | Resolve, validate, scan, and initialize the permanent hierarchy. |
| `project_revision_manifest` | `project_vault_service` | Validate immutable revision identity and its self-contained Arduino library. |
| `managed_junction_set` | `managed_junction_service` | Preview, create, verify, roll back a failed creation, and remove only FAH-owned links. |
| `project_vault_browser` | `project_vault_dialog` | Present the hierarchy and current link state without hiding paths or failures. |
| `visuino_workflow_adapter` | existing activation boundary | Rebuild and verify a project cache after the link model is proven. |
| `audit_log` | existing audit repository | Record junction and vault mutations. |

## Integration Contracts

### `CONTRACT-PROJECT-VAULT-MANIFEST`

Input:

- vault root;
- stable client, project, and revision IDs;
- human display names;
- one library-relative path;
- one safe Arduino library folder name;
- project and UI metadata paths.

Output:

- validated immutable revision;
- resolved library target;
- operator-visible validation result.

Failure:

- Reject missing files, unsafe names, path escape, mutable revision identity,
  or more than one project library.

### `CONTRACT-MANAGED-JUNCTION`

Input:

- validated revision;
- normal sketchbook `libraries` path;
- expected junction name and target;
- previous active-link manifest.

Output:

- dry-run plan;
- verified junction;
- atomic active-link manifest;
- rollback result.

Failure:

- Never overwrite a real directory, file, symbolic link, foreign junction, or
  unexpected reparse point.
- Never delete or modify a junction target.
- Restore the previous FAH-owned link when activation cannot verify.

### `CONTRACT-PROJECT-VAULT-BROWSER`

Input:

- validated vault inventory;
- active-link manifest;
- current filesystem junction state.

Output:

- Client → Project → Revision tree;
- library name, target, and link status;
- broken, inactive, active, or conflict state.

Failure:

- Show invalid manifests and inaccessible paths as explicit read-only errors.

## Automation

### `AUT-010-IMPORT-VAULT-REVISION`

Triggered by a confirmed import action. It validates a standalone project,
builds a dry-run inventory, stages one self-contained library and the required
handoff files, validates the staged manifest, and atomically places the new
immutable revision in the vault. The source folder remains unchanged.

### `AUT-011-ACTIVATE-VAULT-LIBRARY`

Triggered when the operator confirms one valid inactive revision. It requires
Visuino to be closed, previews the exact single-active switch, creates and
verifies the new junction, removes only the previous verified FAH-owned
junction, atomically writes a single active-link entry with `linkedAt`, and
records the audit event.

### `AUT-012-RESTORE-JUNCTION-SET`

Runs inside a failed switch transaction. It removes only the newly created
FAH-owned junction, recreates only the previously verified junction, preserves
both immutable targets, and keeps the previous active-link manifest.

## YAML Model Proposal

The runtime representation may use atomic JSON, but the lockable model is:

```yaml
schemaVersion: 1
revision:
  id: "r001"
  immutable: true
client:
  id: "client_acme"
  name: "ACME"
project:
  id: "project_panel"
  name: "Panel"
library:
  name: "FAH_ACME_Panel_r001"
  relativePath: "libraries/FAH_ACME_Panel_r001"
  selfContained: true
  lvgl:
    version: "8.4.0"
    storage: "vendored"
handoff:
  rootIno: "FAH-ACME-Panel.ino"
  projectMeta: "project-meta.json"
  uiElements: "ui-elements.json"
```

## Security And Recovery Rules

- Resolve every path before comparison.
- Require vault targets to remain beneath the configured local vault root.
- Require live links to be direct children of the normal `libraries` folder.
- Use `_winapi.CreateJunction` instead of shell commands.
- Detect junctions with `os.path.isjunction`.
- Remove junctions with directory-entry removal only after target and ownership
  revalidation.
- Treat a real destination directory as a blocking conflict.
- Write the active-link manifest atomically with a previous valid copy.
- Never calculate or require content hashes, consistent with the current
  product contract.

## Implementation Phases

1. Lock this specification and stable metadata IDs.
2. Implement manifest, scan, and managed-junction services with isolated tests.
3. Add a read-only project-vault browser and explicit link activation preview.
4. Run Arduino CLI discovery and compile proof with a self-contained probe
   library. Completed with Arduino CLI 1.5.1 and `arduino:avr:uno`.
5. Implement and test the confirmed standalone-project import into an immutable
   vault revision. Completed with five focused import tests and the full
   then-current 86-test suite.
6. Import the verified Waveshare 4.3B package as `r001` and compile it through
   its unique library. Completed: 715 files, 17,467,169 bytes, LVGL 8.4.0,
   Arduino CLI 1.4.0, 708,174 program bytes, and 73,972 global-variable bytes.
   The live normal-sketchbook junction is created and verified, and Arduino CLI
   discovered the project through that live junction. The isolated proof is
   repeatable with
   `scripts/prove_waveshare_vault_import.py`.
7. Run Visuino cache and compile proof. Completed for the Project Vault
   junction: Visuino opened the retained demo and completed an ESP32-S3 build
   through the exact normal-library junction with `SUCCESS` in 11 minutes
   10 seconds. The project library has no Visuino component definitions and is
   therefore a compile-time Arduino dependency, not a component-cache entry.
   The known `Ron` and `Ron1` image warnings are accepted and require no
   Project Vault work.
8. Enforce exactly one active revision, add rollback-safe switching, and show
   active Client / Project / Revision with activation time. Completed with
   focused Windows junction switch and simulated persistence-failure rollback
   tests, full-suite verification, and visual GUI verification.
9. Decide whether to keep vendored LVGL copies or permit immutable shared-LVGL
   junctions.
10. Only after approval, plan migration, GPT Knowledge changes, packaging, and
   release.

## Validation Checklist

- `main` remains unchanged.
- Invalid and escaping manifests are rejected.
- Real folders and foreign links are never overwritten.
- Removing a managed junction preserves its target.
- Failed link creation rolls back without changing the project target.
- Previous-set restoration remains a planned extension.
- Vault browser distinguishes active, inactive, broken, and conflict states.
- Arduino CLI discovers and compiles the project through the junction. Passed
  first with the isolated AVR probe, then with the real self-contained
  Waveshare ESP32-S3 revision in an otherwise empty temporary sketchbook.
- Visuino cache references the selected project library.
- Reopening and recompiling a project uses the same immutable revision.
- Existing version 1.0.1 tests remain green.

## Extension Roadmap

- Optional shared, immutable LVGL version store.
- Project-specific Visuino cache without changing Arduino Library Directory.
- Existing setup-to-vault migration assistant.
- GPT output contract for one self-contained FAH project library.
- Customer revision locks and exportable delivery bundles.
