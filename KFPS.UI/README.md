# KFPS Native QML Interface

This directory contains the PySide6/Qt Quick desktop interface. It changes presentation and orchestration only: the KFPS generator, finalizer, game-memory importer/exporter, JSON renderer, updater, and Fabric editor remain the existing backend implementations.

## Source launch

Use 64-bit Python 3.12:

```powershell
python -m pip install -r requirements.txt
python KFPS.UI\app.py
```

The app starts at approximately `1760×1040`, adapts down to `1360×820`, and uses a wide sidebar on normal displays with an automatic compact rail on constrained windows.

## Current refinement baseline

The current geometry baseline standardizes centered button content, field alignment, logical scaling breakpoints, creator-first page sizing, and route-aware sidebar scrolling. Use `tools/audit_layout_matrix.py` and `tools/capture_pages.py` for repeatable layout checks.

## Build KFPS.exe

```powershell
powershell -ExecutionPolicy Bypass -File tools\native_launcher\build_launcher.ps1
```

The shipped executable is intentionally small. It prefers the packaged `python/` runtime, then validates `KFPS_PYTHON`, `py -3.12`, and common system Python locations before launching `KFPS.UI\app.py`. External runtimes must be 64-bit Python 3.12 with every package in `requirements.txt`. Copy the output `KFPS.exe` beside the `KloudysFH6Painter` folder, and keep the same launcher payload inside `KloudysFH6Painter\KFPS.exe` so the updater can repair the parent launcher. A flat source archive remains blocked even if a Python directory is manually added.

## Structure

- `qml/` — the entire interface and reusable visual system
- `assets/` — original Night Blossom artwork and SVG icons
- `src/kfps_ui/` — small Python services exposed to QML
- `bridges/` — thin subprocess adapters to the unchanged backend
- `tests/` — non-destructive service tests
- `tools/` — screenshot and visual-QA helpers
- `docs/` — architecture, behavior, build, and validation notes

See `docs/ARCHITECTURE.md` before changing application state or process handling.
