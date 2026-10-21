# FH4/FH5 Steam offline transfers

## Scope and checkpoints

Developed and tested in DIRTY, then prepared for source-only promotion in 3.1.113.
No real saves, personal installations or remote services are changed by tests.
Run evidence and pre-edit backups: `runtime/offline-transfer-20261020/steam/`.

1. Establish the flat Steam file layout and validate available native files.
2. Add explicit Steam routing, bounded identity validation and additive writes.
3. Exercise the actual service, rescan exported files, and test failures and
   compatibility. Native game visibility remains a separate qualification.

## Format evidence and decisions

- Existing FH5 Steam saves contain `LayerGroup_0000_<YYYYMMDDHHMMSS>.C_group`,
  `.header` and `.thumb.png` in the numeric account folder below `remote`.
- The existing decoder successfully reads owned native FH5 groups with no
  structural warnings. Both v4 and v6 headers occur locally; only validated,
  unpublished, owned templates are acceptable.
- FLS's [header format](https://github.com/Arstz/ForzaLiveryStudio/blob/main/docs/HEADER.md)
  documents v4 for FH4 and v6 for FH5, with the same bounded draft tail.
  Its [group format](https://github.com/Arstz/ForzaLiveryStudio/blob/main/docs/CGROUP.md)
  describes the shared payload wrapper. These are format references, not copied
  implementation. FLS is AGPL-3.0; no FLS source is incorporated.
- Additive files are preferable to replacing an existing vinyl. Steam's
  `remotecache.vdf`, game profiles and cloud metadata must not be edited.
- A destination is selected through an owned template header, not guessed from
  the first installed account. Foreign, locked, published, malformed or linked
  templates are refused. FH4 requires v4; FH5 accepts v4/v6 and emits v6.
- No local FH4 Steam save is available. Synthetic v4 tests are not proof of FH4
  native game acceptance. Neither game's cloud acceptance can be proven by a
  file round trip alone.

## Lookback

The actual missing functionality is the Steam destination writer, not another
vinyl encoder. Reuse the newly validated group codec and existing scan/export
path. Do not change WGS transactions or live-memory behavior. If native files do
not satisfy a verified format, fail with guidance rather than inventing fields.

## Usage

1. In the game, save a small, unpublished vinyl of your own.
2. Close the game, finish Steam cloud synchronization, then exit Steam.
3. In KFPS, select the JSON in Outputs and choose FH4 or FH5 under Offline game.
4. Set Import to **Steam (Test)** and click the import button.
5. Confirm the warning and select your saved vinyl's `.header`. Its folder is
   `Steam/userdata/<Steam user>/<app ID>/remote/<Xbox account>/`.
   App IDs: FH4 `1293830`, FH5 `1551360`. The selected vinyl is not replaced.
6. Start Steam and check My Vinyl Groups. Verify groups, masks, transforms and
   colours, save the result in-game, restart, then Scan Saves to round-trip it.

Scanning/export already reads both stores and does not require the import store
selector. Studio section JSON uses the same import path. This does not enable
new full-car Studio exports into FH4/FH5.

## Safety and recovery

The complete selected flat account is backed up with SHA-256 verification under
`runtime/fh4-steam-import-backups/` or `runtime/fh5-steam-import-backups/`.
The transaction manifest lists original hashes and the three new file names.
`committed.json` records a verified completed transaction. Existing files,
profiles and `remotecache.vdf` are never replaced or repaired automatically.

Each filename and asset identity is fresh. Windows no-overwrite renames publish
the thumbnail, C_group, then header. Input and final files are decoded and checked.
Cancellation is honored until publication; a late cancellation cannot misreport
a committed import as doing nothing. Concurrent changes abort. Rollback removes
only unchanged files created by that transaction; changed files are preserved
with a recovery error and the backup location.

These three writes are NOT collectively atomic. Power loss/process termination
can leave an incomplete new entry or staging directory. Keep the game and Steam
closed, consult the recorded transaction before retrying, and remove only the
listed new files whose hashes still match that transaction. Do not restore an
entire old account over newer game/cloud progress. Unknown/changed files require
manual inspection. Retained `.kfps-stage-*` directories block another import.

The bounded backup currently permits a flat account of at most 50,000 files,
8 GiB total and 2 GiB per file. Unknown header tails, incomplete companions,
foreign ownership, locked payloads, linked paths and nested account layouts
fail closed. Save a simple owned draft if the selected template is unsupported.

## Validation and outcome

- **184 tests passed**, zero failures/errors/skips:
  `runtime/offline-transfer-20261020/steam/regression-tests.log`.
  Includes all offline suites, store discovery, key-neutral access, help and QML
  contracts, plus 20 Steam test methods covering both games.
- The real asynchronous import action, actual thumbnail renderer and subsequent
  library scan/export passed for both games using synthetic Steam accounts.
  Repeated imports, Unicode titles, fresh GUIDs, groups, terminal zero-alpha masks
  and 3,000-shape documents are covered.
- Backup corruption, wrong accounts/games, hard links, missing files, cancellation,
  concurrent file creation, disk errors, post-commit decode failures, foreign
  edits and incomplete-stage recovery were exercised.
- **17 copied native FH5 vinyls, 17,855 layers**, successfully re-encoded, imported,
  and reopened. Real source files were read-only and rechecked afterward.
  Of 48 inspected candidates, 25 had unqualified header tails, one was published,
  three had another account identity, and two had nonstandard filenames. These
  were rejected, not silently modified. Evidence: `steam/native-validation.json`.
- Outputs QML compiled offscreen. Dialogs were mocked; no foreground UI, live
  game, cloud synchronization, or FH4 native-save acceptance was tested.
- Existing datetime/Qt shutdown warnings remain. An initial test exposed an
  inconsistent malformed-PNG exception; normalized and rerun successfully.

Final lookback: Steam needed a destination writer and selection UI, not another
renderer/encoder. Native readback supports the bounded FH5 contract. It does not
prove game discovery or cloud acceptance; the **Test** labels remain. FH4
acceptance is specifically unverified without a local native save. These are
labelled test destinations, not a claim of native/cloud qualification.

## Changed-file index

- `tools/cgroup/steam_offline.py`: explicit destination validation and transaction.
- `tools/cgroup/horizon_vinyl_header.py`: shared FH4/FH5 bounded draft metadata.
- `tools/cgroup/fh5_offline.py`: compatibility wrappers using the shared metadata;
  WGS transaction behavior is unchanged.
- `KFPS.UI/src/kfps_ui/cgroup_library_service.py`, `game_adapters/registry.py`:
  Steam dispatch, process guard and capability/help text.
- `KFPS.UI/qml/pages/JsonPage.qml`: theme-compatible import destination selector.
- `KFPS.UI/help/topics.json`: accurate user workflow and compatibility boundaries.
- `KFPS.UI/tests/test_steam_offline_transfer.py`, `test_help_accuracy.py`,
  `test_qml_refinement.py`: transaction, integration and UI/help regressions.
- This document and `OFFLINE-TRANSFER-IMPROVEMENTS.md`.
- `runtime/offline-transfer-20261020/steam/baseline-files.json` and `baseline/`:
  pre-edit hashes/files. `steam/changed-files.json`: scoped final file hashes.
