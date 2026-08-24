# Game Adapter Architecture

## Purpose

KFPS supports four games whose save formats, memory locators, ownership evidence,
and shape identifiers are related but not identical. Those product decisions live
in `game_adapters/` instead of being repeated across QML, services, and subprocess
bridges.

The adapter is the source of truth for:

- live import and export availability;
- offline import and export availability;
- supported store families;
- ownership policy names and additional file preflights;
- save-root and artifact discovery strategy;
- live locator behavior;
- canonical shape/schema target and decoded-source acceptance;
- the offline-import handler selected by the library service.

Game-specific codecs and memory scanners remain specialized implementation code.
They consume adapter declarations; they are not alternate capability registries.

## Current declarations

| Game | Live import/export | Offline export | Offline import | Stores | Locator source |
| --- | --- | --- | --- | --- | --- |
| FH6 | Yes | Yes | Yes | Microsoft/Xbox, Steam | Shared profile, then verified local fallback |
| FH5 | Yes | Yes | No | Microsoft/Xbox, Steam | Packaged final descriptors |
| FH4 | Yes | Yes | Yes | Microsoft/Xbox, Steam | Packaged final static profile |
| FM8 | Yes | Yes | Yes | Microsoft/Xbox, Steam | Dedicated ownership-verified live root |

Offline export means read-only local save scanning into KFPS JSON. Offline import
means creating or replacing supported local save records. Live operations use the
running game's memory.

FM8 save discovery covers the Steam-local
`%LOCALAPPDATA%\Microsoft.ForzaMotorsport\UGC` tree, Steam app `2440510`
remote roots, and Microsoft Store package-local `LocalCache\Local\UGC` or
`LocalState\UGC` trees. Only `LayerGroups/<record>/data` files are candidates;
full-car `Liveries` records remain outside the vinyl-group scanner.

## Files and responsibilities

- `game_adapters/contracts.py`: immutable contracts only.
- `game_adapters/registry.py`: the four canonical declarations and aliases.
- `game_adapters/discovery.py`: strategy-driven save and artifact discovery.
- `game_adapters/policies.py`: additional fail-closed ownership preflights.
- `game_profiles.py`: compatibility facade for legacy memory scripts. Do not add
  new declarations there.
- `KFPS.UI/src/kfps_ui/cgroup_library_service.py`: UI orchestration and format
  handler implementations. Its old private discovery methods are compatibility
  wrappers around `game_adapters.discovery`.
- `KFPS.UI/src/kfps_ui/transfer_service.py`: resolves a game once, verifies the
  declared live capability, and passes the adapter's bridge key.
- `KFPS.UI/bridges/transfer_bridge.py`: consumes process, template, locator, and
  fallback declarations before invoking the existing verified memory tools.

## Compatibility rules

- Canonical application keys are `fh4`, `fh5`, `fh6`, and `fm8`.
- The established memory-tool key for FM8 remains `fm` through
  `GameAdapter.bridge_key`.
- `game_profiles.PROFILES`, `get_profile`, and `iter_profiles` remain supported for
  existing standalone tools.
- Unknown UI values retain the historic FH6 default. Command-line parsing remains
  strict and rejects unsupported bridge keys.
- The common decoder always runs with locked content disabled. A game may declare
  an additional ownership preflight, but may not weaken the common gate.

## Adding or changing a game

1. Change or add one declaration in `game_adapters/registry.py`.
2. Add a discovery strategy primitive only when existing primitives cannot express
   the save layout.
3. Keep binary parsing in a focused codec or memory module. Do not move raw format
   parsing into the registry.
4. Add declaration, alias, store, discovery, ownership, and shape-schema tests in
   `KFPS.UI/tests/test_game_adapters.py`.
5. Add real-format regression fixtures for any new codec or ownership rule.
6. Run focused game tests, the bridge safety tests, QML checks, and the full suite.
7. Verify the actual app workflow before changing the capability from unavailable
   to available.

## Invariants

- Adapters declare behavior; they do not perform writes.
- Ownership decisions fail closed.
- Offline import dispatch may only call a handler explicitly named by the adapter.
- Save discovery is read-only.
- Shape normalization uses the adapter's canonical game key.
- QML asks the service for capabilities and labels instead of naming games in
  conditional expressions.
