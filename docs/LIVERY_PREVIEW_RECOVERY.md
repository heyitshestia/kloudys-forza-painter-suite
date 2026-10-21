# Recovering A Failed Livery Preview

KFPS 3.1.109 fixes the missing-file error caused by long generated preview paths.
It also fixes High-quality preview recovery after rebuilding the car index and
prevents delayed cache cleanup from reopening an obsolete selection.

## What To Do

1. Update KFPS to 3.1.109 or newer, then restart KFPS.
2. Open Liveries, select the affected livery, and choose Open 3D Preview again.
3. If it still needs rebuilding, select that livery and choose Clear Cache once.
   KFPS rebuilds and reopens the selected preview automatically.

There is no need to re-export the livery, move KFPS, change Windows settings, or
close the game. The operation regenerates derived preview files; it does not
rewrite game saves or exported livery packages.

If the error persists, send a fresh Report a Problem with the new error and
KFPS version. A corrupt package, unavailable game archive, unsupported format,
or ownership restriction still requires its own diagnosis.

## Cache Compatibility

New read-only previews use `runtime/lv/<installation-id>/cars/<car-id>` inside
KFPS. The old `tools/livery-studio/runs/readonly-viewer/<installation-id>` cache
remains recognized and shares the existing cleanup and storage budget.

Only recognized generated files are removed. Unknown files, foreign ownership,
redirected paths, and modified cache inventories remain protected. Do not place
personal files inside the generated cache directories.

Temporary writes use short, exclusively created names beside their destination.
Failed writes preserve the previous file. Full descriptor hashes and integrity
checks are unchanged; rendering quality, UVs and livery formats are unchanged.

This addresses preview preparation and recovery, not every Windows long-path
limitation. It does not certify arbitrary-depth Qt loading, Explorer extraction,
third-party tools, or network shares.
