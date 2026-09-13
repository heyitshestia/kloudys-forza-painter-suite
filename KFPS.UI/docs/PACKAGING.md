# Packaging

KFPS ships as loose application files, native launchers and an installation-owned Python/Qt runtime. The launchers are built from `tools/native_launcher/KFPSLauncher.cs`; they do not embed the application source or assets. All supported end-user downloads include `KloudysFH6Painter/python/`. The advanced no-Python variant is retired. The editor verifies the packaged runtime and source baseline before creating its window; it does not use the user's default browser or silently switch to system Python. Development checkouts retain their explicit development launch path.

The standalone layout is:

```text
Standalone root/
├── KFPS.exe
├── KFPS Editor.exe
├── KFPS-Updater.exe
├── Images/
└── KloudysFH6Painter/
    ├── VERSION
    ├── KFPS.exe
    ├── KFPS Editor.exe
    ├── KFPS-Updater.exe
    ├── KloudysGalateaGenesis.exe
    ├── python/                 (required managed runtime)
    ├── generator_backend.py
    ├── KFPS.UI/
    ├── KFPS.Editor/            (editor source and baseline.json)
    ├── tools/
    ├── settings/
    └── imgs/
```

`Standalone root/KFPS.exe` is the user-facing launcher. `KloudysFH6Painter/KFPS.exe` is the tracked updater payload used to repair or replace the parent launcher. The updater verifies the parent launcher by SHA256 so an old large binary and the new small launcher cannot be confused just because both are named `KFPS.exe`.

Every release must include:

- the parent `KFPS.exe`
- `KFPS Editor.exe` and `KFPS-Updater.exe` beside it, with repair copies inside the app folder
- the full `KloudysFH6Painter` app folder
- `KloudysFH6Painter/KFPS.exe` as the launcher repair payload
- an `Images/` folder beside `KFPS.exe`

The supported bundle includes `KloudysFH6Painter/python/` with Python 3.12 and all locked dependencies. Do not flatten or rename the nested app folder. Active Git checkouts remain usable for development, while source archives are intercepted by the wrong-download guard before normal app services initialize. Users of historical no-Python packages need the managed runtime through the verified updater repair or the supported bundle; installing arbitrary system packages is not an editor repair.

Installed bundles prefer `KFPS-Updater.exe`. KFPS refuses update handoff while the editor is open. Development/legacy fallback uses the installed `03_update_from_github.bat`. See the updater tests and release process for the separately verified repair and rollback paths.

## Release builder

Release archives must be made with `tools/release/build_release_bundles.py`, from the exact committed revision being published. The builder exports Git-tracked files from that immutable commit instead of copying the working directory. It refuses modified tracked files by default, blocks runtime/personal-state paths, preserves the established nested layout, and writes both `RELEASE-MANIFEST.json` and a SHA-256 file beside each archive.

Recommended builds copy the supplied Python runtime into an isolated staging
directory, remove packages outside `requirements.lock.txt`, and force-reinstall
every locked dependency. The builder then verifies wheel `RECORD` sizes and
hashes plus critical OpenCV, NumPy, Pillow, Qt, psutil, and pywin32 APIs. Package
metadata and `pip check` alone are not accepted as proof that native modules are
complete.

```powershell
py -3.12 tools\release\build_release_bundles.py `
  --output-dir C:\path\to\release-output `
  --python-source C:\path\to\validated\python `
  --kind recommended
```

The supported output name remains:

- `KFPS-<version>-bundled.zip` for the recommended package with Python and dependencies.

`--kind all` is retained only as an alias for the single supported bundle.
`--kind advanced` is rejected. Historical upgrade fixtures are not new offerings.
After dependency verification, the builder generates the editor baseline with the
staged Python using `-I -B`. Failure aborts packaging. The final state scan runs
after that generator so caches or private files cannot slip into the archive.

The generated manifest records the source commit and every included file's size and SHA-256 digest. Rebuilding the same commit with the same Python runtime produces byte-identical archives. A release signing key is deliberately not stored in this repository; release signatures require a separately controlled production key before they can become a trust boundary.

## Update safety

The application executes only the updater batch shipped with the installed copy. Each run resolves `main` once, pins that 40-character commit, fetches and verifies that exact revision, and never downloads another batch for immediate execution. A complete program-file backup is required before mutation. Failed updates restore the previous program files and parent launcher automatically while leaving `runtime/`, `imgs/`, `webui-data/`, supporter keys, and packaged Python untouched.
