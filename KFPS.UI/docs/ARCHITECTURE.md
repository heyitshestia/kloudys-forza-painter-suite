# Architecture

## Boundary

QML owns layout, visual state, animation, focus, and presentation. Python owns files, processes, settings, reports, version checks, models, and all interaction with the existing backend. QML JavaScript is intentionally limited to small local UI decisions.

```text
QML page/component
    ↓ property/slot/signal
Python service or controller
    ↓
Existing KFPS Python/native backend
```

## Shell

`Main.qml` owns only the window shell: frameless title bar, adaptive sidebar, global background, page loader, centered version pill, and bottom panel. Each functional page is a separate QML file. Shared controls live under `qml/components`.

## Services

- `AppController` — route and page-title state
- `SettingsService` — clean QML settings stored atomically in `runtime/qml-shell-settings.json`
- `LogService` — one shared, timestamped log model; incoming output is batched every 120 ms and capped at 2500 rows
- `VersionService` — fixed-width current/update state
- `RuntimeService` — non-blocking packaged-runtime checks
- `SourceImageService` — selection, source report, and heatmap
- `GenerationService` — generator bridge ownership, preview polling, graceful stop, and force stop
- `JsonService` — grouped JSON library, selection, preview cache, and recent files
- `TransferService` — import/export bridge ownership
- `EditorService` — project browser and unchanged Fabric editor launcher
- `ReportService` — local-only Markdown reports
- `UpdateService` — safe close/update/relaunch handoff

## Thread and process rules

- Never run generator or game-memory operations on the Qt GUI thread.
- Generator and transfer output enters one shared log queue and is added to QML in batches.
- Force Stop terminates the full bridge process tree with `psutil`.
- Graceful Stop writes the backend's `.v2-stop` request in the active run directory.
- JSON previews are cached by path, timestamp, and size.

## Themes

Night Blossom is the public default; Command Prompt and Apex Vector are also public. Windows 94, Patron's Atelier, Carbon Dark, and Overdrive 200X are supporter presets. `Kfps.Theme/Theme.qml` selects a palette behind one semantic token contract so themes share components without changing page structure. Generic shell loaders allow a palette to opt into a custom backdrop or page transition without adding theme-name branches to shared controls. See `THEME_SYSTEM.md` for the contract and new-theme checklist.
