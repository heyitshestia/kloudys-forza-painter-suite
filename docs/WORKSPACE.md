# Connected Workspace

Normal KFPS launch now opens the connected workspace through
`KFPS.UI/workspace.py`. The separate Vinyl Editor and Livery Studio launchers,
and the Chrome preferences, remain available. No project conversion is required.
`KFPS.UI/app.py --legacy-ui` retains the previous standalone KFPS shell for
diagnosis; background worker and inspection commands keep their existing routes.

## Everyday Workflow

1. Launch KFPS normally.
2. Use the KFPS, Editor and Studio tabs across the top. Editor and Studio load
   on demand; switching tabs retains the same document, selection and history.
3. In the Editor, use Place on car in the top toolbar to send the current vinyl. An already
   open Studio receives the vinyl without rebuilding its window or car scene.
4. In Studio, select a placement, expand Edit source artwork and choose Open in
   2D editor. A separate Source tab protects the ordinary Editor document.
5. Edit the artwork, then use Return to Studio in the top toolbar. Studio checks
   for returned artwork automatically. Choose the affected instances and Apply
   returned artwork when ready. Existing confirmation and Undo behavior remains.
6. Close a tab with its close button. Closing the whole workspace asks each
   document first. Cancelling preserves the other documents. Saved files and
   recovery data use the existing Editor and Studio locations and formats.

Loaded Editor tabs use the existing document title and unsaved `*` marker. Source
tabs show the original artwork name while retaining their private job identity.
The native and Chrome source Editor shows its destination and return state. Editing after return
shows changes not returned; undo to the returned history snapshot restores the
returned label. A different loaded document disables that source return link.
Studio distinguishes editing, ready, applying, applied and failed operations.
Receiving artwork alone is not an applied result, and checking status never
applies artwork. Titles and source names are displayed as text in all three
supported languages.

Existing Chrome preferences still launch those tools separately. A source edit
from a Studio session not owned by this workspace remains a separate editor.
Opening an already-running separate Editor reuses it rather than creating a
second owner for its data folder. Switching a host preference does not move an
already-open document between hosts; close it normally and reopen it.

Updated native Studio windows share an ownership guard with workspace tabs. A
second native owner of the same backend is refused before changing its theme or
staging artwork. Use the existing window, or save and close it first. A failed
Studio page can be closed with explicit discard confirmation; cancelling keeps
the page and ownership intact. The workspace's own cross-car package handoffs
retain the existing unsaved-document confirmation.

Chrome and native windows left open from before this update do not participate
in that guard. Close Studio windows before changing hosts or updating. Do not
manually switch cars in one of several pages sharing the same backend.

## Outputs And Liveries

Outputs opens directly in Generated. Use the Generated, Editor exports, Game
exports and Library tabs above the gallery to switch categories, using the same
active-tab styling as the workspace navigation. The existing folders and files
remain in place. Clicking the active tab keeps the current folder and selection;
Up stops at that category's root. Search, sorting, folder management, previews
and the existing files remain available. Each category remembers its folder,
search, sort, scroll position and selection. Switching to Editor or Studio and
returning does not reset the gallery. A refresh reconciles removed files without
moving outside the category. Community browsing has its own navigation state.

The selected artwork has consistent Edit vinyl, Place on car, Export to game and
Show file actions. Unavailable actions explain why. Place on car uses the existing
Studio handoff; it does not install anything into a game. Background imports,
downloads and scans refresh the library without changing what you are browsing.
Use the completed task's Open result action to navigate explicitly.

On narrow windows, Import / Export opens the transfer controls and Back to vinyls
returns to the gallery without resetting its state. Wide windows show both areas.
With a category tab focused, Left/Right changes category and Home/End selects the
first/last category.

Liveries opens directly without the WIP acknowledgement overlay. Confirmations
and validation before installing a livery are unchanged.

## Saving And Exporting

- Save project retains editable work in the existing Editor or per-car Studio
  project storage. Save As creates a separately named project.
- Export artwork produces transferable artwork, not an editable workspace save.
  Studio distinguishes original source vinyl from a transformed section export.
  The confirmation describes the chosen destination, game, sections and groups
  where the operation supports them.
- Export to game opens the existing transfer workflow. Live-memory operations
  and offline save-file operations retain their separate checks and confirmations.
  Studio's experimental full-design export keeps its existing validation gates.

Exporting does not clear unsaved project changes. A dispatched command is not a
successful save: existing write receipts and completion/error states remain the
authority. Cancelling a prompt leaves the document intact.

## Commands And Background Tasks

Use the command button beside the workspace tabs to search the current tool's
commands and common KFPS settings. The standalone KFPS title bar has the same
entry. Editor and Studio also have their own search buttons in native and Chrome
windows. Search shows registered shortcut bindings and disabled-action reasons;
it does not add or take over keyboard shortcuts. An action whose document or
selection changed since the search opened is rejected rather than sent elsewhere.

The adjacent Background tasks button lists current operations and a bounded
history of completed work. Stop safely is only offered when the existing worker
supports it. Generation cancellation retains its checkpoint; Retry failed retries
failed inputs only, not completed images. Game writes have no forced-stop control.
Review and Open result are explicit navigation actions. Merely finishing a task
does not open a dialog or move to another page.

The task view observes existing services rather than running a second queue.
Editor/Studio activity is checked only while the task view is open. History is
local to this application session, not a persistent job scheduler.

## Reopening A Session

Settings > Reopen previous workspace is off by default. Enable it to retain
bounded references to saved Editor and Studio projects and the last eligible
KFPS page. Reopened tool tabs initially remain placeholders: selecting one loads
the tool and its saved document. Reopen previous tabs is also available manually.
Studio can prepare the saved car when the default car differs.

Unsaved work goes through the existing Recovery interface; it is never silently
applied. Missing files leave the tool available without replacing current work.
Corrupt session metadata is preserved and automatic reopening is disabled until
the setting is explicitly changed. Private Source tabs, authentication URLs,
background jobs and artwork contents are not stored in the session manifest.

Right-click a workspace tab to close it or return to KFPS. Recovery remains in
each tool's existing recovery interface. Unsaved or busy tools retain their
existing guards. Closing a tool releases its host, while
switching tabs retains the document and uses the inactive-cache policy below.
Session reopening is a native workspace feature; Chrome retains separate windows
and browser ownership. This does not restore arbitrary browser tabs.

## Startup And Safety

- The ordinary KFPS window no longer waits for a forced five-second splash or
  a separate pre-window thumbnail pass. Existing background services own loading.
- PS2 and Xbox intro behavior remains available.
- Direct page launches select their destination before building the UI, avoiding
  an unnecessary Create-page load. Default Create startup follows the same path.
- Workspace admission retains the update lease and existing runtime integrity
  verification. Hosted tools borrow the lease; closing one cannot release it
  while others still run. A packaged verification still takes time on cold disks.
- Source transfers retain document/revision/session validation. Automatic status
  checks never apply artwork automatically. Failed checks leave a manual retry.
- Themes, shortcuts, project formats, renderers, live-memory operations and
  offline save-file processing are not replaced by the workspace.

## Inactive Previews

### Opening A Livery Package

In KFPS > Liveries > Packages, select a package and choose **Open in Studio**
below **Open 3D Preview**. Compact windows show these actions under **Details**.
The existing native/Chrome preference selects the destination. Studio validates
the package, prepares its exact car when needed, and opens all editable sections
with their groups, masks and transforms. Unsaved work retains the existing
Save/Discard/Cancel confirmation. The original package is unchanged; save a
Studio project for subsequent editing. Body paint and materials are not imported.
The action is intentionally unavailable for in-game save entries.
Native Studio can switch cars after its unsaved-work check. Chrome package
opening requires the matching car to be selected first: save current work, choose
that car in Studio, then open the package from KFPS. Automatic package car
switching is blocked in Chrome because other windows can share its backend.
This does not add cross-window coordination to the ordinary Choose car command.

### Loading And Idle Resources

Preview and Studio verify and reuse prepared-car files on disk instead of
repeating static preparation when the inputs still match. Studio can reuse an
inactive car folder owned by its current session when switching back, within its
existing workspace count limit. Preview also reuses verified saved atlases.
Changed inputs or missing artifacts require rebuilding. These are disk-reuse
optimizations, not an additional always-resident model or texture cache. They
do not alter UVs, rendering quality, preview resolution or game files. Cold opens
still require conversion, and first-time car switches can still take time.

Editor and Studio retain their documents, selections, history and background
operations when switching tabs. After about five seconds hidden, they trim their
largest rebuildable drawing caches to a per-document limit of 96 MiB, or 32 MiB
when the browser reports a device with at most 4 GiB memory. Smaller caches stay
warm for 30 seconds, extended to 60 seconds after a recent return. Remaining
disposable caches then expire. Browser timer throttling can delay cleanup.
This is a canvas-capacity budget, not a global process-RAM or GPU-memory limit.
Quick returns also restore any pending paint.

The Editor releases per-shape bitmap caches and unused preview buffers. Returning
shows the existing GPU preview while rebuilding larger documents in small batches.
Studio retains section preview canvases within that budget and shrinks its hidden
drawing buffer after five seconds. Only evicted or changed sections need rebuilding;
the car, decoded artwork and selected quality remain intact. Both standalone
windows and Chrome use the same page-visibility policy. Tabs are never discarded
or frozen, so recovery and source-return status checks can continue.

This reduces inactive memory, not the active document's inherent footprint. Large
documents still take time to rebuild their full caches; software-only rendering
can show larger stalls. It does not change game data, mask semantics, shapes,
preview resolution settings or the graphics backend.

## Diagnostics

The existing local log and problem report include workspace startup/admission,
tab ownership, handoff stages, session restore, cache operations and shutdown
outcomes. Correlation IDs connect the stages of one operation. Runtime
verification time is recorded separately from shell startup time.

Reports include the workspace component revision and on-demand source hashes so
an unpublished test build can be identified without changing its release version.
Lifecycle data uses bounded history and allowlisted fields, not artwork, project
names, authentication URLs or exception contents. This adds no automatic upload
or always-running diagnostic worker.

## Qualification Boundaries

Automated Windows checks use offscreen Qt and headless Chrome with isolated test
profiles. They cover real pages and server routes, prepared-car rendering,
1/300/3000-shape round trips, save/reopen, tab reuse, close cancellation, private
source isolation and explicit apply/undo. Software rendering flags belong only
to the test harness, not the product launcher.

Physical monitor transitions, hardware-specific graphics drivers, native OS
dialogs and foreground keyboard/focus behavior still need a user-driven check.
Automatic discovery of an installed FH6 and reuse of an owned backend were also
exercised. Qt display scaling was checked at 100%, 125% and 150%; this is not a
physical multi-monitor test. Game-save/live-memory correctness is outside this
hosting change; no game saves were modified during qualification.
