# Packaging

KFPS ships as loose QML/Python application files plus a small native launcher. The launcher is built from `tools/native_launcher/KFPSLauncher.cs`; it does not embed QML, Python modules, backend scripts, or assets. It prefers `KloudysFH6Painter/python/`, then validates `KFPS_PYTHON`, the Windows `py -3.12` launcher, and common system Python locations. Every external candidate must be 64-bit Python 3.12 and import all packages required by KFPS.

The standalone layout is:

```text
Standalone root/
├── KFPS.exe
├── Images/
└── KloudysFH6Painter/
    ├── VERSION
    ├── KFPS.exe
    ├── KloudysGalateaGenesis.exe
    ├── python/                 (bundled release only)
    ├── generator_backend.py
    ├── KFPS.UI/
    ├── tools/
    ├── settings/
    └── imgs/
```

`Standalone root/KFPS.exe` is the user-facing launcher. `KloudysFH6Painter/KFPS.exe` is the tracked updater payload used to repair or replace the parent launcher. The updater verifies the parent launcher by SHA256 so an old large binary and the new small launcher cannot be confused just because both are named `KFPS.exe`.

Every release must include:

- the parent `KFPS.exe`
- the full `KloudysFH6Painter` app folder
- `KloudysFH6Painter/KFPS.exe` as the launcher repair payload
- an `Images/` folder beside `KFPS.exe`

Bundled releases additionally include `KloudysFH6Painter/python/` with Python 3.12 and all app dependencies. Binary releases intentionally omit that directory and require the user to install `requirements.txt` into a system 64-bit Python 3.12. Neither release may flatten or rename the nested app folder. Active Git checkouts remain usable for development, while source archives are intercepted by the wrong-download guard before normal app services initialize.

The in-app updater closes `KFPS.exe` and invokes `03_update_from_github.bat`. The batch updater preserves generated/runtime/user data, mirrors program files from GitHub, verifies tracked files, then verifies the parent launcher hash.

## Release builder

Release archives must be made with `tools/release/build_release_bundles.py`, from the exact committed revision being published. The builder exports Git-tracked files from that immutable commit instead of copying the working directory. It refuses modified tracked files by default, blocks runtime/personal-state paths, preserves the established nested layout, and writes both `RELEASE-MANIFEST.json` and a SHA-256 file beside each archive.

```powershell
py -3.12 tools\release\build_release_bundles.py `
  --output-dir C:\path\to\release-output `
  --python-source C:\path\to\validated\python `
  --kind all
```

The output names remain:

- `KFPS-<version>-bundled.zip` for the recommended package with Python and dependencies.
- `KFPS-<version>-ADVANCED-NO-PYTHON-NO-DEPENDENCIES.zip` for the advanced package.

The generated manifest records the source commit and every included file's size and SHA-256 digest. Rebuilding the same commit with the same Python runtime produces byte-identical archives. A release signing key is deliberately not stored in this repository; release signatures require a separately controlled production key before they can become a trust boundary.

## Update safety

The application executes only the updater batch shipped with the installed copy. Each run resolves `main` once, pins that 40-character commit, fetches and verifies that exact revision, and never downloads another batch for immediate execution. A complete program-file backup is required before mutation. Failed updates restore the previous program files and parent launcher automatically while leaving `runtime/`, `imgs/`, `webui-data/`, supporter keys, and packaged Python untouched.
