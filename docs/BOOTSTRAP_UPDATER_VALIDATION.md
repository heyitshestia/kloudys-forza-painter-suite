# Bootstrap Updater Validation

## Bootstrap 1.0.2 terminal and handoff validation

Bootstrap 1.0.2 adds live terminal phases and periodic inventory progress while
keeping the signed update, path, transaction, and rollback contracts unchanged.
Interactive failures wait for acknowledgement and show the failure phase,
reason, log, and report locations. Explicit `--no-pause` automation remains
non-interactive and the preference is preserved through verified self-update
handoffs. Release validation covers both paths, a 1.0.1-to-1.0.2 self-replace,
full KFPS application update, warm no-op, and relaunch behavior.

Validation date: 2026-09-02

Validation host:

- Windows 10 Enterprise 22H2, build 19045, x64
- Go 1.26.3 windows/amd64
- Python 3.12.10 for KFPS integration tests only
- Bootstrap updater 1.0.1, built with `CGO_ENABLED=0`

## Result

All locally reproducible release gates pass after the second independent source audit and targeted rework. Every reported audit reproduction now has a fail-closed regression or an isolated-state invariant. One file-symlink test could not create its fixture without Windows symlink privilege; Windows hard-link rejection and a real NTFS junction rejection cover the same lock-leaf write boundary on this host.

The validation covered both isolated failure injection and the actual compiled command-line executable. It also damaged and rebuilt disposable copies of the published 3.1.54 recommended package.

## Defects found and fixed during this pass

1. Program files were committed before signed sequence state was saved. A late state-write failure could therefore report failure after a successful update with no rollback data left. State is now persisted while rollback data is still available, and a failed state write rolls back the installation.
2. A committed journal could block the next run when its backup had already been cleaned but the journal deletion was interrupted. Final journals now clean safely without requiring rollback files.
3. A large transaction rewrote its complete JSON journal before and after every file. A nearly empty package would have produced quadratic journal I/O. The complete backed-up plan is now made crash-recoverable with one applying checkpoint.
4. An invalid explicit `--root` could fall through to the working directory and target a different KFPS checkout. An explicit root is now authoritative and rejected when unrecognized.
5. Any existing explicit directory could previously be treated as a package root. Recovery now requires a KFPS package marker.
6. Unsafe updater state locations could overlap or contain the installation. Drive roots, files, ancestors, and descendants of the installation are now rejected before logs or cleanup are created.
7. Windows device names, control characters, invalid characters, trailing spaces/dots, noncanonical ZIP separators, and file/directory archive collisions are now rejected.
8. Direct `MoveFileExW` calls did not opt into extended Windows paths. Replacement now supports tested Unicode and space-containing paths over 260 characters.
9. Read-only managed files could block repair. Their read-only attribute is cleared only when a verified transaction replaces or removes that managed path.
10. Failed transaction preparation could leave partial rollback data until another run. It is now discarded immediately without touching installation files.
11. Future signed application components excluded the inner updater copy. The inner copy is now independently repairable while the native component manages the outer copy.
12. A failed self-update process launch could leave a successful `handoff` report. The same report is now rewritten as failed.
13. Application-side update reports were not bounded. State and application report histories now retain at most 40 recent files and 90 days.
14. The batch wrapper retried the inner updater after any outer failure, potentially masking a real signed-update rejection. It now retries only recognized Windows executable-launch failures.
15. Publisher failures could leave a partial payload directory. Failed publication now removes its incomplete output, validates versions and retired paths, and includes the inner updater in the application component.
16. Forced or fallback recovery could downgrade a newer package. One recovery-eligibility check now evaluates installed version, persistent signed state, and release-manifest evidence on every recovery path.
17. A public `--skip-self-update` flag bypassed the signed minimum bootstrap. The flag was removed and the signed compatibility floor is enforced independently after self-update selection.
18. Lexical path checks could follow symlinks or Windows junctions. Existing ancestors are now rejected across install, state, staging, backup, download, log, cleanup, and report paths. Native Windows junction scenarios wrote zero bytes outside their roots.
19. A crash after `state.json` persistence could roll files back while leaving anti-rollback state advanced. The previous state payload and transition are now durable transaction-journal data.
20. The publisher could sign a version different from packaged `VERSION`. Release version, file bytes, manifest identity, filenames, and state now share one enforced value.
21. Cross-component removals and install/remove conflicts could produce an unrecoverable journal. One global destination preflight now runs before any component download, with transaction-level duplicate defense.
22. Self-update handoff lost package context and could race its parent. It now carries resolved roots, working directory, state, and parent PID; reports remain `handoff-pending` until the child completes.
23. Working-directory discovery could override the updater's own package. Explicit root remains authoritative, then executable-side package is preferred, and every candidate is fully validated before selection.
24. Policy failures could be masked by recovery fallback. Only typed availability failures can trigger automatic fallback.
25. Equal signed sequence numbers could identify different releases. Persistent channel/manifest hashes now make equal-sequence acceptance identity-exact.
26. PID-file ownership was replaced with a held OS lock, and transaction space is checked per storage volume.
27. Large downloads now use activity timeouts and verified range resume. Wrong `Content-Range`, wrong hash, and policy errors fail immediately and discard unsafe partials.
28. Publication now executes updater `--build-info`, validates version/key/platform, snapshots one updater byte stream, includes both package copies, reopens every archive, and validates the final client contract.
29. `--check` now has automation-safe exits: 0 healthy, 3 repair required, 1 operation failure, and 2 invalid command/layout.
30. Production binaries compile test-only custom channel/state/sequence behavior out; the environment variable alone cannot enable it.
31. `updater.lock` is opened with no-follow/reparse semantics and must be a single-link regular file. Windows hard-link and junction probes preserve the outside target.
32. Equal-sequence channel and manifest identities are enforced before any updater download or handoff, including conservative legacy-state handling.
33. Handoff now carries signed size/SHA-256, authenticates through a held OS file handle, verifies Windows file identity/final path, and denies replacement through process creation.
34. Application publication reads directly from an immutable archive of the declared Git commit. Python and updater inputs are copied once into a private snapshot before packaging.
35. Equal-version recovery refuses a different commit identified by persistent state or the installed release manifest.
36. Default state is namespaced by a SHA-256 installation identity, and persisted state is rejected when bound to another package.
37. Executable-side automatic discovery can rebuild a package whose complete `KloudysFH6Painter` directory is missing, without making working-directory discovery equally permissive.
38. A verified `--check` handoff waits and returns the child's exact terminal code. Mutating handoff uses documented exit `4` for pending rather than false success.
39. Redirect-policy rejection remains a policy error and cannot trigger availability recovery fallback.
40. Publisher output is rejected when it overlaps an application or Python source root; the finished private payload is atomically promoted.
41. A directory or non-regular object at a retired-file path produces an explicit manual-remediation error.
42. Build documentation now matches the module's supported Go 1.22 minimum.
43. Flat pre-package releases with a root-level `VERSION` were rejected when `--root` was used. A dropped-in bootstrap now identifies that narrowly defined legacy layout as an incomplete outer package and rebuilds the modern `KloudysFH6Painter` child without deleting legacy-root data. Current source checkouts with `KFPS.UI` retain their existing layout behavior.

## Automated test matrix

The Go test suite exercises:

- Ed25519 acceptance, wrong-key rejection, and payload tamper rejection
- Signed channel and signed manifest loading
- Monotonic sequence rollback rejection
- Verified self-update handoff, matching-version no-op, and updater downgrade refusal
- Full application, Python, and native-launcher component updates
- Same-version repair and healthy second-run no-op
- Dry-run immutability and no sequence-state advancement
- Removal-only updates without component downloads
- Archive size, hash, per-file hash, inventory, traversal, link, duplicate, topology, and canonical-path rejection
- Protected runtime, key, local Worker, image, and generated-cache preservation
- Exact Python cleanup excluding `__pycache__` and `*.pyc`
- Install/retire collisions and cross-component destination collisions
- Apply failure rollback and state-save failure rollback
- Interrupted applying, committed, malformed, outside-root, and missing-backup journals
- Partial preparation cleanup
- Live, dead, and stale malformed updater locks
- Bounded parent-process waiting
- Read-only replacement and rollback
- Unicode, spaces, and a real Windows path longer than 260 characters
- Arbitrary root, broken package marker, drive-root, and overlapping state-path rejection
- HTTPS/local-source policy, secure redirect policy, retries, and failed-partial cleanup
- Interrupted artifact resume and mismatched `Content-Range` rejection
- Recovery downgrade rejection using installed, persistent-state, and release-manifest evidence
- Same-version/different-commit recovery rejection
- Same-sequence/different-identity rejection and no policy-to-recovery fallback
- Same-sequence rejection before self-update selection
- Per-install state namespacing and state/install identity binding
- Missing-application-directory automatic discovery from executable-side markers
- Durable file-plus-state crash rollback
- Windows junction rejection for install, logs, staging, state reports, and application reports
- Lock-leaf hard-link rejection and held-handle handoff replacement rejection
- Publisher updater build identity, exact version, final archive, and destination-collision validation
- Immutable Git snapshot bytes and disjoint publication output
- Healthy/repair-required check exit-code distinction
- Synchronous check-handoff exit propagation and distinct mutating pending status
- Bounded state and application report retention
- Dirty release-source and incorrect-commit publication rejection
- Outer/inner updater selection and source-checkout fallback
- Release bundle inclusion of both updater copies
- Explicit migration from a flat legacy package root without misclassifying a current source checkout
- Untouched 3.1.28 and 3.1.52 BAT delivery of the inner bootstrap and bootstrap-aware UI
- Pinned-recovery compatibility shim, redundant updater-copy repair, and signed BAT retirement
- Frozen historical BAT and launcher identities through `legacy_bridge_contract.json`

Passing commands:

```text
go test ./... -count=1
go test -race ./... -count=1
go vet ./...
py -3 KFPS.UI\tests\test_updater_safety.py -q
py -3 KFPS.UI\tests\test_release_builder.py -q
py -3 -m unittest discover -s KFPS.UI/tests -q
.\tools\bootstrap_updater\tests\run_signed_cli_release_gate.ps1 -KeepArtifacts
.\tools\bootstrap_updater\tests\run_windows_lock_gate.ps1 -KeepArtifacts
.\tools\bootstrap_updater\tests\run_real_recovery_gate.ps1 -Archive C:\path\KFPS-3.1.54-bundled.zip -Updater C:\path\test-enabled-updater.exe
.\tools\bootstrap_updater\tests\run_legacy_bat_bootstrap_gate.ps1 -RecoveryArchive C:\path\KFPS-3.1.54-bundled.zip
```

The complete KFPS suite passed 570 tests. It emitted the pre-existing `datetime.utcnow()` deprecation and shutdown `ResourceWarning`, both outside updater scope. The Go suite also passed three shuffled repetitions and the race detector. Final statement coverage was 60.2% for the publisher command, 34.2% for the CLI command, and 68.1% for the core bootstrap package; executable-level scenarios below cover important process and Windows filesystem boundaries that statement coverage does not count.

## Historical draft-release matrix

`tests/run_historical_release_matrix.ps1` retrieves authenticated draft assets with GitHub CLI, verifies each asset against GitHub's recorded byte size and SHA-256, rejects unsafe ZIP topology, extracts to a disposable directory, and places the exact production bootstrap beside the old installation. Each fixture must pass an immutable dry run, transactional recovery to the pinned 3.1.54 bundle, an independent 9,927-file size/hash audit, protected-data checks, stale-Python cleanup where applicable, and a zero-operation warm check.

| Draft fixture | Original version | Package shape | Check/apply/warm | Final hash failures |
| --- | --- | --- | --- | --- |
| `v3.1.52-advanced` | 3.1.52 | No bundled Python/dependencies | 3 / 0 / 0 | 0 |
| `v3.1.52-bundled` | 3.1.52 | Recommended bundle | 3 / 0 / 0 | 0 |
| `v3.1.28-advanced` | 3.1.28 | No bundled Python/dependencies | 3 / 0 / 0 | 0 |
| `v3.1.28-bundled` | 3.1.28 | Recommended bundle | 3 / 0 / 0 | 0 |
| `v3.1.14-bundled` | 3.1.14 | Recommended bundle | 3 / 0 / 0 | 0 |
| `v3.0.96-bundled` | 3.0.96 | Recommended bundle | 3 / 0 / 0 | 0 |
| `v2.0.59` | 2.0.59 | Legacy nested bundle | 3 / 0 / 0 | 0 |
| `v1.10.75` | 1.10.75 | Legacy nested bundle | 3 / 0 / 0 | 0 |
| `v1.6.1` | 2026.05.24.1 | Flat source-style package | 3 / 0 / 0 | 0 |

The flat 1.6.1 case rebuilt all 9,927 managed files plus the release manifest into the modern child directory while preserving four root-level data markers and the original legacy `VERSION`. Every other fixture preserved runtime data, image data, a supporter-key marker, and generated Python cache data; every fixture that began with a modern Python directory also removed an injected obsolete extension. Successful disposable installations were deleted, while verified source archives and compact logs/JSON remain under `tools/bootstrap_updater/build/historical-release-*`.

The matrix validates recovery after the bootstrap has been placed beside an old installation. The separate legacy bridge gate below validates acquisition through the original BATs. Neither gate alters draft release metadata.

```powershell
.\tools\bootstrap_updater\tests\run_historical_release_matrix.ps1 `
  -RecoveryArchive 'C:\path\KFPS-3.1.54-bundled.zip'
```

## Untouched legacy BAT bridge

`tests/run_legacy_bat_bootstrap_gate.ps1` uses the exact downloaded 3.1.28 and 3.1.52 recommended bundles. It verifies each original BAT SHA-256, points that unmodified BAT at a disposable Git remote containing the candidate source, and exercises the two-stage user path.

Both versions passed:

| Scenario | 3.1.28 | 3.1.52 |
| --- | ---: | ---: |
| Original BAT Git update | 0 | 0 |
| Inner bootstrap acquired with exact candidate hash | Yes | Yes |
| Bootstrap-aware UI service acquired | Yes | Yes |
| Pinned recovery and dependency repair | 0 | 0 |
| Missing inner updater repaired by outer updater | 0 | 0 |
| Reintroduced legacy BATs and missing `cv2.pyd` repaired | 0 | 0 |
| Recovered old UI shim launched bootstrap | 0 | 0 |
| Recovered old UI shim bypassed a corrupt outer updater | 0 | 0 |
| Inner updater repaired the corrupt outer copy | 0 | 0 |
| Recovered old UI shim preserved updater failure exit | 2 | 2 |
| Final warm check | 0 | 0 |
| Final immutable-file mismatches | 0 | 0 |

Each fixture preserved runtime, image, web state, and supporter-key markers. The final independent audit verified 9,925 immutable files, excluding 317 generated Python cache records and the two recovery-bridge BAT paths. Compact final evidence is stored under `tools/bootstrap_updater/build/validation-1.0.1-2026-09-02-final/legacy-bat-bridge`.

## Signed executable release gate

`tools/bootstrap_updater/tests/run_signed_cli_release_gate.ps1` builds two disposable updater executables and a complete three-component update using a new ephemeral test key. It does not use or expose the production private key.

The compiled executable passed:

| Scenario | Result |
| --- | --- |
| Signed dry-run from 1.0.0 to 2.0.0 | Exit 3; 8 replacements and 4 removals reported; target and sequence state unchanged |
| `--check` self-update from bootstrap 1.0.0 | Verified 1.0.1 child ran synchronously; child repair-required exit 3 propagated exactly; target and sequence state unchanged |
| Mutating self-update from bootstrap 1.0.0 | Parent returned pending exit 4; authenticated 1.0.1 child waited for its parent and completed update |
| Full signed apply | 8 files replaced, the compatibility shim, legacy wrapper, fixture retirement, and stale Python file removed; post-install verification passed |
| Healthy repeat | Exit 0; zero operations and no component downloads |
| Same-version damaged file | Exactly one application file downloaded and repaired |
| Sequence 2 state against signed sequence 1 | Exit 1; target file remained untouched; failed JSON report written |

The retained evidence produced eight coherent reports, including the parent and child check-handoff records, one pending mutating handoff, completed child/normal runs, and one expected rollback-sequence rejection. Compact logs and reports are stored under `tools/bootstrap_updater/build/validation-1.0.1-2026-09-02-final`.

## Published 3.1.54 package recovery

The local published bundle was independently verified before use:

- Size: `422238121` bytes
- SHA-256: `551f4052ee8f6707d7c7e24fb7b42ed74be9bfac45e3cfdd7281ca773e1ad0ec`
- Managed program files: 9,927

### Stock-package migration

The rebuilt executable checked the extracted recommended package, then planned three updater/shim replacements and one legacy-wrapper removal. The real run installed matching inner and outer updater copies, replaced the old Git BAT with the bootstrap shim, removed the wrapper, and passed a zero-operation warm check.

### Deliberately damaged package

Damage included:

- Corrupt, read-only outer `KFPS.exe`
- Missing `update_service.py`
- Missing `cv2.pyd`
- Missing `opencv_videoio_ffmpeg4100_64.dll`
- One obsolete Python extension

Test-only runtime data, a `.kfpskey`, and generated Python bytecode were added before repair. The dry-run reported four replacements and one removal and changed nothing. The real run repaired exactly those four files, removed the obsolete Python file, restored every reference SHA-256, preserved all three protected files, and left no journal, staging run, or rollback backup. The next run was a zero-operation no-op.

### Nearly empty package

A disposable package contained only `KFPS-Updater.exe`, runtime test data, a test key, generated bytecode, and one obsolete Python file. Recovery:

- Replaced 9,928 program and migration files
- Removed the one obsolete Python file
- Produced a valid 3.1.54 package with outer and inner launchers, Python, and OpenCV
- Preserved runtime data, the key, generated cache, and bootstrap marker
- Left no active journal or rollback backup

This is the tested worst-case local rebuild path, not only a one-file repair.

The current bootstrap 1.0.1 recovery gate completed all migration, repair, and nearly empty rebuild scenarios. The release manifest declared 10,244 files: 9,925 immutable files were independently verified after excluding 317 generated Python-cache records and the two migration-owned BAT paths. Both repaired and nearly empty scenarios had zero size/SHA-256 failures, preserved runtime/key/cache fixtures, removed stale Python files, and ended with clean zero-operation checks. The gate wrote eight JSON reports and left no active journal or rollback backup.

### Public HTTPS recovery

An earlier executable-level pass downloaded the pinned public archive from GitHub, received exactly 422,238,121 bytes with progress reporting, verified its embedded size and SHA-256, repaired one missing program file, and preserved user data. The current pass reused the exact verified local archive to avoid another 422 MB download.

## Negative command-line tests

- Invalid explicit root: exit 2; no fallback to the current checkout; no state directory created
- State directory inside the package: exit 2 before log/state creation
- Bad local recovery archive: rejected before installation changes
- Invalid channel signature: rejected before component processing
- Wrong component inventory: rejected before transaction creation
- Protected retired path: rejected and preserved
- Live updater lock: bounded refusal
- Dead or stale malformed lock: reclaimed
- Hard-linked lock leaf: rejected; outside file unchanged
- NTFS junction at the lock leaf: exit 1; outside directory and marker unchanged
- State persistence failure after apply: installation rolled back and state not advanced
- Newer installed/state evidence with forced recovery: downgrade rejected
- Removed minimum-bootstrap bypass flag: exit 2
- Production custom channel/state attempt with test environment set: exit 2
- Install, log, staging, primary-report, and application-report junctions: exit/skip before external writes; outside content unchanged
- Wrong or missing updater publication identity: payload build rejected
- Mismatched HTTP range resume: partial rejected and no destination installed

## Executable inspection

The production build is Windows x64 PE, console subsystem version 6.1, built with `CGO_ENABLED=0`, `-trimpath`, no VCS paths, and stripped symbols. Its only imported DLL is `kernel32.dll`. It has no Python, Node.js, Git, .NET, PowerShell, or Visual C++ runtime dependency.

The audit source ZIP was also extracted outside the KFPS repository and built with its included `build.ps1`. Its Go tests and static checks passed, the script explicitly reported that the absent pair of repository-level Python integration tests was skipped, and it reproduced the exact production executable SHA-256 below. The complete repository build separately passed all 16 of those Python integration tests. `Compress-Archive` records package timestamps, so independently rebuilt ZIP container hashes are not reproducible; compare the executable hash and the ZIP's internal `SHA256SUMS.txt` instead.

The standalone ZIP contains only:

- `KFPS-Updater.exe`
- `README.txt`
- `SHA256SUMS.txt`

Final local build artifacts from this pass:

- `KFPS-Updater.exe`: 7,303,680 bytes; SHA-256 `f4a2fd7a732e2eaa5376cdd022d466b9d5da34d37d02a34328f1edfdeb18d563`
- `KFPS-Bootstrap-Updater-1.0.1-Windows-x64.zip`: SHA-256 `4249e6d208a608a3625c958476c5984bce33e8f9193f737b30f320d9617442bf`
- The updater bytes inside the ZIP match the root executable exactly, and `SHA256SUMS.txt` names the same hash.

## External gates that cannot be proven on this host

These remain explicit staging checks rather than local assumptions:

- Microsoft reputation/SmartScreen and third-party antivirus behavior on clean machines
- ACL behavior under a genuinely non-elevated restricted `Program Files` installation
- A genuinely full disk during staging, backup, and apply
- Forced power loss or process termination during a real 9,000-file apply; equivalent journal states are covered by deterministic recovery tests
- Another physical drive, UNC path, and removable media
- Windows 11 and other supported Windows builds
- A production-key stable-channel deployment through the final public URLs
- GUI relaunch/focus behavior across varied user desktops; process waiting and non-GUI relaunch mechanics are covered locally
- A true Windows file-symlink lock fixture under an account with symlink privilege; hard-link and NTFS-junction variants passed here

These are the only remaining environment-dependent gates found in this audit.
