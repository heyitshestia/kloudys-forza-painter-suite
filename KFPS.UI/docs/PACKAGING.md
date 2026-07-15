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
