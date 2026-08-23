# Full Livery Experimental Boundary

## Status

The FH6 Full Livery Workshop is a **candidate experiment**, not a stable KFPS
subsystem. It remains public for community testing, but the page identifies its
stage and shows the existing WIP notice once per application session.

The implementation and validation state completed on 2026-08-23 is recorded in
[`FULL_LIVERY_IMPLEMENTATION_RECORD_2026-08-23.md`](FULL_LIVERY_IMPLEMENTATION_RECORD_2026-08-23.md).

The experiment may be marked stable only when the checked qualification matrix
matches the current KFPS version, package compiler revision, and cache revision.
Setting `KFPS_FULL_LIVERY_STAGE=stable` without complete evidence falls back to
`candidate` automatically.

## Process boundary

`FullLiveryService` is a small QML-facing facade. It owns page state and starts
or cancels operations, but it does not decode saves, validate or migrate
packages, build the car index, convert meshes, render section atlases, or write
FH6 save data.

Those operations run one at a time in an isolated child process through the
versioned JSON protocol in `kfps_ui.experimental.full_livery`. The supervisor:

- rejects stale results by request and selection identity;
- requests cooperative cancellation when work is superseded or the page closes;
- terminates work that ignores cancellation, exceeds its deadline, or exceeds
  the process-tree memory limit;
- captures stdout, stderr, traceback, elapsed time, and peak resident memory;
- supports bundled Python and the no-Python executable build;
- never performs a hidden write merely because the page opened.

Python-based launches use the dedicated `KFPS.UI/full_livery_process.py`
bootstrap, which supplies the same module roots to bundled and system Python
without relying on inherited `PYTHONPATH` behavior. Frozen builds use the same
worker and inspector entry points through hidden application arguments.

The local 3D inspector is a second disposable process. Each new livery receives
a fresh server session. Leaving the page clears the URL, destroys the QML
`WebEngineView`, requests viewer shutdown without blocking the UI, and force
stops a viewer that does not exit promptly.

## Runtime layout

All rebuildable and operational state is isolated under:

```text
runtime/experiments/full-livery/
  state/
    settings.json
    catalog.sqlite3
    qualification.json
  cache/v<revision>/
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

Shareable `.kfpslivery` packages remain user output and are stored at
`imgs/exported/full-liveries`. Clearing the experimental cache cannot remove
those packages or local FH6 saves.

## Durable catalog

`catalog.sqlite3` is a rebuildable, versioned index of discovered save sources,
saved packages, and cache entries. It uses SQLite WAL mode, full synchronous
commits, corruption checking, and corruption quarantine.

A scan reads the prior file identities once, reuses unchanged rows in memory,
and commits the complete result in one transaction. Interrupted scans leave the
last completed catalog intact. Deleted files are removed only after a complete
scan of their configured root. A missing manually selected root never falls
back to a different drive, and a root that becomes unreadable partway through a
scan keeps its last complete snapshot with a stale-data warning. This avoids
per-file disk flushes and keeps a warm restart responsive with large catalogs.

The catalog is never trusted for ownership, package integrity, car identity, or
save writes. Export and installation independently reopen and verify source data
inside the worker.

## Diagnostics and recovery

Each operation has its own session directory with request metadata, bounded
logs, lifecycle events, result, and failure traceback. An active marker left by
a terminated process is converted into an abandoned-session recovery record on
the next start. The `Diagnostics` button exports a privacy-scrubbed ZIP with
session evidence, recovery records, catalog counts, and release-gate state.

Absolute Windows account names are removed from exported diagnostics. Original
save records, packages, images, keys, and receipts are not included.

## Qualification gate

The required checks cover:

- Microsoft Store/Xbox and Steam installations;
- AMD, NVIDIA, and Intel graphics;
- coupe, sedan, hatchback, SUV/off-road, and unusual multi-part cars;
- masks, windows, fades, gradients, overlap, and layer order;
- first uncached and later cached workflows;
- at least 25 repeated car/package switches;
- cancellation, worker failure, abandoned-session recovery, package round trip,
  and package security.

Developer evidence is maintained with:

```powershell
.\python\python.exe tools\livery\full_livery_qualification.py initialize
.\python\python.exe tools\livery\full_livery_qualification.py record gpu.amd --pass --evidence "diagnostic ZIP and comparison set"
.\python\python.exe tools\livery\full_livery_qualification.py status
```

Failed checks remain failed. Evidence is not carried across KFPS versions or
cache/package revisions without explicit revalidation.
