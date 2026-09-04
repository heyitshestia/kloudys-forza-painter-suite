# KFPS Bootstrap Updater

## Interactive terminal behavior

Bootstrap 1.0.2 gives every long operation a visible status: process waiting,
state recovery, channel and manifest trust checks, component file scans,
downloads, rollback backup, file installation, and final verification. Large
inventories report periodic checked-file counts and large downloads retain
percentage and byte progress.

An interactive failure prints a terminal summary containing the failed phase,
reason, log path, and JSON report path, then waits for Enter. An in-app success
closes only after KFPS relaunches. `--no-pause` remains the explicit automation
contract and propagates through a verified updater self-handoff.

## Purpose

`KFPS-Updater.exe` is the recovery floor for packaged KFPS installations. It is a self-contained Windows x64 executable and does not use Git, Python, Node.js, .NET, PowerShell, or the KFPS-bundled Python runtime to perform an update.

It solves two separate problems:

1. Repair old or incomplete packaged installations against one immutable, hash-pinned release.
2. Install future signed component updates without downloading or replacing healthy components.

Source checkouts such as `KFPS CLEAN` and `KFPS DIRTY` continue to use `03_update_from_github.bat`. The bootstrap updater is for release-package layouts.

## Package layout

Future recommended bundles contain two identical updater copies:

```text
KFPS-<version>/
  KFPS.exe
  KFPS-Updater.exe
  KloudysFH6Painter/
    KFPS.exe
    KFPS-Updater.exe
    VERSION
```

The outer executable is preferred. The inner copy is a launch fallback when the outer copy is missing or cannot start. A separately downloaded updater can also be placed beside the outer `KFPS.exe` and run directly.

## Trust model

Normal updates use a detached Ed25519 signature chain:

```text
embedded public key
  -> signed stable channel
  -> pinned manifest size and SHA-256
  -> signed component manifest
  -> component archive size and SHA-256
  -> exact per-file size and SHA-256
  -> post-install verification
```

The stable channel has a monotonically increasing sequence number. An installation that has accepted sequence 12 will reject sequence 11, even when sequence 11 has a valid signature. A rollback must be published as a new, higher sequence.

Accepted state stores the exact signed channel and manifest identities. Reusing sequence 12 for different signed bytes is rejected rather than treated as another sequence-12 release.

State is isolated per installation. The updater derives a stable identity from the canonical package root, stores state beneath that identity, and records the identity in `state.json` and every run report. Two portable KFPS folders therefore cannot share a lock, transaction journal, accepted sequence, report history, or handoff cache.

The production private key is not in Git or any release bundle. The updater contains only the public key with key ID `a1ded23c6c64b25b`.

## Recovery floor

The executable pins the public KFPS 3.1.54 recommended bundle:

- Version: `3.1.54`
- Commit: `87dd1de0dc9104f423a8042d9be304f86f87ad15`
- Bundle size: `422238121` bytes
- Bundle SHA-256: `551f4052ee8f6707d7c7e24fb7b42ed74be9bfac45e3cfdd7281ca773e1ad0ec`
- Release manifest size: `2286851` bytes
- Release manifest SHA-256: `3929f83aa0794909dfe1854d97885a10db9d6d0badfe0f10d3b55a176044a4c6`

When the signed channel is unavailable:

- A healthy 3.1.54 package is checked locally; the first bootstrap run also installs the two updater copies and replaces the legacy Git updater with a small bootstrap-only compatibility shim.
- A damaged or incomplete package at 3.1.54 or older downloads the pinned bundle and repairs only missing or mismatched program files.
- A package newer than 3.1.54 is not downgraded. It stops if no valid signed channel is available.

Automatic recovery fallback is limited to transport/source availability failures. Signature, hash, schema, sequence, state-integrity, and path-policy failures remain visible and fail closed. Explicit recovery applies the same downgrade check using valid `VERSION`, persistent accepted state, and release-manifest evidence. Large artifacts use connection/header/activity timeouts and verified HTTP range resume rather than one whole-download deadline.

Generated Python bytecode under `__pycache__` and `*.pyc` is ignored. It is mutable cache, not a dependency. Real Python modules, extension modules, DLLs, and executables remain hash-verified.

## Legacy BAT migration

The public 3.1.28 and 3.1.52 recommended bundles contain different historical copies of `03_update_from_github.bat`. Both can update from Git and both pin the same native launcher SHA-256. The migration uses that existing behavior in two user-visible Update actions:

1. The untouched historical BAT updates program files from `main`. This delivers `KFPS-Updater.exe` inside `KloudysFH6Painter` and the bootstrap-aware UI update service. Python remains preserved during this first stage.
2. The next Update action selects the inner bootstrap automatically. The bootstrap verifies the signed channel or pinned recovery inventory, repairs Python and other program files, and installs identical inner and outer updater copies.

Pinned 3.1.54 recovery contains the pre-bootstrap UI service. A recovery run therefore replaces the old 37 KB Git BAT with a small compatibility shim that invokes the verified outer or inner updater; it removes the obsolete `update_from_github.bat` wrapper. This keeps the recovered old UI Update button functional without retaining the legacy Git updater. The first successful signed component update installs the bootstrap-aware UI and removes both BAT names transactionally.

`tools/bootstrap_updater/legacy_bridge_contract.json` records the immutable historical BAT hashes and required launcher hash. Tests fail if `KFPS.exe` changes while this legacy acquisition bridge is active. Do not change the launcher bytes or remove the source BAT until the migration window is explicitly closed.

## Component model

Future updates have three independently verified components:

| Component | Target | Behavior |
| --- | --- | --- |
| `application` | `KloudysFH6Painter` | Repairs tracked KFPS program files. Stale files are removed only when explicitly listed as retired. |
| `python-runtime` | `KloudysFH6Painter/python` | Repairs the complete bundled Python runtime and removes stale program-owned packages, excluding generated bytecode caches. |
| `native-launchers` | Outer package root | Repairs `KFPS.exe` and `KFPS-Updater.exe`. Launchers are applied last. |

A component archive is downloaded only when at least one file from that component needs replacement. Removal-only cleanup does not download its archive.

## Preserved data

Signed manifests cannot manage these application paths:

- `.git/`
- `runtime/`
- `imgs/`
- `webui-data/`
- `node_modules/`
- `.wrangler/`
- `.venv/`
- `.dev.vars*`
- `*.kfpskey`

The updater does not repair or delete generated images, JSON outputs, community downloads, settings stored in runtime data, supporter keys, local Worker state, or unrelated files. The bundled `python/` directory is program-owned and is the exception.

## Transaction behavior

Before any installation file changes, the updater:

1. Waits for the KFPS process that launched it to exit, with a bounded timeout.
2. Downloads and verifies required archives.
3. Extracts only required files into a private staging directory.
4. Verifies every staged file.
5. Checks each involved volume for rollback copies, same-directory replacement space, and a safety margin.
6. Backs up every destination that will change.
7. Writes an atomic transaction journal covering the complete backed-up plan.

Each file is installed through a unique, journaled same-directory temporary file and `MoveFileExW` with replace and write-through flags. Extended Windows paths are used for long package locations. The prior signed sequence state is part of the durable transaction journal, so files and anti-rollback state recover together across a crash. If apply, verification, state persistence, or commit fails, the complete backed-up plan rolls back in reverse order. If the computer or updater stops mid-transaction, the next run validates the journal and performs the rollback before doing new work.

Every existing ancestor used for installation, state, staging, backups, downloads, logs, and reports is checked for symlinks, junctions, and Windows reparse points before mutation. Unsafe paths are rejected or, for the optional application report copy, skipped without following the link.

An interrupted journal is rejected when it identifies another installation, escapes the installation or backup roots, duplicates a destination, names an unknown operation, or is missing a required rollback file.

Successful and rolled-back transactions remove their temporary backups. Old logs and reports are bounded by count and age.

## Self-update

The signed channel declares the required bootstrap version and exact updater executable hash. When the running updater is too old or has the wrong hash, it downloads the signed updater artifact into the local updater state directory and starts a verified handoff process. The handoff executable updates the outer copy after the original process exits.

A newer bootstrap updater will not downgrade itself to an older channel updater. The child receives the resolved package/state paths and waits for the parent updater process to exit before replacing launchers. The downloaded executable is reopened without following links, hashed through the held file handle, checked for a stable Windows file identity, and kept open without write/delete sharing through process creation.

For `--check`, the parent waits for the verified child and returns the child's exact terminal exit code. For a mutating update, exit `4` means the verified child was started and the update remains pending; it does not mean the update completed. The parent report uses `handoff-pending`, while the child writes its own terminal report. A process-launch failure rewrites the parent report as `failed`.

## Commands

```text
KFPS-Updater.exe --root "C:\path\to\KFPS-package" --check
KFPS-Updater.exe --root "C:\path\to\KFPS-package"
KFPS-Updater.exe --root "C:\path\to\KFPS-package" --recover
KFPS-Updater.exe --root "C:\path\to\KFPS-package" --recover --recovery-archive "KFPS-3.1.54-bundled.zip"
```

`--check` verifies and reports without changing installation files. Exit `0` means healthy, exit `3` means verified repairs are required, exit `1` means the operation failed, and exit `2` means options or layout were invalid. For a mutating self-update only, exit `4` means an authenticated updater child started and the final result is pending. A local recovery archive is accepted only when its exact size and SHA-256 match the recovery values embedded in the executable.

Custom channels, custom state paths, local files, loopback HTTP, and sequence-reset options require both a separately compiled test-enabled executable and `KFPS_UPDATER_TEST_MODE=1`. Production builds omit the test capability, so an environment variable alone cannot enable it.

## Diagnostics

Primary state is stored under:

```text
%LOCALAPPDATA%\KloudysFH6Painter\updater\installations\<installation-id>\
  logs\
  reports\
  state.json
  current-transaction.json      # only while a transaction is active
```

A copy of each JSON report is also written to:

```text
KloudysFH6Painter\runtime\update-reports\
```

Reports identify the updater version, platform, installation roots, mode, phase, status, source and target versions, accepted sequence, downloaded bytes, rollback result, crash recovery, and every planned file action with its expected hash.

Older global updater state is not imported automatically because it cannot prove which portable package it belongs to. It may remain on disk, but current updaters use only the installation-specific namespace.

For a failure, collect the newest JSON report and the `log_path` named inside it. Do not send `.kfpskey` files or unrelated runtime data.

## Publication

The non-shipping `KFPS-Update-Publisher.exe` is built under `tools/bootstrap_updater/build`. It refuses modified tracked files and refuses a commit identifier that is not the current `HEAD`. Application files come from `git archive` of that exact commit, while the Python runtime and updater are copied once into a private snapshot. `VERSION` and updater build identity are read from those snapshots. Output must be absent or empty and cannot equal, contain, or sit beneath an input root. The complete payload is built in a private sibling workspace, every archive and the final client contract are reopened and verified, source Git identity is rechecked, and the completed directory is atomically promoted.

While the legacy bridge is active, the publisher excludes `03_update_from_github.bat` and `update_from_github.bat` from the signed application archive and lists both as retired. They remain in Git only so historical BAT clients can acquire the bootstrap on their first update.

Production publication order is deliberately atomic:

1. Bump and commit KFPS. Verify the checkout is clean.
2. Build and test `KFPS-Updater.exe` with `tools/bootstrap_updater/build.ps1`.
3. Run the publisher with a new sequence and an immutable HTTPS artifact base URL.
4. Verify `SHA256SUMS.txt`, the manifest signature, and the channel signature.
5. Upload the component ZIPs, versioned updater, manifest, and manifest signature.
6. Download the uploaded assets once and verify their exact sizes and hashes.
7. Copy only `channel.json` and `channel.json.sig` into `updates/stable/`.
8. Commit and push those two channel files last.
9. Test one healthy package, one damaged application file, and one damaged Python dependency through the real KFPS Update page.

Never replace an artifact at a published URL. Publish a new immutable URL and a higher channel sequence instead.

Normal version bumps on `main` are published automatically by the final jobs in
`quality.yml`. The publisher runs only after the Windows application, Worker, and
Community end-to-end gates pass. It verifies the currently signed channel and
manifest, reuses that manifest's verified Python runtime as publication input,
creates a new immutable update-data prerelease, downloads and hashes every
uploaded asset, publishes the prerelease, and commits the new signed channel
last. Public KFPS releases and downloadable bundles remain a separate manual
operation.

The `updater-production` GitHub environment is restricted to `main` and contains
the `KFPS_UPDATER_PRIVATE_KEY` secret. The old BAT updater is not used to publish
or install current updates; it remains only as the authenticated bridge for
historical 3.1.28 and 3.1.52 installations.

Example staging command:

```powershell
& .\tools\bootstrap_updater\build\KFPS-Update-Publisher.exe build `
  --app-root . `
  --python-root .\python `
  --updater .\KFPS-Updater.exe `
  --private "$env:LOCALAPPDATA\KloudysFH6Painter\updater-signing\production-ed25519.private" `
  --public .\tools\bootstrap_updater\trust\production-ed25519.public `
  --output C:\verified-empty-staging-directory `
  --base-url https://immutable.example.invalid/kfps/3.1.56-sequence-3 `
  --version 3.1.56 `
  --commit (git rev-parse HEAD) `
  --bootstrap-version 1.0.2 `
  --sequence 3
```

The private key path is local machine state, not a suggested backup. Store an offline protected backup separately. Losing or compromising the private key requires shipping a new bootstrap updater with a new trusted public key.

## Known limits

- The executable is not currently Authenticode-signed, so Windows may identify the publisher as unknown.
- It cannot repair itself when no runnable outer or inner updater copy remains. In that case, use a fresh drop-in `KFPS-Updater.exe`.
- A mutating run that exits `4` has started a verified child but has not reported that child's terminal result. Use the newest child JSON report and log for the outcome.
- Recovery restores KFPS program files, not user-created content.
- The embedded recovery floor is intentionally fixed at 3.1.54. Future versions depend on the signed channel and never silently fall back to an older release.
- Until the first signed channel is published, pinned recovery intentionally leaves a bootstrap-only BAT shim because the 3.1.54 UI predates direct EXE launching. It contains no Git update implementation and is removed by the signed update.
- Network, disk, antivirus, permissions, or a still-running KFPS process can block replacement. The updater stops and rolls back rather than accepting a partial installation.
