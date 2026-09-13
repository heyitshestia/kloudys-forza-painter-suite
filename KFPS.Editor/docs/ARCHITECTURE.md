# Editor Ownership and Contracts

## Canonical State

Fabric owns the live scene. There is no second artwork model. `web/editor.js`
composes owners and retains the existing tool/render/mutation boundaries not
profitably separated yet. Dedicated owners are not permission for arbitrary
cross-module calls or independently committing the same change twice.

Scene-space hit tests must use the Fabric adapter's `sceneBounds`, not assume
`getBoundingRect(true, true)` is world-space for an ActiveSelection member.
Guide drawing owns its input gesture: disarm a shape transform that Fabric may
already have started beneath a touch before accepting the first guide endpoint.
Neither operation commits an artwork change by itself.

| Owner | File | Owns |
| --- | --- | --- |
| Commands | `web/editor-commands.js` | Bounded admission, generation fencing, terminal result and single commit |
| Numeric input | `web/editor-transform-inputs.js` | Field focus, label drag, pointer capture, preview/cancel and stale-input cleanup |
| History | `web/editor-history.js` | Saved-content identity, undo/redo branches, coalescing and the 80-state limit |
| Layer groups | `web/editor-layer-groups.js` | Group metadata and rename target validation |
| Native protocol | `web/editor-desktop-protocol.js` | Bounded request/reply tracking, user-wait and outcome reconciliation |
| Project workflow | `web/editor-projects.js` | Explicit save outcome, fingerprints, receipts and saved association |
| Persistence | `web/editor-persistence.js`, `web/editor-persistence-worker.js` | Worker lifetimes, serialization, authenticated storage requests and browser recovery |
| Recovery | `web/editor-recovery.js` | Ordered checkpoint submission, independent backup, retry, clear and graceful drain |
| Reference | `web/editor-reference.js` | Original source, image/decode lifetime, placement, sampler and layered SVG state |
| Renderer | `web/editor-renderer.js` | Preview programs/buffers/textures, cooperative document cache preparation, context state, fallback and cleanup |
| Catalog | `web/editor-catalog.js` | Metadata, shape-resource lookup, shared requests, deadlines and caches |
| Themes | `web/editor-themes.js` | Catalog refresh, active choice, preview, save and late-result fencing |
| Preferences/assets | `web/editor-preferences.js`, `web/editor-assets.js` | Existing independent settings and reusable artwork storage |
| Diagnostics | `web/editor-diagnostics.js` | Bounded semantic events, performance recorder and observer lifetime |
| Native host | `src/kfps_editor/host.py`, `ipc.py` | Window, readiness, single instance, transport and safe close decisions |
| Installed baseline | `src/kfps_editor/baseline.py`, `update_guard.py` | Release-owned file/runtime contract, isolated local interpreter and pre-Qt update exclusion |
| Update awareness (O20) | `web/editor-updates.js`, shared `tools/kfps_update_status.py` | Independent stable-channel checks, bounded requests and per-version blink acknowledgement; no installation or artwork mutation |
| Native storage | `src/kfps_editor/projects.py`, `recovery.py` | Atomic writes, byte limits, receipts, fingerprints, heads and floors |
| Local server | `src/kfps_editor/server.py` | Authenticated routes and the fixed editor asset mount |
| Native diagnostics | `src/kfps_editor/diagnostics.py`, `bootstrap_log.py` | Rotating semantic logs and separate prelaunch raw-log retention |
| KFPS bridge | `KFPS.UI/src/kfps_ui/editor_launch.py` | Main-app launch, readiness presentation and integration |

`manifest.json` assigns stable O01-O20 ownership codes. The native inventory tool
emits exact source hashes, function locations and imports. Execution checkpoints
also contain the current JavaScript function/binding inventory. Static ownership
is not proof that every possible input sequence has been exercised.

## Mutation and Save Rules

Commit valid artwork/history/recovery changes before fallible UI refresh. If an
operation only staged objects, cancellation must release them without touching the
current scene. Document generation and operation-specific target identity both
matter; a matching generation alone is not permission to edit a changed selection.

`documentGeneration` fences load attempts and staged commands; `documentIdentity`
changes only for an accepted replacement/New. Failed B must not invalidate A's
project receipt or in-flight Save. Installation retains A's backing objects until
B's membership, required coordinates and baseline are accepted; optional display
refresh cannot revoke that acceptance. Reference restoration has its own token
and cannot overwrite a newer choice or mark newer edits clean.

A completed disk write is separate from updating the browser title or layer list.
Lost replies are reconciled using a request receipt, not by blindly repeating the
write. Current-client overwrite checks the prior fingerprint. Saved identity
remains content-based across undo/redo, not merely a monotonic revision comparison.

Recovery keeps the 500 ms idle / 2 s submission policy. This is not a promise of
disk completion within two seconds. Disk and browser copies progress independently;
large reference sidecars are reused. Normal native close drains pending work and
keeps the window open on protection failure unless the user explicitly overrides.
Browser unload alone cannot guarantee last-moment durability.

## Reference Preview Routing

The existing GPU interaction preview is eligible for either 300+ vinyl layers or
a visible, nonzero-opacity reference of at least 4,194,304 pixels. Large references
can make Canvas2D's first zoom expensive even on an empty scene. This threshold
selects a preview path; it is not an input or project capacity limit. Original
reference pixels, sampling and saved data remain unchanged.

Reference loading prepares the existing preview texture. This can add work during
explicit image loading while avoiding a larger first-zoom stall. Normal Fabric
rendering remains the settled/failure path, and device/upload failures must leave
the last complete canvas usable. It does not guarantee every GPU driver will
recover from a native graphics crash. Small references retain the layer threshold.

After accepting a document, the renderer can publish its existing GPU preview and
prepare cold Fabric caches in short animation-frame slices. One job owns that work;
it checks committed document identity and canvas membership, and cancels on a new
interaction, replacement, reset or disposal. It does not defer document acceptance,
change shape geometry or own saves. A completed job returns to normal Fabric drawing;
a failed or cancelled job uses the existing fallback. Individual shape work can
exceed the cooperative budget. This reduces one opening stall, not every large
reference decode, upload or whole-document operation.

## Diagnostics Without Pointer-Path I/O

Ordinary logs contain bounded state summaries and causal IDs, never full artwork,
reference bytes or a raw pointer stream. Recovery data is a separate responsibility.
The recorder retains 600 frames, a 1,024-event backlog and 64 action transitions.
Outgoing packets remain limited to 48 events and 24 KiB. Automatic paced draining
keeps ordinary bursts moving without synchronous pointer-path I/O; failed requests
retry the same packet identity. Native queue saturation returns backpressure,
not a false acknowledgment. Graceful close attempts a bounded two-second drain.
Native diagnostics use a 128-entry queue, batches of 16 and 2 MiB rotating files.
Critical losses are counted separately; diagnostics saturation must not stall saves.

Within the random page ID, `commitId`/`operationId` identify an accepted content
operation, `commandId` identifies a queued command when applicable, and `inputId`
links a Fabric pointer edit to that acceptance. No-op/cancelled edits do not gain
accepted IDs. `historyId` is a history sequence, not saved-content equality.
Recovery carries a first/last commit range and its independent monotonic revision.
The native checkpoint acknowledgment is emitted after storage acceptance, before
the HTTP response; the client result distinguishes disk and browser success.
Save receipts retain their existing UUID correlation. None of these IDs contains
user filenames, user IDs, shape coordinates or project content.

The support collector selects sixteen recent records from the existing bounded
snapshot, preferring commits, checkpoints and failures over routine jobs. Native
ACKs can arrive before delayed browser batches; collection must not assume their
arrival order is causal order. This is a recent diagnostic window, not an exhaustive
edit journal. Buffer loss counters and failed logging remain visible.

Document build/prewarm/install/retire/presentation spans and first completed Fabric
paint are separate. Worker duration includes worker-side asynchronous I/O; the
client duration also includes transport/queue time. Fabric paint timing measures
canvas draw submission, not physical display latency or GPU completion. Cache pixel
area and mesh count are allocation estimates, not total native memory or VRAM.
For cooperative opening, `document-cache` records preparation time and
`document-paint` measures the final post-preparation Fabric pass. End-to-end opening
latency must include decoding, reference restoration and all preceding phases;
the final paint duration alone is not the time the user waited.

Known file/text sizes are admitted before worker reads, with two project-sized
reads and six ordinary/eight total requests at most. Two slots remain available
for recovery protection. Streamed server responses are byte-bounded too. These
bounds do not claim a maximum for decoded images or the whole editor process.

`desktop.log` is the separate raw startup/Chromium stream. Before launch, when no
writer holds it, retention keeps a maximum 2 MiB newest tail and one prior tail.
An active inherited append handle is never renamed or truncated. No recurring log
rotation runs during pointer interaction. A noisy active session can exceed that
raw-file threshold until the next unowned launch; this is not a hard live size cap.
Denied raw-log storage must not prevent launching. The structured writer and native
startup-error/readiness markers remain independent failure-reporting paths.

## Stable Distribution Boundaries

The source package is `KFPS.Editor`, but HTTP remains `/tools/fabric-editor/`.
Resource requests never fall back to an old physical web folder. GET and HEAD use
the same allow-list and do not serve native code, tests or private data.

Legacy Python entries are small adapters. The legacy dynamically loaded server
adapter executes the canonical trusted server in its namespace for import
compatibility. Each server captures an immutable `ServerPaths` at construction;
the native host passes its runtime locations explicitly. Handlers and stores do
not consult later module-level path overrides. Legacy helper callers can still
use a snapshot of the old defaults. Production locations have not moved.

Projects, assets, recovery, preferences, themes, confirmation and change markers
belong to that runtime. Export output normally remains `imgs/editor` in the
installation; an explicit test export root isolates native qualification output.
Static resources and generated/game-export libraries remain installation-owned.
Session authorization is per server, not per Python module. Runtime isolation is
not multi-user security against other processes running under the same account.

Updater retirement is an exact file list from the immutable application snapshot.
It must not name current files, profile data or a directory tree for broad deletion.
Update/repair/rollback operate on program files without reverting newer recovery,
settings or assets. The editor retains the existing installation lock identity.

Production editors use their installation's Python/Qt/WebEngine only. The signed
publisher generates `KFPS.Editor/baseline.json` from the delivered runtime and
application. Startup checks the exact inventory, file content and engine identity
before importing Qt. A mixed or incomplete install gets an English/Korean repair
message; it does not silently use system Python, a default browser or pip.
The existing updater is the repair owner. Verification adds startup I/O, not
editing-time hashing. The contract is a consistency check, not protection against
a local attacker who can rewrite both files and contract.

The update lease is acquired with standard-library Windows calls before Qt loads.
If another process owns it, a bounded pre-Qt message can activate an existing
editor; otherwise startup stops. Lost acknowledgements are not replayed. Qualified
source/test-stage exceptions are explicit and do not weaken production startup.

This establishes one engine per delivered release, not identical graphics drivers
or an ability to update offline users. Security updates still require a newly
qualified and published runtime baseline; the engine must not remain frozen forever.
