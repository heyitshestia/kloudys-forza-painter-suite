# KFPS C_group Prototype Tools

These tools are isolated prototypes. They do not change the default live memory
importer/exporter and should not be wired into the UI until validated in game.

## Tools

- `shape_identity.py`: canonical shape identity helpers.
- `cgroup_codec.py`: flat `C_group` encoder/decoder.
- `export_kfps_json_to_cgroup.py`: KFPS JSON to flat `C_group`.
- `import_cgroup_to_kfps_json.py`: flat `C_group` to KFPS JSON.
- `audit_shape_identity.py`: identity conflict and round-trip report.
- `forza_source_decoder.py`: export-only decoder for real `C_group`/`C_livery`
  file artifacts.
- `export_forza_source_to_kfps_json.py`: real `C_group`/`C_livery` file/folder
  to KFPS JSON.
- `find_forza_sources.py`: helper to locate `C_group`/`C_livery` files under
  common Windows save/download/desktop roots.
- `xbox_wgs.py`: strict FH4 Microsoft Store/Xbox WGS metadata reader and
  additive layer-group writer.

## FH4 Xbox WGS Safety Contract

FH4 Microsoft Store/Xbox vinyl groups are stored behind opaque filenames in an
Xbox WGS account slot. `xbox_wgs.py` resolves the logical `C_group`, `header`,
and `thumb.png` files through `containers.index` and each `container.N` file.
It is isolated from the general C_group codec and does not alter live-memory
transfer.

Before an offline import commits anything, KFPS requires all of the following:

- FH4 is fully closed.
- The existing index and template file list parse and serialize byte-for-byte.
- The generated FH4 `C_group` independently decodes to the expected layer count.
- The complete WGS account slot is copied to
  `runtime/fh4-offline-import-backups`.
- A second full-slot fingerprint confirms the save did not change during backup.
- A new container is staged and verified without overwriting an existing group.
- The final index replacement is atomic and the committed logical files reopen
  with their exact staged bytes.

Any staging or verification failure removes the new container and restores the
original index. FH4 WGS import is intentionally additive; KFPS does not replace
or delete an existing FH4 vinyl group.

The format implementation was independently verified against local FH4 files.
The following projects were used only as format-behavior references; no source
code was copied:

- `tylercamp/palcalc` (MIT): Xbox WGS parsing reference.
- `HarukaMa/palworld-xgp-import` (Unlicense): Xbox WGS write-behavior reference.
- `Arstz/ForzaLiveryStudio` (AGPL-3.0): Forza file-tooling comparison; it does
  not currently supply KFPS's WGS writer.

## Export From Real Forza Files

This is the useful path for shape identity work. It uses the game/save artifact
as source truth instead of trusting a KFPS JSON.

Find possible source files:

```bash
python -m tools.cgroup.find_forza_sources \
  C:\XboxGames \
  --expected-layers 285 \
  --output runtime/cgroup-prototype/source-scan.json
```

If you know the game saves are under `C:\XboxGames`, pass that folder
explicitly. It avoids wasting time in Desktop/Downloads/Documents and makes the
scanner identify the newest matching save much faster.

The finder prints a readable list sorted newest first. Use the `MATCH` entry
whose decoded layer count matches the visible layer count in the game and whose
modified time matches the save you just made. Each entry includes:

- a candidate number,
- `C_group` / `C_livery` kind,
- decoded layer count when it can be inspected,
- last modified time,
- file size,
- a short file fingerprint,
- nearby sibling file hints,
- the exact export command for that candidate.

If you only want raw JSON on stdout, add `--json`. If you want file metadata
without decoding payloads, add `--no-inspect`.

When `--expected-layers` is set, the finder stops after the first exact newest
match by default. Add `--keep-scanning-after-match` only if you want a longer
comparison list.

Export a folder containing `C_group` or `C_livery`:

```bash
python -m tools.cgroup.export_forza_source_to_kfps_json \
  "path/to/folder-containing-C_group" \
  runtime/cgroup-prototype/exported-from-real-cgroup.json
```

Export a direct file:

```bash
python -m tools.cgroup.export_forza_source_to_kfps_json \
  "path/to/C_group" \
  runtime/cgroup-prototype/exported-from-real-cgroup.json
```

The exporter writes a sibling `.report.json` with decode details, warnings,
section counts for `C_livery`, and ambiguous shape-word/resource matches.

Privacy guard: by default the prototype refuses known locked payload markers:

- `C_group` payload byte `0x1D == 0x21`
- `C_livery` decompressed `u32` at offset `0x08 == 1`

There is a development-only `--allow-locked` flag, but public builds should not
use it.

## Example

```bash
python -m tools.cgroup.export_kfps_json_to_cgroup \
  assets/app/KFPS\ Logo.json \
  runtime/cgroup-prototype/kfps-logo-flat \
  --report runtime/cgroup-prototype/kfps-logo-flat.report.json

python -m tools.cgroup.import_cgroup_to_kfps_json \
  runtime/cgroup-prototype/kfps-logo-flat/C_group \
  runtime/cgroup-prototype/kfps-logo-flat.roundtrip.json

python -m tools.cgroup.audit_shape_identity \
  assets/app/KFPS\ Logo.json \
  --cgroup runtime/cgroup-prototype/kfps-logo-flat/C_group \
  --output runtime/cgroup-prototype/kfps-logo-identity-audit.json
```

## Validation Focus

Use these tools to build fixtures before touching live import/export:

- Shape IDs in JSON vs shape IDs in `C_group`.
- Editor resource identity vs game `type_word`.
- Preview renderer output vs canonical shape word.
- Live memory export JSON vs known `C_group` fixture JSON.
