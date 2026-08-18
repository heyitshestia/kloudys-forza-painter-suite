# Building and running

## Requirements

- Windows 10 or 11 x64
- 64-bit Python 3.12
- Dependencies from the root `requirements.txt`
- The normal KFPS backend files and `KloudysGalateaGenesis.exe`

## Development run

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 KFPS.UI\app.py
```

`requirements.txt` is the supported version range for ordinary development.
`requirements.lock.txt` is the exact Windows x64 Python 3.12 set used by CI and
release-runtime validation. Update the lock only after the complete quality gate
passes with the new versions.

The source app discovers the KFPS root by searching for `VERSION` and the generator/backend files. Set `KFPS_APP_ROOT` only for unusual local layouts.

## Tests

```powershell
py -3.12 -m unittest discover -s KFPS.UI\tests -v
```

Tests create temporary folders. Memory tests use the current test process or
fixtures; they do not write to a running game.

The repository's bundled runtime can be used instead of a system installation:

```powershell
.\python\python.exe -m unittest discover -s KFPS.UI\tests -p "test_*.py" -v
```

Run the editor's dependency-free JavaScript contract tests separately:

```powershell
node tools\fabric-editor\tests\editor-core.node.js
node tools\fabric-editor\tests\editor-shell.node.js
```

Run a real headless Outputs-page startup and write layout evidence:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
py -3.12 KFPS.UI\app.py --demo --allow-unsupported-python `
  --skip-startup-index --skip-startup-thumbnails --page outputs `
  --width 1600 --height 900 --layout-report outputs-layout.json
```

The two Cloudflare Workers have independent locked test environments:

```powershell
cd tools\supporter_activation_worker
npm ci
npm run typecheck
npm test

cd ..\fh6_rtti_relay_worker
npm ci
npm run typecheck
npm test
```

`.github/workflows/quality.yml` runs these gates on pull requests and pushes to
`main`. A successful smoke test is not a release decision; use the full release
checklist in `RELEASE_PROCESS.md`.

## Visual capture

```powershell
py -3.12 KFPS.UI\tools\capture_pages.py
```

This launches the real Qt application in deterministic demo mode and captures every page at the required reference sizes.

Development screenshot and layout hooks live in
`src/kfps_ui/development_harness.py`. Keep them out of normal services and verify
that product startup still works without any capture arguments.
