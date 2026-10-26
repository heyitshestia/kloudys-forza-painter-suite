# FH3 Offline Vinyl Export

FH3 supports export **from local game saves into KFPS**. It is not a live-memory
target or an import destination. Existing FH4, FH5, FH6 and FM8 routes are unchanged.

## Batch Workflow

1. Save your vinyl groups in FH3, close the game and let cloud synchronization finish.
2. Open **Outputs**, choose **FH3** under **Offline game**, then **Scan FH3 Saves**.
3. KFPS batch-extracts every supported, readable owned vinyl group into **Library**.
4. Select an extracted item and right-click **Open in Editor**. Nested groups,
   loose shapes, colours and transforms are retained.

Automatic discovery searches the current Windows user's package storage:

`%LOCALAPPDATA%\Packages\Microsoft.OpusPG_8wekyb3d8bbwe\SystemAppData\wgs`

This is separate from the game installation and does not depend on its drive.
The newer `C:\XboxGames\GameSave\pgs\u_*\current\ContainersRoot` layout is not
FH3's normal location. No game launch, Xbox login or cloud downloader is required;
the saves must already be present locally.

**Save folder** batch-reads a chosen WGS root/profile, copied package folder, or
folder of extracted `C_group`/`header` pairs. A successful choice is remembered
across restarts. **Extract file** is an optional single-file fallback for an
already-extracted `C_group`, not a required step for each vinyl.

## Safety And Compatibility

- Game saves, container indexes, identity and cloud state are never written.
- WGS index-v14 and descriptor-v4 are supported. Only the registered active
  descriptor and current blob GUID are used; stale files are not guessed.
- Package identity, header version/count and payload structure are checked.
- Index, descriptor, header and payload hashes are rechecked before each commit.
- Unchanged rescans reuse Library entries. Edited Library copies are not overwritten.
- A damaged or protected entry is reported without hiding healthy entries.
- Cancellation retains completed entries and discards incomplete staging.
- FH3 generation-1/2 standalone vinyls and header-v1 are supported, up to 3000
  shapes and 64 nesting levels. Unsupported or incomplete records are rejected
  instead of silently dropping artwork. Masks and full-car liveries are not
  part of this extraction route.
- A recipient reports that FH3 extraction works. Nested-group handling also has
  automated coverage; this does not establish compatibility with every
  historical save or vinyl type.

If a scan fails, use the manual folder fallback and include its displayed error
in a private problem report. Do not share account credentials or complete saves
publicly. Reports and save metadata can contain local paths and account identifiers.

## Implementation And Tests

The FH3 acquisition module reuses KFPS's existing strict WGS parser and source
decoder. No external implementation was copied and no dependency was added.
The registry advertises offline export only. An internal legacy encoder is
retained for synthetic compatibility tests; it does not install FH3 saves.

Primary format references reviewed:
- [FLS source](https://github.com/Arstz/ForzaLiveryStudio), commit
  `0a202d19b3991a6cb3d714ffd10cbe824e932ce9`, WGS reader and import locations.
- [Xbox save format](https://github.com/Fr33dan/GPSaveConverter/wiki/Xbox-Save-Format).

Tests: `test_fh3_offline_files.py`, `test_fh3_save_discovery.py`, and
`test_fh3_offline_ui.py`. Coverage includes synthetic independent fixtures,
3000-shape/nested documents, corrupt or changed saves, locked records, rescans,
cancellation, manual-path persistence, current-game conversions and real native
Outputs controls at two sizes and 100%/150% scaling. Tests never use personal saves.
