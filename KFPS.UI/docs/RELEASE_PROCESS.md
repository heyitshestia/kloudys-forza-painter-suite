# Release Process

## Scope And Authority

A version bump, source push, service rollout and public release are separate
actions. Perform only explicitly authorized actions. The release owner's reviewed
per-release packaging recipe and frozen file inventories take precedence over
generic examples. This document describes the current signed Go bootstrap process,
not the retired Git-checkout fetch/mirror updater.

Use the controlled publication checkout only after the normal tested staging
transfer. Preserve exact preimages and hashes before transfer; never overwrite
unrelated working changes. Version and publication time are selected only after
the final upstream check and release gates. A draft changelog is not publication.

## Freeze And Public Inputs

1. Account for every changed and untracked path. Select exact reviewed public
   source, tests and docs; do not recursively add a working installation or Studio
   development tree. Review machine paths, licenses and synthetic fixture provenance.
2. Run the affected Python, editor Node/native/Chrome, Worker and updater suites,
   plus real hidden/offscreen workflows for materially changed interfaces.
   Verify actual save/reopen, recovery, failure/cancellation and ownership behavior,
   not only source assertions. Inspect the staged diff and whitespace checks.
3. Freeze diagnostics, announcement and activity integration with matching
   collector/service contracts. Use synthetic inputs and disable activity in
   automated hosts. Test report collection/privacy without real report submission.
4. Materialize the exact Studio shipping inventory from its authoritative source.
   Refresh converter v2 source/prerequisite/build receipts and licenses when an
   input changes, including fingerprinted documentation. Supplemental prerequisite
   lists are not a replacement for the whole application asset inventory.
5. Reject dependencies on a developer workspace, private launch configuration,
   game assets, artwork, credentials, keys, receipts or personal state. Private
   rollback copies, run reports, test downloads and one-off probes are not public
   inputs. Git tracking alone is not evidence that a file belongs in a bundle.

## One Immutable Release

The managed-runtime bundle and signed updater payload must use the same exact
reviewed commit and qualified Python runtime. Do not build from a mixed directory
or use dirty-tree overrides. Include the validated updater binary in that commit
before building the bundle; changing a Go source default does not update an old EXE.

The established application launchers are exactly:

- `KFPS.exe`
- `KFPS Editor.exe`
- `KFPSLiverySudio.exe`

Preserve that established Studio filename. Matching inner and outer copies of
these three launchers and `KFPS-Updater.exe` must be verified.

Build the production bootstrap as **1.0.5** with the existing production public
trust key and normal tests/static checks. The existing build entry point is
`tools/bootstrap_updater/build.ps1`; the publisher it produces is non-shipping.
Check the resulting updater's build identity rather than assuming a source
default or old binary is current.

The existing AiO builder is `tools/release/build_release_bundles.py`, using its
`--repo`, `--commit`, `--python-source`, `--kind recommended` and `--output-dir`
arguments as specified in the reviewed release recipe. The public bundle name
remains `KFPS-<version>-bundled.zip`. The advanced no-Python distribution is retired;
`all` is a compatibility alias for the supported managed-runtime bundle.

The existing `KFPS-Update-Publisher.exe build` workflow signs exact channel and
component metadata using the controlled production signing key. Use the same
commit, app version and Python, immutable HTTPS component URLs, the approved
publication timestamp and a sequence above the live accepted sequence. For the
Studio-launcher release, both `minimum_bootstrap` and `updater.version` are
**1.0.5**, and the publisher's bootstrap-version input is 1.0.5. Private signing
material never enters source, payloads, release folders or public logs.

Regenerate the editor baseline from final source and the exact managed runtime.
Run the strict Python Studio policy on the immutable export before producing
both the AiO and signed update. The Go publisher's signed path validation does not
replace the richer Studio source, converter and license inventory gate.

## Signed Update And Preservation Contract

Normal installed updates use the self-contained Go `KFPS-Updater.exe`, not Git,
Python scripts, a mirror operation or an installed checkout. Ed25519 signatures
authenticate exact metadata bytes; signed component sizes, SHA-256 values and
per-file inventories verify content. Monotonic sequence checks prevent replay.

A manifest managing the outer Studio launcher requires bootstrap 1.0.5. Older
bootstraps use the existing authenticated self-update handoff before applying it.
Exit code **4** means a verified child has started, not final update success:
wait for the child's final report. Program files are applied before launchers,
with the updater last.

The updater backs up changed program files, journals operations and verifies
recovery before continuing after interruption. It must reject reparse paths,
unsafe inventory targets, bad signatures/hashes and replacement locks without
silently discarding user work. It may repair or replace the signed managed
`python/` runtime; that directory is program-owned, not preserved user data.

Protected data includes `runtime/`, `imgs/`, `webui-data/`, key files and
secret/developer state covered by the updater policy. Studio adds explicit
protection against replacement **and retirement** for `tools/livery-studio/settings`,
`recovery` and mutable `runs`. Only these exact program artifacts are managed
under Studio runs:

- `tools/livery-studio/runs/component-converter/converter/build-manifest.json`
- `tools/livery-studio/runs/component-converter/converter/publish/Kfps.LiveryLab.Converter.exe`

Managed projects/recoveries under `imgs/livery-projects` remain protected.
Activity seed/preferences/locks and shared-announcement acknowledgement state are
runtime data: preserve existing copies during upgrade, but never ship copies in
source, diagnostics archives or release bundles.

## Artifact And Prepublication Gates

- Verify release version/commit, complete inventories, hashes and applicable
  signatures. A ZIP hash alone is not a publisher signature.
- Audit both formats for excluded state and exact launcher/updater identity.
  Verify converter executable/receipt agreement, pinned prerequisites and licenses.
  General test/docs paths are not automatically absent from a Git archive.
- Extract one isolated full bundle and exercise actual native/Chrome launch,
  Studio, shared viewer, source-editor handoff, diagnostics and announcement paths.
  Compiled-launcher checks or reduced-runtime markers are not full GUI validation.
- Verify managed-runtime dependencies and first/repeated startup without relying
  on system Python or the development workspace. Chrome remains user-installed;
  a missing selected Chrome must offer explicit guidance, not a silent fallback.
- Seed only synthetic themes, shortcuts, settings and valid projects. Record
  protected hashes, then verify that these values are actually consumed after
  upgrade, edit/save/reopen and restart. Byte preservation alone is insufficient.
- Keep Worker compatibility, migrations, cutoff/policy selection, observability
  privacy, backups and storefront promises as coordinated release gates. Do not
  enable live counter collection before its infrastructure/retention review.
- Keep Studio native export experimental. Tests do not establish in-game
  acceptance, every car/body-kit mapping, physical IME/DPI or universal performance.

## Publication And Actual Previous-Bundle Upgrade

Publish only the approved immutable artifacts and matching signed metadata.
Then independently verify remote identities, sizes, hashes, signatures and
availability. Local candidate tests do not prove the public update path works.

Use a verified original previous public bundle in one isolated disposable
extraction, not a personal installation. Isolate profile/TEMP/APPDATA roots and
set `KFPS_ACTIVITY_DISABLED=1`. Use the original updater and real public channel
without test trust keys or sequence resets. First check without product mutation,
then perform the approved update without relaunching user windows. Wait for any
authenticated child and its final report.

Compare all seeded protected bytes and exercise real native/Chrome combinations,
themes/shortcuts/settings, old-project open/edit/save/reopen, Studio recovery,
source returns and the read-only viewer. Verify warm no-op and damaged/missing
program-file repair against the actual published inventories. Use isolated
ephemeral signed fixtures, not public payloads, for destructive failure tests.

Retain journal/backups after interrupted recovery. The pinned `--recover` floor
is not a general downgrade mechanism and must not bypass newer accepted state.
Production remediation normally uses a forward repair with a newer signed
sequence; live rollback remains a separately reviewed decision that preserves
subsequent user data. Record observed failures and environmental limits rather
than marking pending public-upgrade or hardware gates as passed.

See [the bootstrap updater guide](../../tools/bootstrap_updater/README.md) for
existing commands, trust details and recovery behavior. This process guide does
not start a build, change a version, deploy a service or publish a release.
