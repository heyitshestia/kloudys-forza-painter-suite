# KFPS Bootstrap Updater

`KFPS-Updater.exe` is a self-contained Windows x64 updater and recovery tool. It does not require Git, Python, Node.js, .NET, or an existing intact KFPS installation.

The complete architecture, compatibility rules, diagnostics contract, and publication procedure are documented in [`docs/BOOTSTRAP_UPDATER.md`](../../docs/BOOTSTRAP_UPDATER.md).

## Trust and recovery

- Normal updates use exact JSON bytes signed with the KFPS Ed25519 production key embedded at build time.
- Every component archive has a signed size and SHA-256 and a per-file inventory.
- Channel sequence numbers prevent replaying an older signed update after a newer one was accepted.
- The published KFPS 3.1.54 recommended bundle is embedded as a URL, size, SHA-256, release-manifest SHA-256, version, and commit. It is the offline-compatible recovery floor for old and incomplete installations.
- The private signing key is never stored in the repository or a release bundle.

## Installation behavior

The updater recognizes either the outer release folder or `KloudysFH6Painter` itself. It stages and verifies downloads before writing. Changed files are backed up, every operation is journaled, and a failed or interrupted transaction is rolled back before another update starts.

For the 3.1.28 and 3.1.52 transition, their untouched BAT updater first delivers the inner bootstrap and bootstrap-aware UI from Git. The next Update action runs the EXE, repairs the full package, and installs matching inner and outer updater copies. Pinned 3.1.54 recovery keeps only a tiny BAT shim for its older UI; the first signed update removes both BAT names. The immutable BAT and launcher hashes are recorded in `legacy_bridge_contract.json`.

The updater never lets a manifest manage these application paths:

- `.git/`
- `runtime/`
- `imgs/`
- `webui-data/`
- `node_modules/`
- `.wrangler/`
- `.venv/`
- `.dev.vars*`
- `*.kfpskey`

Only the signed `python-runtime` component can manage `python/`. It treats that directory as an exact program-owned runtime, allowing missing dependencies to be repaired and stale packages to be removed. Generated `__pycache__` directories and `*.pyc` files are ignored.

## Commands

```text
KFPS-Updater.exe --root "C:\path\to\KFPS" --check
KFPS-Updater.exe --root "C:\path\to\KFPS"
KFPS-Updater.exe --root "C:\path\to\KFPS" --recover
KFPS-Updater.exe --root "C:\path\to\KFPS" --recover --recovery-archive "KFPS-3.1.54-bundled.zip"
```

`--check` performs download and verification but does not modify the installation. It exits `0` when healthy, `3` when verified repairs are required, and `1` on failure. Invalid options or layouts exit `2`. A mutating self-update exits `4` after an authenticated child starts; final success or failure is written by that child. `--recover` explicitly selects the embedded 3.1.54 baseline, but it refuses to downgrade newer version or same-version/different-commit evidence from accepted state or the installed release manifest. A local recovery archive is accepted only when its exact size and SHA-256 match the values embedded in the executable.

Interactive runs print live state, trust, manifest, file-inventory, download, backup, apply, and final-verification phases. Failures print the exact phase and reason plus the log and JSON report paths, then wait for Enter. Successful in-app updates close the updater only after KFPS has relaunched. `--no-pause` retains immediate exits for scripts and test automation, including verified self-update handoffs.

Existing symlinks, junctions, and other Windows reparse points are rejected in installation, state, staging, download, backup, log, and report paths. The updater never follows one to repair or clean another location.

Logs, reports, backups, staging state, and interruption journals are stored under `%LOCALAPPDATA%\KloudysFH6Painter\updater\installations\<installation-id>`. Each portable install has independent state. JSON reports are also copied to `KloudysFH6Painter\runtime\update-reports` when that directory can be created.

## Build

The production public key must exist at `trust\production-ed25519.public`.

```powershell
.\tools\bootstrap_updater\build.ps1
```

The build runs Go tests, Go static checks, updater integration tests, and release-builder tests. It creates the self-contained `KFPS-Updater.exe` in the repository root, creates the non-shipping publisher in `tools\bootstrap_updater\build`, checks the executable version, and prints its SHA-256.

Go 1.22 or newer is the supported build floor; see `BUILDING.txt`.

The executable-level signed update gate uses an ephemeral test key and exercises dry-run, self-update handoff, apply, no-op, repair, and sequence rollback:

```powershell
.\tools\bootstrap_updater\tests\run_signed_cli_release_gate.ps1
```

The Windows lock gate creates a real NTFS junction at `updater.lock` and proves the updater rejects it without modifying the junction target:

```powershell
.\tools\bootstrap_updater\tests\run_windows_lock_gate.ps1
```

The full pinned-recovery gate exercises an actual published bundle, including a nearly empty legacy rebuild:

```powershell
.\tools\bootstrap_updater\tests\run_real_recovery_gate.ps1 -Archive C:\path\KFPS-3.1.54-bundled.zip -Updater C:\path\test-enabled-updater.exe
```

The historical release matrix downloads authenticated draft fixtures, verifies their GitHub asset hashes, and runs the exact production bootstrap against disposable copies:

```powershell
.\tools\bootstrap_updater\tests\run_historical_release_matrix.ps1 -RecoveryArchive C:\path\KFPS-3.1.54-bundled.zip
```

The legacy bridge gate runs the untouched 3.1.28 and 3.1.52 BATs first, then proves the next-update bootstrap handoff, dependency repair, recovery shim, redundant-copy repair, protected-data preservation, and warm no-op:

```powershell
.\tools\bootstrap_updater\tests\run_legacy_bat_bootstrap_gate.ps1 -RecoveryArchive C:\path\KFPS-3.1.54-bundled.zip
```

Measured release-gate results and environment-dependent gaps are recorded in [`docs/BOOTSTRAP_UPDATER_VALIDATION.md`](../../docs/BOOTSTRAP_UPDATER_VALIDATION.md).

The private key belongs under `%LOCALAPPDATA%\KloudysFH6Painter\updater-signing`, with access restricted to the current Windows account. Use the publisher's `keygen`, `sign`, and `verify` commands. Never place the private key under the repository, Desktop release folders, archives, or cloud synchronization.
