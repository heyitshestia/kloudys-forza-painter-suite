# Full Livery Isolation Implementation Record

Date: 2026-08-23

Workspace: the active KFPS staging checkout

Version at implementation: 3.1.33

## Scope

The experimental FH6 Full Livery Workshop was separated from the stable KFPS
runtime as far as practical without changing its public workflow. CLEAN, Native
Updated Local, GitHub, the application version, and release bundles were not
changed.

The feature remains a candidate/WIP experiment. This work improves containment,
recovery, indexing, diagnostics, and lifecycle behavior; it does not claim that
all vehicle rendering is visually correct.

## Implemented architecture

- `FullLiveryService` is now the QML-facing state and command facade.
- Save scanning, package indexing, package validation and migration, source
  preview construction, export, installation, vehicle indexing, mesh conversion,
  render-atlas construction, and cache clearing run in a supervised child
  process.
- The 3D inspector runs in a separate disposable process with a unique local
  session for each selected livery.
- Leaving the Liveries page clears the viewer URL, destroys the WebEngine view,
  requests worker cancellation, and force-stops processes that do not exit.
- Stale worker results are rejected by request, selection, and serial identity.
- Worker process trees have operation deadlines, cooperative cancellation,
  forced termination, and a 6 GiB resident-memory limit.
- The viewer has a separate abnormal-growth guard. A 4 GiB process-tree increase
  closes the viewer and records diagnostic evidence.
- A dedicated `KFPS.UI/full_livery_process.py` bootstrap supports bundled and
  system Python without depending on inherited `PYTHONPATH` behavior.
- Frozen/native launchers use hidden application worker and inspector entry
  points implementing the same protocol.

## Runtime isolation

Operational state is stored beneath:

```text
runtime/experiments/full-livery/
  state/
    settings.json
    catalog.sqlite3
    qualification.json
  cache/v11/
    vehicle-index/
    meshes/
    atlases/
    previews/
  sessions/
  diagnostics/
  quarantine/
  recovery/
    install-backups/
```

User-created `.kfpslivery` packages remain in
`imgs/exported/full-liveries`. Cache clearing cannot remove packages or FH6 save
data. Existing legacy settings are copied into the isolated state directory
without deleting the original file.

## Durable indexing

The experiment now uses a versioned SQLite catalog for save sources, packages,
and rebuildable cache identities.

- SQLite uses WAL mode, full synchronous commits, a busy timeout, and startup
  integrity checking.
- Corrupt catalog files are moved to quarantine before an empty catalog is
  rebuilt.
- Scans load prior identities once, reuse unchanged rows in memory, and publish
  a complete scan in one transaction.
- Interrupted scans leave the previous complete catalog intact.
- Files are removed from the catalog only after their configured root completes
  successfully.
- A missing manually selected save root never silently falls back to another
  drive.
- If a save root becomes unreadable during traversal, its last complete snapshot
  remains visible with a stale-data warning.
- The catalog is advisory only. Ownership, source content, package integrity,
  car identity, and save writes are independently reopened and verified by the
  worker before sensitive operations.

## Diagnostics and recovery

- Every worker operation receives a session directory containing its bounded
  stdout, stderr, lifecycle events, request metadata, result, and traceback.
- A running marker left after a crash is converted into an abandoned-session
  recovery record on the next startup.
- Old session directories are pruned to a bounded history.
- The Liveries page has a Diagnostics action that exports a privacy-scrubbed ZIP.
- Diagnostic exports omit original saves, packages, images, keys, receipts, and
  other user content. Windows account names are scrubbed from included text.

## Release gate

The experiment supports `disabled`, `preview`, `candidate`, and `stable` stages.
The default remains candidate/WIP.

- `disabled` cannot start scans, package work, previews, conversion, export, or
  installation, including through previously cached list entries.
- `preview` allows inspection and package export but not save installation.
- `candidate` exposes the complete testing workflow.
- `stable` is refused unless qualification evidence matches the current KFPS
  version, package compiler revision, and cache revision.

Required stable evidence covers both FH6 stores, AMD/NVIDIA/Intel graphics,
multiple vehicle forms, masks, windows, layering, gradients, cold/warm runs,
25 repeated switches, cancellation, crash recovery, package round trips, and
security checks.

The evidence helper is:

```powershell
.\python\python.exe tools\livery\full_livery_qualification.py initialize
.\python\python.exe tools\livery\full_livery_qualification.py record <check> --pass --evidence <description>
.\python\python.exe tools\livery\full_livery_qualification.py status
```

## Main files

- `KFPS.UI/src/kfps_ui/full_livery_service.py`: UI-facing facade and lifecycle.
- `KFPS.UI/full_livery_process.py`: bundled/system Python process bootstrap.
- `KFPS.UI/src/kfps_ui/experimental/full_livery/paths.py`: isolated paths.
- `catalog.py`: durable SQLite catalog.
- `protocol.py`: versioned worker operations.
- `jobs.py`: worker-side full-livery operations.
- `worker_main.py`: worker execution and cancellation.
- `supervisor.py`: worker and inspector process supervision.
- `inspector_main.py`: disposable local inspector host.
- `diagnostics.py`: session records, recovery, scrubbing, and ZIP export.
- `feature_gate.py`: experiment stages.
- `qualification.py`: stable-release evidence contract.
- `KFPS.UI/qml/pages/LiveryPage.qml`: page activation, teardown, diagnostics,
  stage display, and disabled-state controls.
- `tools/livery/full_livery_qualification.py`: qualification command-line helper.

## Verification completed

- Full project suite: 454 tests passed; one existing opt-in network integration
  test was skipped.
- Focused full-livery suite with system Python: 83 tests passed.
- Focused full-livery suite with bundled Python: 83 tests passed.
- Real child-process bootstrap was exercised in both focused runtime runs.
- Python compilation passed.
- QML parsing passed. Existing unqualified-context warnings remain warnings only.
- Offscreen bundled-runtime capture of the Liveries page passed at 1280x720.
- Worker and capture processes exited without lingering child processes.
- `git diff --check` passed.

## Known limits and next evidence

- This is not yet qualified as visually correct across every FH6 vehicle.
- AMD, NVIDIA, and Intel repeated-switch testing still requires real hardware.
- Microsoft Store/Xbox and Steam installations both require complete workflow
  evidence.
- Masks, windows, fades, gradients, overlap, and exact layer order need broader
  real-livery comparison sets.
- First-render and cached-render timings should be recorded on representative
  machines.
- Installation and package round-trip tests require controlled real-save tests
  with recovery records retained.

Do not mark this subsystem stable merely because automated tests pass. Stable
status requires the complete evidence matrix described above.
