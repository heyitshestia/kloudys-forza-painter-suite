# Live-memory locator engine

## Product contract

`live_memory_locator` is the only production entry point for locating an open
vinyl group. The transfer bridge invokes it once and consumes one
`locator-session.json` report. Import and export tools do not independently
choose, rank, or fall through between locator implementations.

The engine contract is versioned independently from KFPS:

- engine version: `1.1.0`;
- diagnostic schema: `kfps_live_memory_locator_v1`;
- cache schema: `kfps_live_memory_locator_cache_v1`.

`game_adapters` remains the source of truth for game capabilities, process names,
memory profile, profile source, fallback permission, import-template rules, and
ownership requirements.

## Location sequence

1. Resolve one `GameAdapter` and verify that the requested operation is supported.
2. Record the process name, executable, PID, and creation time. Reject a process
   whose name is not declared by the adapter.
3. Run the profile locator. This includes FH6 shared RTTI profile matching and
   allocator-window lookup, fixed FH4/FH5 profiles, and the FM8 live-root strategy.
4. Deterministically validate the returned group, table, vector, capacity, layer
   pointers, import template, group hierarchy, and ownership evidence required by
   the adapter.
5. Treat a safety refusal, a complete authoritative scan, or an unexpected backend
   exception as terminal. These outcomes never fall through to a noisier scanner.
6. Only after an incomplete, non-authoritative miss, run the adapter-permitted
   count/table research strategy. Candidates are ranked deterministically and must
   pass exact full-table validation.
7. Re-read the process identity. A process exit, restart, or PID reuse invalidates
   the result even when every address previously validated.
8. Atomically write one canonical diagnostic and return a status-specific exit
   code.

The established algorithms in `fh6_probe.py` and `fh6_group1000_probe.py` are
internal compatibility backends during this migration. Their direct command-line
reports use the canonical diagnostic envelope, but production orchestration must
not invoke them separately.

## Cache policy

The persistent cache lives at `runtime/live-memory/locator-cache.json`. It keeps:

- allocator windows keyed by a matched build/profile;
- bounded prior-session outcomes keyed by canonical game, matched profile,
  process creation time, and operation.

It never stores group addresses, table addresses, pointer fields, or other live
pointers. Every operation locates and validates the current editor state again.
This is intentional: a group can be closed or replaced without the game process
restarting, so blindly reusing a pointer would be faster but unsafe.

The older FH6 allocator-window cache is read once as a migration source. Invalid
or partial current cache data cannot block that migration. Writes are atomic, and
cache-write failure does not turn a validated transfer into an unsafe one.

## Report archive

The requested run report remains in its transfer run directory. Every canonical
engine result is also archived under `runtime/live-memory/reports`:

- `latest.json`: newest report from any game or operation;
- `latest/<game>-<operation>.json`: newest report for one game and operation;
- `index.json`: searchable summary of every dated report;
- `<YYYY-MM-DD>/`: immutable reports with game, operation, layer count, outcome,
  and diagnostic ID in each filename.

The index is rebuilt from dated reports if it is missing or malformed. Archive
failure is recorded in the requested run report but never changes a validated
locator outcome. Reports identify the detected Steam or Microsoft/Xbox
installation and include Windows, CPU, memory, active GPU, and driver information.
User-profile components in paths are scrubbed before writing.

The report archive is local runtime data and is excluded from Git and release
bundles. Located reports contain transient live addresses needed for diagnosis;
the pointer-free locator cache remains a separate file and never gains those
fields.

## Diagnostic contract

Every engine result includes:

- request identity and scan limits;
- process identity;
- profile strategy and matched profile evidence;
- ordered attempts and elapsed time;
- exactly one outcome: `located`, `refused`, `no_match`, or `error`;
- authoritative-state flag and plain-language reason;
- selected addresses and validation evidence only for a located result;
- cache metadata and low-level scanner diagnostics;
- KFPS version and build commit when available.

The transfer bridge rechecks schema, game, PID, layer count, purpose, status, exit
code, and required selected addresses. The exporter then verifies the report
against live vector metadata and independently rechecks the current hierarchy and
ownership before reading layers. A report is evidence, not permission to bypass a
live safety check.

## Failure rules

- Unknown process, backend exception, changed process instance, malformed report,
  request/report mismatch, partial vector, duplicate pointer, invalid capacity,
  bad import template, or incomplete ownership evidence fails closed.
- An authoritative exact-profile miss does not trigger a full-memory fallback.
- A fallback candidate must decode every requested layer and contain no duplicate
  or unreadable layer pointer.
- No locator path writes game memory. Import writes begin only after the bridge and
  importer have accepted the locator result.

## Change checklist

1. Change the engine contract or adapter declaration, not bridge-local policy.
2. Add a regression test for the exact failure or new profile behavior.
3. Test located, refused, authoritative no-match, incomplete no-match, backend
   error, process restart, cache restart, and tampered report paths.
4. Run FH4, FH5, FH6, FM8, grouped-export, import rollback, and native memory
   session tests.
5. Run the complete `KFPS.UI/tests` suite and static compilation.
6. Validate a real open template for every affected game before release.

## Release validation: 2026-08-26

These were read-only executions of the canonical production locator against real
running games. Import rows validate the import target but do not perform writes.

| Game/install | Real cases | Result |
| --- | --- | --- |
| FH4 Microsoft Store | 3000-layer grouped template import/export; 319-layer grouped owned; 1200-layer foreign | Located exact owned/template groups and authoritatively refused the foreign group |
| FH5 Steam | 3000-layer grouped template import/export; 277- and 223-layer grouped owned | Located and flattened all tested groups; foreign behavior retained from the established policy and regression tests because this account cannot access a foreign FH5 group |
| FH6 Xbox app | 3000-layer grouped template import/export; 2158-layer grouped owned; 45-layer grouped foreign | Located through the allocator profile and authoritatively refused the foreign group without fallback |
| FM8 Steam | 1710-layer template; 65- and 160-layer grouped owned; 500- and 3-layer grouped foreign | Located nested owned groups, learned verified allocator windows, and authoritatively refused both large and tiny foreign groups without research fallback on cached runs |

The final full suite passed 534 tests with one existing skip before promotion.
