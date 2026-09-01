# Release process

## Scope rules

A version bump, a push to `main`, and a release bundle are three separate actions.
Perform only the actions explicitly requested. Most KFPS updates bump the version
and update `main` without building release archives.

Release artifacts must never contain supporter keys, receipts, local settings,
generated artwork, private documentation, test downloads, unrelated JSON files,
runtime caches, logs, backups, or personal images.

## Before changing the version

1. Start from the controlled CLEAN checkout.
2. Review `git status` and account for every changed and untracked path.
3. Confirm the intended feature was tested in DIRTY when the normal staging rule
   applies.
4. Run the complete Python suite and editor Node tests.
5. Run the real offscreen app startup for each materially changed page.
6. Run the affected Worker tests for Worker changes.
7. Check `git diff --check` and inspect the exact staged diff.

Do not treat an existing generated file as permission to include it. The release
builder starts from tracked Git content specifically to avoid that mistake.

## Version-only update

When a version bump and repository update are requested without bundles:

1. update the canonical version and changelog locations used by the app;
2. rerun version/changelog tests;
3. commit only the reviewed product changes;
4. push the intended commit to `main`;
5. verify the remote commit and update metadata;
6. do not create or replace release archives.

## Release bundle update

Build only from the exact committed revision intended for release:

```powershell
py -3.12 tools\release\build_release_bundles.py `
  --output-dir C:\path\to\release-output `
  --python-source C:\path\to\validated\python `
  --kind all
```

The expected names are:

- `KFPS-<version>-bundled.zip`: recommended, with Python and dependencies.
- `KFPS-<version>-ADVANCED-NO-PYTHON-NO-DEPENDENCIES.zip`: advanced.

For each archive:

1. verify its SHA-256 sidecar;
2. inspect `RELEASE-MANIFEST.json` and confirm the source commit;
3. extract into a new temporary directory;
4. confirm the Recommended build reports complete wheel `RECORD` contents and
   passes the bundled dependency API probe;
5. start the recommended package on a machine without relying on system Python;
6. start the advanced package with a supported system Python installation;
7. test first startup, second startup, updater handoff, editor launch, and an
   output that survives restart;
8. verify generated/runtime data is absent before upload.

The manifest and hash prove content consistency, not publisher identity. Do not
describe them as signatures unless a separately controlled signing workflow is
implemented.

## Updater verification

Test both an installed bundle and a Git checkout:

- installed bundle: backup, exact-commit fetch, mirror, verification, launcher
  replacement, and rollback on forced failure;
- Git checkout: no destructive clean, reset, or deletion of untracked developer
  files;
- both: `runtime`, `imgs`, packaged Python, supporter state, and user data remain
  untouched.

The updater must execute its installed script, pin one remote commit for the whole
operation, and restore the backup if program verification or launcher replacement
fails.
