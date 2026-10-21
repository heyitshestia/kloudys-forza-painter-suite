# Offline Transfer Improvements

## Scope and State

This work is prepared for KFPS 3.1.113. Development and background validation
were performed in DIRTY before a reviewed source-only promotion to CLEAN.
Live-memory transfer and personal installations are unchanged. The original
implementation used synthetic saves; the separately authorized FH6 qualification
below added backed-up test entries without replacing existing game saves.
The supported games remain FH4, FH5, FH6 and FM8. Microsoft Store and Steam
support follows verified save layouts, not merely a game's capability flag.
Studio section exports reuse validation and preserve individual placements as
groups; native full-livery authoring is not rewritten in this task.

Baseline: 50 offline tests and 103 group/library/live-policy regression tests pass.
The latter use mocked memory, not a running game. Existing datetime deprecation
and Qt shutdown resource warnings occur before this change.
Scoped original files and test artifacts: `runtime/offline-transfer-20261020/`.

## FH6 Grouped-File Qualification Follow-Up (2026-10-21)

The first real-game section-vinyl test rejected an exported Top group. Investigation
found missing native traversal framing in the new grouped writer: child-group
transforms, group closes and first-shape control placement. Local recovery-decoder
round trips had not detected this malformed representation.

DIRTY now emits explicit identity transforms and closing records while preserving
the same shape bodies and group membership. The existing flat exporter is unchanged.
Independent synthetic framing tests reproduce the old failure; the strict check
also consumes a privately retained original game-saved nested group. No private
save or artwork is included in the product tests.

All 41 original test exports have been re-encoded locally with unchanged geometry,
colours, masks and groups. The focused correction passes 174 regression tests.
On 2026-10-21 the user confirmed that the corrected two-group Top canary loads in
FH6. That is user-reported game acceptance, separate from automated file checks.
The same user authorized remaking the remaining 40 entries as new copies. All
40 were added and independently verified, with a fresh byte-verified backup and
all pre-existing files unchanged. The working Top is retained; the earlier failed
entries were never overwritten. Corrected names and references are in the local
qualification page and CSV, separate from the immutable original-batch receipts.
The failure was native record framing, not artwork resolution or a need to flatten
groups. Recovery-decoder success alone was an insufficient validation gate.
The user subsequently confirmed successful loading, accurate alignment and
ungrouping on all four tested cars. The Nissan design was saved in-game and its
581 shapes across ten sections independently read back with matching ordered
types, colours, masks, positions and effective transforms (using the existing
Spoiler section-coordinate convention). No save files were changed during that
readback. Restart/undo persistence, the other three cars' saved-file readback,
other vehicles/parts and other games remain separate qualification gaps. These
results do not qualify the experimental direct full-livery authoring exporter.
The local qualification record is under
`tools/livery-studio/runs/grouped-sections-20261021/diagnosis/` (private, ignored).

## Milestones

### Group-Preserving Finished Exports (2026-10-21)

- The editor's normal **Export JSON** already keeps nested group membership and
  names in the existing optional `editor_group_*` fields. Saving the editable
  project remains necessary for reference images and other project-only state.
  The normal export and its download-recovery copy use the same grouped payload.
- Offline game-vinyl extraction already retains native groups. Re-scan the save
  library and reopen the extracted JSON in the editor. Native files do not retain
  custom editor group names, so recovered groups use generic names.
- Full saved-livery **JSON extraction** now also keeps groups, with unique IDs
  across car sections and no artificial group for a section's structural wrapper.
  This is the existing `tools.cgroup.export_forza_source_to_kfps_json` file-tool
  path, not a new Workshop button or a new full-car authoring capability.
  Native package export already retains the original save bytes; its canonical
  JSON/rendering contract remains unchanged for backward compatibility.
- Old JSON that has already been flattened cannot reconstruct its group tree.
  Re-export from the original grouped project or original owned game save.
  Live-memory import/export is unchanged and still flat.

Validation: 177 offline/decoder/privacy/package/project-store tests passed;
nine HTTP export tests passed (one unrelated cross-drive test skipped on C:);
18 Studio section-export tests passed. Three editor Node suites passed, covering
the real finished-export handler, fallback, group editing and 1,275 membership
combinations. HTTP coverage saves/reopens nested and loose shapes, retries without
duplicates and recovers on-disk receipts. These are background integration/unit
checks, not a fresh foreground native/Chrome UI or in-game acceptance test.

The frozen user-verified Nissan save exported 581 shapes across ten sections with
30 distinct groups. All ordered placement data matched the pre-change decoder
exactly; default package decoding also matched exactly. Every section re-encoded
with three native groups (the game-added placement wrapper plus its two children)
and passed independent strict framing and effective-geometry verification.
No game saves were written. Evidence: `runtime/offline-group-exports-20261021/`.

The user subsequently verified the editor-made 12-shape nested-vinyl round trip
through FH6. Two five-shape parent groups retained their nested three-shape
groups; the two loose shapes remained outside them. The game regenerated group
names and omitted an outer placement wrapper. The recovered editor hierarchy
was explicitly accepted. Direct full-car authoring remains a separate
experimental qualification; section-vinyl success does not unlock it.

### Latest FLS Review and Save Locations (2026-10-21)

FLS was fetched to `0a202d19b3991a6cb3d714ffd10cbe824e932ce9`, three commits
after the previous transfer audit. The changes reorganize framing/encoding;
they do not justify replacing KFPS's game-verified FH6 encoder. No AGPL source
was copied. The current FLS shortcut chooses the newest C-drive PGS slot; KFPS
retains multi-drive, multi-account discovery and explicit write destinations.

- FH6/PGS scanning now accepts a selected GameSave root, PGS root, account,
  save slot, ContainersRoot or individual LayerGroup folder. Subfolder scans
  stay within the selected subtree. Overlapping roots are deduplicated.
- FH4 recognized WGS/Steam save roots are no longer truncated by the generic
  60,000-file/18-second scan budget. Unrecognized folders retain that budget.
- FM8 native and packaged UGC roots remain valid when restored from the cache.
- FH4/FH5 Steam discovery retains separate accounts for app IDs `1293830` and
  `1551360`. FM8 keeps its separate UGC layout and app ID `2440510`.
- Encoded offline vinyls now verify exact nested leaf membership, not only
  counts and geometry. Mask helper groups and same-range nested groups are
  included. The proven wire format is unchanged.
- Outputs now offers **Open in Editor** for one selected JSON, using the
  configured native or Chrome editor. Unsaved-work confirmation and scoped
  file access remain enforced; the source JSON is not overwritten.

FLS's FH5 WGS writer replaces a selected slot. KFPS keeps its additive,
backed-up transaction instead. Neither FLS support nor our synthetic checks
establish game/cloud acceptance for KFPS's FH4/FH5 experimental import paths.

1. Complete: preserve ordered nested vinyl groups through native save and editor JSON
   round trips. Verify geometry, colour, masks, shape identity and layer order
   for all four games, including 3,000 shapes. Keep flat exports compatible.
2. Complete as a labelled test path: FH5 Microsoft Store/Xbox WGS imports.
   Preserve ownership checks, backups, cancellation, concurrency checks and
   rollback.
3. Complete: real application paths and synthetic-save regression tests.
   Remaining in-game qualification gaps are listed below. No real save writes.
4. Complete as labelled test paths: FH4/FH5 Steam import destinations, with
   explicit template/account selection and verified additive transactions.
   See [Steam workflow and evidence](FH45-STEAM-OFFLINE.md).

## Design and Provenance

FLS reference: https://github.com/Arstz/ForzaLiveryStudio/tree/0a202d19b3991a6cb3d714ffd10cbe824e932ce9
Its AGPL implementation is not copied. Format observations from `docs/CGROUP.md`
are checked against KFPS's pre-existing decoder and independently generated
fixtures. KFPS keeps its existing architecture and MIT implementation.

Alternatives: replacing the transfer stack with FLS would introduce a licensing
and architecture change; preserving original native bytes would fail after edits.
The selected approach retains the KFPS flat shape representation, carries its
existing optional editor group paths, and emits identity-transform native groups.
Geometry remains in the leaves. Interleaved editor groups must not reorder art.

## Lookback

The problem is transfer fidelity and save safety, not rendering or live memory.
Existing editor group metadata and the native tree decoder remove the need for a
new project format. Synthetic round trips can detect encoding mistakes but do
not prove that a game indexes or renders the exported save correctly. In-game
acceptance must remain explicitly unverified until tested there.

## Initial Validation

All runs were background/offscreen, using synthetic files and mocked dialogs.
The real service workers, asynchronous UI action, decoder and thumbnail renderer
were exercised. No real game account, cloud binding, or production save was used.
The subsequent Steam extension also validated read-only copies of native FH5
vinyls. Its 184-test regression and remaining limitations are documented separately.

| Suite | Result | Evidence in runtime/offline-transfer-20261020 |
| --- | --- | --- |
| Offline import/export | 95 passed | offline-tests.log |
| Group/library/live-policy regressions | 112 passed | group-tests.log |
| Game adapters and store discovery | 10 passed | adapter-tests.log |
| Editor JavaScript syntax and unit suites | 74 checks passed | editor-unit.log |
| Studio exports | 23 passed | studio-export-tests.log |
| Studio native save codec | 12 passed | studio-save-tests.log |

Counts overlap between offline and group suites and must not be added as unique
test totals. Existing datetime deprecation and Qt shutdown resource warnings
remain. The first editor run omitted its required Python environment variable;
the corrected run passed. An old FH5-disabled test was updated to mock the new
confirmation; its offscreen blocked run was stopped and rerun successfully.

Coverage includes 3,000 shapes for all four game encodings, 64-level grouping,
interleaved groups, mirrored/skewed geometry, terminal/nested and zero-alpha
masks, malformed flags, old flat bytes, public worker dispatch, explicit account
selection, cancellation, game-start races, corrupt backup/readback, concurrent
writers, failed commit, failed rollback and retained recovery material. The
review-found malformed-mask coercion was fixed and regression-tested.

## What Is Ready to Test

- FH6 and FM8: existing Microsoft Store/Steam-compatible local save layouts now
  use grouped encoding and stricter round-trip validation. File verification
  still does not prove the game discovers or renders a newly added group.
- FH4: existing Microsoft Store/Xbox WGS path gains grouped encoding, verified
  full-slot backup, cooperative writer locking, repeated readiness checks and
  semantic verification inside rollback. Steam (Test) now adds a separate
  destination using an explicitly selected owned draft header.
- FH5: **FH5 WGS Import (Test)** adds a new group to the explicitly selected
  account. It does not replace the selected donor. The 53-byte v4/v6 draft
  header and equal-GUID three-blob WGS layout are required; unknown formats fail
  closed. Native/cloud acceptance is not yet qualified. Steam (Test) is now
  available; Helium/PGS writes remain unavailable. Live import stays available.
- Studio: exporting a section as vinyl JSON keeps each placed vinyl together
  and validates it for offline transfer. Full-car authoring/export remains
  subject to its existing experimental guards; no new compatibility claim.

## Manual Qualification

1. Start KFPS normally; select a small grouped JSON with a known mask.
2. Use its existing offline import for FH4, FH6 or FM8. FH4 WGS still requires
   the game closed; additive FH6/FM8 imports still allow it to remain open.
3. For FH5 Microsoft Store/Xbox only, save a small owned test vinyl in-game,
   close the game and wait for cloud sync. Choose FH5 WGS Import (Test), read the
   confirmation and select that vinyl's active container.N beneath
   `%LOCALAPPDATA%/Packages/Microsoft.624F8B84B80_8wekyb3d8bbwe/SystemAppData/wgs/`.
   Do not pick containers.index or a different account. Unsupported selections
   do not fall back to another account. The result reports its backup location.
4. Check the imported artwork in-game for visibility, shape order, transforms,
   group behavior and mask clipping; save it there. Scan the save library again
   and reopen the exported JSON in the editor. Group names become generic because
   the native format does not store the KFPS names. Test a 3,000-shape example only
   after the small example behaves correctly. Verify cloud/restart behavior too.
5. In Studio, export a side containing two placed vinyls, open the section JSON
   in the editor and verify two separate placement groups before importing it.
6. For FH4/FH5 Steam, follow [the Steam test workflow](FH45-STEAM-OFFLINE.md#usage).
   Close the game, finish synchronization and exit Steam before the file transaction.

Do not publish this as universally game-qualified on the strength of synthetic
tests. A changing WGS save aborts; a failed/conflicting rollback reports retained
paths. No automatic restore over newer cloud data, and no power-loss journal.

## Artifact and Change Index

- Encoding and grouping: tools/cgroup/{vinyl_document,cgroup_codec,forza_source_decoder}.py.
- Transactions/FH5: tools/cgroup/{xbox_wgs,fh5_offline}.py.
- Steam follow-up: tools/cgroup/{steam_offline,horizon_vinyl_header}.py, import
  destination UI and test_steam_offline_transfer.py. Details and hashes under
  runtime/offline-transfer-20261020/steam/.
- Product integration: KFPS.UI/src/kfps_ui/cgroup_library_service.py,
  game_adapters/registry.py, KFPS.Editor/web/{editor,editor-layer-groups}.js.
- Editor messages: KFPS.Editor/web/locales/{en,ko,ja}.{json,js}; catalog build passed.
- Studio: tools/livery-studio/src/kfps_livery_lab/save_codec.py.
- Regression tests: new UI offline_vinyl_codec, offline_grouped_services and
  fh5_offline_transfer tests; existing game_adapters and cgroup_library_access
  tests; editor-offline-groups.node.js; Studio test_section_export and test_save_codec.
- Documentation: this file and tools/cgroup/README.md.
- Originals: runtime/offline-transfer-20261020/baseline/ and
  backups/fh5-wgs-before-01/. See baseline-files.json and FH5-WGS-HANDOFF.md.
- Scoped final hashes: runtime/offline-transfer-20261020/changed-files.json.

Final lookback: transfer fidelity and safety improved without replacing the
renderer, live-memory code or native full-car exporter. Strict input validation
and data-preserving failure behavior are verified; game acceptance is a separate
remaining test, especially FH5's additive registration. Existing local work was
preserved, no nested clone/dependencies were added, and temporary fixtures were
automatically removed except the interrupted access-test fixture
`%TEMP%/kfps-library-access-vwtg7eeh`. It contains only synthetic test data;
explicit cleanup was blocked by the tool policy and was not retried. Those were
the initial development results; the publication follow-up is recorded above.
Personal installations, live game saves and Cloudflare are outside this push.
