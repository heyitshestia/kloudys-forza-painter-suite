# KFPS Editor

The editor's authoritative source package. It retains Fabric, the existing tools,
English/Korean interface, shape conversion rules and saved-file formats.

## Source Layout

| Location | Responsibility |
| --- | --- |
| `editor.py` | Standalone Python entry point |
| `src/kfps_editor/` | Native window, IPC, local server, storage and diagnostics |
| `web/` | Editor interface, dedicated owners, workers, locales, Fabric and shapes |
| `manifest.json` | Source roles, ownership, shared dependencies and stable paths |
| `requirements.txt` | Editor-only subset of the qualified Windows Python runtime |
| `retired-files.json` | Exact obsolete program paths consumed by the existing updater |
| `tools/` | Isolated staging and source-inventory utilities |
| `web/tests/` | Unit, native-window, workflow, fault and performance checks |

Shared shape parsing and preview code remain in `kfps_shapes/`,
`geometry_json.py` and `json_preview_renderer.py`. The manifest explicitly lists
them. The editor does not import the main KFPS interface or generator.

## Run From Source

From a complete development checkout with the qualified Python dependencies:

```powershell
py -3.12 KFPS.Editor/editor.py
```

`--background` opens without raising the editor or taking focus; it does not
minimize the window. Normal launches bring the editor forward, restore a minimized
window, and focus its active dialog when one needs attention. Windows may deny
foreground focus after unrelated user input; the editor requests taskbar attention
instead of overriding the user's focus settings.
`--runtime-root` is available for an explicitly isolated test profile.

The native `KFPS Editor.exe` still belongs beside `KFPS.exe` in a combined
installation. The old `KFPS.UI/editor.py` entry and Python import locations are
compatibility adapters. Do not put a second copy of web sources under
`tools/fabric-editor/`.

## Update Awareness

The standalone editor checks the same published stable update channel as KFPS at
startup and every five minutes, even while the main app is closed. A red UPDATE
indicator appears at the upper left when a newer version is available. Click it
to stop blinking for that version; it stays visible until the installation is
current, and a later version can blink again. Reduced-motion settings disable
the animation. The label and explanation support English and Korean.

This is a reminder, not an automatic installation. Save your work and use KFPS's
normal update workflow when ready. Offline checks do not interrupt editing.

## Data Stays Put

Projects, assets, settings, themes, recovery copies and the WebEngine profile stay
under the existing `runtime/fabric-editor/` locations. Flat exports retain their
existing output location. Source relocation does not migrate data, change the
browser origin, reset favorites or replay acknowledged notices.

See the [editor guide](web/README.md), [architecture](docs/ARCHITECTURE.md),
[validation](docs/VALIDATION.md), and [localization workflow](web/locales/README.md).
