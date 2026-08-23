# Architecture

## Product boundary

QML owns layout, visual state, animation, focus, and presentation. Python owns
files, processes, settings, reports, version checks, models, and all interaction
with the existing backend. QML JavaScript is limited to local UI behavior.

```text
QML page or component
    -> Qt property, slot, or signal
Python service
    -> canonical schema, local process, filesystem, network, or game bridge
Existing KFPS backend or isolated external service
```

The main application does not parse game memory in QML, expose raw filesystem
objects to QML, or let the local web editor call arbitrary local endpoints.

## Startup and shutdown

`KFPS.UI/app.py` is the composition root. It resolves `AppPaths`, constructs the
services, exposes them to QML, loads `Main.qml`, and closes services in reverse
construction order. Development-only screenshot and layout auditing is installed
by `development_harness.py`; it is not mixed into product service behavior.

All services with timers, threads, executors, subprocesses, or queued callbacks
implement an idempotent `close()` method. `lifecycle.py` contains the shared
shutdown helpers. Closing the app must stop new work, cancel pending work, detach
callbacks, stop timers, terminate owned subprocesses, and then release models.

## QML shell and pages

`Main.qml` owns the frameless window, navigation, page loader, theme backdrop,
announcement ticker, version status, and process-wide modal state. Functional
pages live under `qml/pages`; reusable controls live under `qml/components`.

Large interaction surfaces should move coherent behavior into named components.
For example, `OutputExplorerContextMenus.qml` owns Outputs right-click and move
menus while `JsonPage.qml` retains page flow and dialogs. Components communicate
through explicit required properties and signals rather than reaching into page
internals.

## Service groups

Shell and state:

- `AppController`: route and page-title state.
- `SettingsService`: atomically stored UI preferences.
- `LogService`: one bounded, batched log model.
- `VersionService`, `ChangelogService`, and `AnnouncementService`: remote display
  data with cached fallbacks.
- `RuntimeService`: non-blocking runtime validation.
- `BackupService`: append-only `imgs` backups.

Artwork and JSON:

- `SourceImageService` and `GenerationService`: source selection, generator
  lifecycle, checkpoint preview polling, graceful stop, and force stop.
- `JsonService`: output navigation, selection, copy/move/delete, thumbnail state,
  and public QML models.
- `json_index.py`: startup scanning and persistent index cache.
- `json_metadata.py`: display names, counts, ages, and summary extraction.
- `PreviewService` and `json_thumbnail_worker.py`: cache identity and isolated
  thumbnail rendering.
- `kfps_shapes`: the canonical cross-app shape schema, resource normalization,
  and FD6 conversion boundary used by app, editor server, validator, and renderer.

External workflows:

- `TransferService`: online memory transfer and offline save-file bridges.
- `CgroupLibraryService`: local save discovery and library extraction.
- `CommunityService`, `community_catalog.py`, and `community_validation.py`:
  authenticated catalog workflows, UI normalization, and upload validation.
- `EditorService`: authenticated local Fabric editor process and project browser.
- `UpdateService`: close-and-handoff to the installed updater.
- `SupporterService` and activation modules: isolated receipt and remote activation
  state.
- `FullLiveryService`: lightweight QML facade for the process-isolated full-livery experiment.

The full-livery implementation lives under
`kfps_ui.experimental.full_livery`. Its worker protocol, durable catalog,
disposable viewer, cache, diagnostics, recovery records, and evidence-based
release gate are isolated from the stable services. See
`FULL_LIVERY_EXPERIMENT.md` before changing this boundary.

## Canonical shape contract

`kfps_shapes` is the only shared interpretation layer for supported vinyl JSON.
Callers may retain their public wrappers for compatibility, but they must delegate
shape discovery, resource identity, and supported foreign-schema conversion to
this package. Adding a schema means adding fixtures and contract tests here first,
then routing consumers through the same implementation.

The package intentionally does not perform game-memory access, filesystem UI,
network requests, or rendering. This keeps parsing deterministic and independently
testable.

## Local Fabric editor boundary

`start_fabric_editor.py` serves only the editor root, validates host/origin/fetch
metadata, and requires a random per-process `X-KFPS-Editor-Session` token for API
requests. The token is delivered in the launch URL fragment and moved to browser
session storage; it is not a stable secret or a query parameter.

`editor-fabric-adapter.js` contains the Fabric-specific scene, stacking, pointer,
and replacement operations. KFPS does not use Fabric SVG import or canvas SVG
export, so those APIs are disabled. See `FABRIC_RUNTIME.md` before changing the
vendored Fabric version.

## Native memory boundary

`native.py` exposes scoped `ProcessMemorySession` objects. Sessions request the
minimum Windows rights for read-only or explicitly requested write operations,
own one process handle, and close it deterministically. There is no module-global
process handle. Probes must default to read-only and must not retain handles across
operations.

## Thread and process rules

- Never run generation, indexing, rendering, networking, or game-memory work on
  the Qt GUI thread.
- A service owns every thread, executor, timer, and subprocess that it creates.
- Only the owning service may stop or replace that work.
- Stale result callbacks must be rejected by generation/request identity.
- Generator and transfer output enters one bounded shared log queue.
- JSON previews are keyed by source identity, timestamp, size, and renderer
  revision so a move does not force unrelated regeneration.

## Graphics renderer policy

`renderer_policy.py` resolves one backend before Qt application construction.
OpenGL remains the tested default. `KFPS_QML_GRAPHICS=auto`, `opengl`, `d3d11`,
or `software` provides an explicit diagnostic override, and an existing supported
`QSG_RHI_BACKEND` is respected when no KFPS override is present. Software mode
disables persistent scene-graph resources. This policy must be tested with editor,
themes, captures, and livery viewing before changing the default.

## Update and release trust boundaries

The installed updater resolves `main` once, pins the exact commit, verifies the
fetched object, requires a complete backup, mirrors only program files, verifies
the result, and restores on failure. It does not replace itself with a freshly
downloaded script before execution and does not clean a developer checkout.

Release archives come only from `tools/release/build_release_bundles.py`. The
builder exports tracked files from an immutable commit and rejects runtime and
personal-state paths. Manifests and SHA-256 files detect corruption and record
provenance; they are not publisher signatures. See `PACKAGING.md` and
`RELEASE_PROCESS.md`.

## Remote services

The supporter activation and FH6 RTTI relay Workers are separate TypeScript
projects with independent lockfiles, migrations, tests, and deployment state.
The desktop app treats remote data as untrusted input, validates it locally, and
retains safe cached fallbacks where the product requires offline startup.

## Themes

`Kfps.Theme/Theme.qml` selects a palette behind one semantic token contract so
themes share controls and page structure. Theme-specific backdrops and transitions
use generic shell hooks, not theme-name branches in shared controls. See
`THEME_SYSTEM.md` for the contract and checklist.
