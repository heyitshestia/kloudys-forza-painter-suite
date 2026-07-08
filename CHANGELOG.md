# Kloudy's FH6 Painter Changelog

## 3.0.53
- Added a live scrolling status banner backed by a remote announcement feed.
- The banner can be clicked to pause or resume scrolling.

## 3.0.52
- Reworked the Outputs browser into a JSON-first thumbnail grid.
- Generated outputs now stay grouped by generation run, newest first, with checkpoints ordered from low to high layer count.
- Added FH5 offline save-library scanning and a first-scan warning for large vinyl libraries.

## 3.0.51
- Kept FH6 offline save-folder import visible while temporarily hiding FM8 from the game target dropdown.
- Prepared the offline save-library path for FH5 scanner work.

## 3.0.50
- Improved native window restore behavior and text sharpness.

## 3.0.49
- Improved offline FH6 imports for generated JSONs and transparent save thumbnails.

## 3.0.48
- Added supporter-gated offline FH6 save-folder library scanning and one-button offline JSON import.
- Offline imports create a fresh FH6 LayerGroup folder with a transparent thumbnail.
- Clarified online probe import/export labels and kept offline import greyed out for FH5/FM8 until tested.

## 3.0.47
- Added another Forza Motorsport process name for detection.

## 3.0.46
- Improved update tab clarity.

## 3.0.45
- Improved update page and update relaunch behavior.

## 3.0.44
- General preview and editor compatibility fixes.

## 3.0.43
- General UI cleanup.

## 3.0.42
- Restored the Tools tab with source preparation shortcuts.

## 3.0.41
- General bug fixes and settings stability improvements.

## 3.0.40
- General bug fixes and stability improvements.

## 3.0.39
- General bug fixes and import/export stability improvements.

## 3.0.38
- General bug fixes and importer/exporter compatibility updates.

## 3.0.37
- General bug fixes and UI polish.

## 3.0.36
- General bug fixes and UI polish.

## 3.0.35
- General bug fixes and UI polish.

## 3.0.34
- General bug fixes and UI polish.

## 3.0.33
- Improved Create preview refresh and live generation log behavior.
- Cleaned stale app files and documentation references.

## 3.0.32
- Removed stale development docs and unused theme references.

## 3.0.31
- Improved native theme handling and UI polish.
- Improved output selection and scrolling behavior.

## 3.0.30
- General bug fixes and UI polish.

## 3.0.29
- Reworked the native QML app around a creator-first, no-scroll workflow layout.
- Added the new Create page and consolidated output browsing into the Outputs workflow.
- Kept legacy navigation routes working for existing shortcuts and update flows.

## 3.0.28
- Fixed the editor eyedropper so source overlays placed above vinyl layers are sampled before the layers beneath them.

## 3.0.27
- Changed the shipped KFPS executable into a small launcher for the loose QML app files.
- Hardened updater replacement with SHA256 verification so old and new `KFPS.exe` files cannot be confused.
- Kept the native launcher repair payload inside the app folder for future updater self-repair.
- Removed the in-app bundle check panel from Settings.
- Removed the obsolete PyInstaller single-file packaging path.

## 3.0.26
- Reworked the native Help tab into a searchable guide with categories, step-by-step workflows, warnings, related topics, and a support checklist.
- Added a dedicated FH6 3000 plain white circle template guide for importing.
- Expanded troubleshooting for release-vs-source downloads, expected folder layout, bundled Python, dependencies, and update/runtime issues.
- Increased Help tab text size and panel contrast for better readability.

## 3.0.25
- Added an updater safety guard so the updater refuses to run outside a real KFPS app folder.

## 3.0.24
- Fixed updater bootstrap quoting so manually downloaded GitHub raw updater batches can hand off to a CRLF-normalized updater.

## 3.0.23
- Fixed updater bootstrap so GitHub raw batch files are normalized to Windows CRLF before execution.

## 3.0.22
- Hardened updater verification so every Git-tracked program file is hash-checked and repaired after update copy.
- Kept generated/runtime/user data preserved while verifying the native KFPS executable one folder above the app root.
- Changed the native update button to fetch a fresh updater script before launching updates.
- Fixed updater batch formatting for more reliable Windows command processing.

## 3.0.21
- Fixed updater self-replacement by running updates from a temporary handoff copy before mirroring program files.

## 3.0.20
- Hardened the updater to mirror program files from GitHub, preserve generated/runtime data, verify critical copied files, verify the native launcher hash, and fail loudly if retired app files remain.

## 3.0.19
- Fixed bundled QML helper bridges resolving backend scripts from PyInstaller temp folders during generation and import/export.

## 3.0.18
- Fixed native updater marker repair so an already-current root KFPS executable does not trigger an unnecessary binary payload download.

## 3.0.17
- Changed the in-app updater to launch the GitHub batch updater directly and close KFPS.
- Removed the in-app updater's immediate auto-relaunch path to avoid transient PyInstaller `_MEI` Python DLL load failures after updates.

## 3.0.16
- Restored multi-image generation queue support in the native Generate tab.
- Restored double-click custom target layer entry with automatic checkpoint suggestions.
- Fixed JSON browser previews so generated checkpoints use the selected checkpoint preview while editor exports use the editor-specific preview path.

## 3.0.15
- Fixed updater binary checks so normal updates do not redownload the QML executable when it is already installed.
- Existing installs with a leftover WPF root executable still repair automatically by reusing the 3.0.14 binary asset.

## 3.0.14
- Fixed Git-checkout/native test installs so updating also installs the QML root executable, not only the app files.
- Kept WPF-to-QML release migration behavior unchanged.

## 3.0.13
- Migrated the shipped app shell from the native WPF prototype to the QML KFPS desktop app.
- Hardened the updater so existing WPF installs can migrate cleanly in one update.
- Removed retired WPF app files from the repo layout and release package.
- Split executable updates into a binary-only updater asset while keeping full bundled releases for fresh installs.

## 3.0.12
- Cleaned the native WPF theme bundle down to Night Blossom and Blackout.
- Fixed clipped native text fields in Help, Reports, Settings, and custom layer prompts.
- Removed extra inner borders from the Help search and report title fields.
- Ships the KFPS logo JSON in every JSON browser source and refreshes those copies on app launch.

## 3.0.11
- Reworked the native Night Blossom shell with the dedicated animated blossom backdrop.
- Added dashboard card hover motion and denser ambient petals.
- Fixed the JSON tab layer-count field so the value is not clipped.

## 3.0.10
- Fixed the native FM8 export option so it maps to the backend Forza Motorsport profile.

## 3.0.9
- Changed the dashboard bottom panel into a changelog view while keeping runtime logs on other tabs.
- Fixed the top version text position so status updates no longer move it around.
- Adjusted the dashboard changelog textbox spacing so text is not clipped at the top or bottom.

## 3.0.8
- Fixed generated final JSONs carrying an extra background/canvas layer, so checkpoint layer counts now match the selected target.
- Added the KFPS logo JSON to the shipped exported JSON folder.

## 3.0.7
- Set Night Blossom as the only exposed native theme and default theme.
- Fixed native WPF theme resource updates so frozen brushes and gradients do not trigger UI warnings.
- Kept the native app as a single-file bundle without loose WPF runtime DLLs.

## 3.0.6
- Added the first native WPF resource dictionary for Sakura Glass theme materials.
- Added reusable procedural texture resources and a subtle Sakura texture overlay.
- Added resource-backed animated button hover/press visuals for future texture and animation work.

## 3.0.5
- Restored the FH6 1000-layer group/table locator support script that was unintentionally left out of the native 3.x tree.

## 3.0.4
- Limited the native theme dropdown to Sakura Glass while keeping the other theme definitions available in code.
- Moved update controls into a dedicated Update tab with current/latest version display.
- Update availability now changes header text color and blinks the Update tab button instead of using a colored header pill.

## 3.0.3
- Fixed the Generate preview panel so starting a new run immediately takes over from older JSON/export previews.
- Live generation preview polling now refreshes when the generator reports preview progress.

## 3.0.2
- Switched the native version indicator to GitHub's contents API so checks do not get stale raw-cache results.

## 3.0.1
- Added a centered native version indicator that checks GitHub main every minute.
- The version indicator turns red and blinks when a newer version is available.

## 3.0.0
- Replaced the old PySide launcher/app shell with the native KFPS desktop app.
- Added native self-update handoff so KFPS closes before replacing the root executable.
- Cleaned the packaged app layout and removed retired 2.x UI files from the shipped tree.
- Kept generator, editor, importer, exporter, and bundled backend tools wired through the native interface.

## 2.0.64
- Updated the FH6 fast locator profile from the latest calibration pass.
- Fixed calibrated locator fallback so stale game-build profiles no longer block normal fallback scanning.

## 2.0.62
- Added a dedicated Fabric editor Text tab for generating editable vinyl text from real Forza font shapes.
- Moved text generation out of Guides and kept it focused on the supported in-game Forza fonts for now.

## 2.0.61
- Adjusted Fabric editor transform handles so they sit farther from small shapes and rotate with the selected shape.
- Improved editor rendering for large vector shapes and expanded gradient-preview detection to more gradient/shadow shape types.

## 2.0.60
- The Fabric editor now opens with the system default browser instead of preferring Microsoft Edge when Edge is installed.

## 2.0.59
- Fixed updater path handling for Windows usernames and folders with apostrophes.

## 2.0.58
- bongocat

## 2.0.57
- Added a Settings option for app UI scale to help users with unusual Windows display scaling.
- The scale setting is saved locally and applies after restarting KFPS.

## 2.0.56
- Added experimental Forza Motorsport export detection.
- FM exports now convert Motorsport shape resources into FH6-compatible JSONs for editor preview and FH6 import.
- Kept FH5 and FH6 import/export behavior separate from the FM conversion path.

## 2.0.55
- Reworked the Fabric editor layout into a cleaner Krita-style workspace with a dominant canvas and one larger right-side dock.
- Added an interactive editor tour that switches tools/tabs and explains the main workflow from import through export.
- Made the editor launch in a dedicated fullscreen/maximized browser app window when Edge or Chrome is available.

## 2.0.54
- Added a pixel-art auto-fill tool to the Fabric editor that detects the source pixel grid and builds square vinyl rectangles from it.
- Pixel-art conversion now keeps exact visible source colors, skips transparent cells, and merges only identical-color blocks horizontally or vertically.
- Removed the earlier pixel-art resolution presets in favor of source-faithful grid detection.

## 2.0.53
- Added generator seed controls with randomize, fixed, increment, and decrement modes.
- Fixed source-aware preset selection not refreshing after choosing a different image.
- Fixed the import tab sometimes showing a newer finalized JSON while still importing a previously selected JSON.

## 2.0.52
- Tuned the Galatea Genesis shaded character preset for cleaner fine detail on detailed anime/digital-art sources.
- Raised the shaded character working resolution after harness testing on multiple character images.
- Kept the generator executable unchanged; this update only adjusts the shipped preset/version metadata.

## 2.0.51
- Updated Galatea Genesis with layer-count-aware late mutation scaling.
- Tuned shaded character generation for faster high-layer detail runs.
- Kept flat/livery generation on the fuller search profile for better solid color adhesion.
- Updated bundled generator preset descriptions for Galatea Genesis.

## 2.0.50
- Replaced the bundled V7 generator with Kloudy's Galatea Genesis.
- Updated generation, release packaging, and updater process handling for the new generator executable name.

## 2.0.49
- Added a Fabric editor theme adjuster that can save custom file-backed editor themes.
- Improved multi-shape/group flipping so selections flip as one object instead of flipping each layer independently.
- Improved duplicated selection precision to avoid rounded scale drift.

## 2.0.48
- Added an Open Folder shortcut to the Fabric editor project browser for bulk project-file imports.
- Fabric editor project saves now preserve source overlay image data and exact overlay placement when an overlay was used.

## 2.0.47
- Improved Fabric editor shape selection accuracy for small edge-cleanup details.
- Reduced Fabric editor canvas lag while panning, zooming, and editing high-layer vinyls.

## 2.0.46
- Improved Fabric editor JSON export confirmation and internal project save/load handling.

## 2.0.45
- Added the Arc Reactor Red app theme with matte red panels and metallic gold controls.

## 2.0.44
- Added visible FH6 shape word labels under each Fabric editor shape-library tile for easier shape-code debugging.

## 2.0.43
- Improved Fabric editor grid snap feedback so the highlighted snap edge matches the actual snapped edge or corner.

## 2.0.42
- Fixed finalized checkpoint preview PNGs so every requested Finalize at Layers checkpoint gets a saved preview.

## 2.0.41
- Fixed the Generate tab preview being replaced by an unrelated Import JSON preview after generation finishes.
- Fixed collapsed Fabric editor groups expanding unexpectedly after undo/redo or editor state rebuilds.

## 2.0.40
- Made Fabric editor theme selection persist across editor restarts.
- Added app-folder temp recovery for unsaved Fabric editor work after an unexpected editor/server shutdown.

## 2.0.39
- Improved Fabric editor grid performance while panning and zooming the canvas.

## 2.0.38
- Fixed Dashboard shortcut buttons for Generate, Open Editor, and Import.

## 2.0.37
- Fixed Fabric editor flip actions becoming unreliable after larger multi-layer selections.
- Reduced redundant editor redraws while moving, snapping, rotating, and updating selection outlines.

## 2.0.36
- Improved JSON organization so generated, handmade, and editor/exported JSONs are browsed from separate import sources.
- Copied successful game exports into the editor JSON folder so they can be selected from the Import JSON browser.
- Fixed editor JSON exports not immediately appearing in the editor browser after saving.
- Improved browser layer counts for editor/exported JSONs.

## 2.0.33
- Restored the stable 2.0.27 editor baseline while keeping the current generator preset updates.
- Kept the updated raw FH6 import/export locator backend without experimental editor shape-resource caching.
- Removed the WIP seed/resource editor path from the shipped build.

## 2.0.27

- Changed Fabric editor corner dragging so normal corner drag scales shapes globally by default.
- Changed Fabric editor Shift+corner drag to skew shapes instead of scaling them.
- Reworked single-shape selection visuals so unselected shapes stay flat and selected shapes use an internal clipped rim instead of an outside halo.
- Reduced high-zoom manipulation UI clutter while keeping large invisible hit areas for easier grabbing.

## 2.0.26

- Added Ctrl-click layer-list multi-select in the Fabric editor so individual non-contiguous layers can be selected together.
- Fixed multi-selected layers moving unpredictably by normalizing Fabric selections before rebuilding them.
- Fixed drifting or stale editor hit boxes by syncing Fabric canvas geometry after layout changes, imports, shape creation, duplication, replacement, and transforms.
- Improved selected-shape highlighting so it uses a boundary-only outer edge outline without internal mesh geometry or flashing filled interiors.

## 2.0.25

- Improved Fabric editor selected-shape outlines so zoomed-in borders sit outside the vinyl shape instead of covering the shape edge.

## 2.0.24

- Fixed Fabric editor layer-list Shift-click range selection after scrolling or pointer-drag handling.
- Improved layer-list selection anchoring so contiguous ranges remain selected reliably.

## 2.0.23

- Improved Fabric editor responsiveness and selection behavior for dense vinyls.
- Added source-overlay move controls so reference images can be adjusted without grabbing vinyl layers.
- Improved guide handling so guide changes participate more reliably in undo/redo.

## 2.0.22

- Improved Fabric editor transform handles with more usable Figma-style corner, side, and rotate controls.
- Improved Fabric editor drag and pan performance by removing expensive selected-shape shadows and avoiding inactive snap overlay work.
- Added layered SVG overlay controls for flipping through reference, guide, and color layers.
- Removed internal development notes from the public package.

## 2.0.21

- Fixed shared JSON preview transforms for exported vinyls with negative scale and skew.
- Improved grouped export flattening so unresolved child groups are not exported as blank drawable shapes.

## 2.0.20

- Relaxed grouped vinyl export validation to reduce false refusals and improved parent negative-scale handling during grouped export flattening.

## 2.0.19

- Improved Fabric editor mask handling, layer editing, shortcuts, and small-shape transform controls.

## 2.0.18

- Improved diagnostic log privacy for import/export troubleshooting.

## 2.0.17

- Improved grouped and nested FH6 export flattening so parent group scale, rotation, skew, and negative scale are applied to child layers instead of only parent position.
- Improved fast export validation so current game exports can use the fast locator report without requiring the old fallback probe report.

## 2.0.16

- Added a basic FH5/FH6 target switch for import/export testing.
- Added a small FH5 compatibility notice in the importer and exporter.
- Improved shared JSON preview handling for generated, handmade, editor, and exported JSONs.
- Improved Fabric editor JSON browser and editor startup behavior.

## 2.0.10

- Fixed the native Windows launcher opening the launcher window behind other windows.
- Verified launcher setup buttons still run the Python setup and dependency setup batch files correctly.

## 2.0.9

- Rebuilt the Windows launcher as a smaller native launcher.
- Improved updater handling when the launcher executable is still running or locked.
- Added release checks to prevent packaging the old launcher format again.

## 2.0.8

- Fixed Fabric editor transform behavior for mirrored shapes, side resizing, corner skewing, and light-theme selection visibility.
- Improved editor JSON round-trip handling for negative scale values.

## 2.0.7

- Improved FH6 import/export memory locating from grouped, ungrouped, and nested-group dump analysis.
- Unified the app importer around one JSON import flow for generated finals, editor exports, hand-edited JSONs, and game exports.
- Made the Import JSON page fit the default app window without an outer page scroll; only the checkpoint list scrolls.
- Added a compact read-only FH6 research dumper for collecting locator diagnostics.

## 2.0.2

- Fixed Fabric editor live overlay color adoption for newly added, moved, nudged, and manually edited shapes.

## 2.0.1

- Fixed Fabric editor primitive import/export mapping so FH6 JSONs keep normal primitive shapes instead of resolving some codes to the wrong border-style resources.

## 2.0.0

- Reworked the main app shell into a wider workflow layout with a left-side navigation rail and dashboard.
- Added a local-only Bug Reports page that builds redaction-friendly reports for preview, copy, or local save without automatic upload.
- Added Eurocorp, Elite, CryNet, UNATCO, New Eden, Red Phosphorous, Blackout Violet, Blue Terminal 90s, and Matrix Green themes.
- Added BIOS-style Blue Terminal visuals, Matrix Green animated falling-code visuals, and terminal-safe monospace sizing.
- Added an optional Blue Terminal 90s dial-up sound loop while generation is running.
- Moved generator Pro Settings for manual resolution/random/mutated sample overrides into Settings while keeping layer count and finalize checkpoints in the Generate page.

## 1.10.80

- Corrected Fabric editor primitive names against the actual bundled primitive thumbnails instead of the old FH5-derived order.

## 1.10.79

- Restored verified primitive display names in the Fabric editor, so basic shapes such as Square and Circle are named normally again.

## 1.10.78

- Fixed Fabric editor full-library shape placement so chosen shapes keep their exact family/resource slot instead of reverse-mapping colliding FH6 words back to primitives.
- Fabric editor exports now preserve `resource_family`, `resource_index`, and `shape_name` metadata for reliable editor round-trips.

## 1.10.77

- Changed Fabric editor non-font shape labels to verified FH6 family/slot/word labels instead of guessed FH5-derived names.
- Font pages still show FH6 font glyph labels from the dumped font registry.

## 1.10.76

- Updated the Fabric editor color controls with an 8-slot saved-color picker, shape/source eyedropper toggle, and protected undo floor for loaded designs.
- Fixed Fabric editor shape-library slot mapping so FH6 shape words follow the calibrated slot order instead of one-by-one FH5-style increments.
- Filled missing FH6 font labels from the dumped font registry, including lower-case A slots.

## 1.10.75

- Fixed late-generation stalls where the generator kept retrying after the detail gate was mostly satisfied while the visible layer timer still looked fast.
- Generator logs now show accepted-layer wall time and retry count, making slow late layers visible instead of hidden.
- Presets now use bounded no-improvement retry counts and less aggressive late weak-shape gating.
- Added a permanent app-folder verification check to the bundled generator executable.

## 1.10.74

- Updated the V7 presets from prototype quality testing.
- Flat Colors now uses stronger edge-detail sampling with guarded rectangle use.
- Shaded Character Art now uses stricter late weak-shape gating and finer late-detail sampling.
- Smooth Gradients now uses a lower sample count with tuned soft-detail weighting for similar quality at better speed.

## 1.10.73

- Updated the GitHub updater to stop stale Kloudy's Painter generator/editor/app subprocesses automatically before syncing.
- The updater now logs which known process IDs it stopped and only fails if Windows refuses to terminate one.

## 1.10.72

- Replaced the Editor tab launcher with the bundled Fabric FH6 editor.
- Added the Fabric editor shape library with searchable shape names, explicit favorite buttons, remembered shape color, viewport-centered shape placement, and live overlay color sampling.
- Removed the editor canvas guide frame from the default view for cleaner manual placement.

## 1.10.68

- Promoted the tested prototype generator to `KloudysGeneratorV7.exe`.
- Updated the shipped presets for V7 raw-first output: sharper shaded-character defaults, lower rectangle pressure on faces/gradients, and legacy Edge Repair disabled by default.
- Updated the app, release packager, and updater cleanup rules to use V7 and retire old V6 generator binaries during updates.
- Added generator V7 notes so future tuning work stays documented instead of living only in test folders.

## 1.10.67

- Fixed FH6 imports reusing stale auto-locate session data after a previous import/save/reopen cycle.
- Normal FH6 imports now force a fresh template scan before every write.
- Added a final live group count/vector safety check inside the importer so stale tables abort before any layer is written.

## 1.10.66

- Hardened FH6 template locating by rejecting stale layer tables whose group vector metadata does not match the active editor template.
- Handmade import now requires a fresh saved/reopened plain white circle template before writing, preventing second-import writes into already-trimmed groups.
- Renamed the bundled V6 generator executable to `KloudysGeneratorV6.exe` and made the updater remove the old filename.
- Converted in-app `?` help buttons to hover tooltips.
- Added generator V6 follow-up notes for future tuning work.

## 1.10.65

- Added the bundled Forza Vinyl Studio editor as an `Editor` tab launcher.
- Shipped the editor as a self-contained Windows runtime so users do not need to install .NET separately.
- Added Forza Vinyl Studio credits and license notices.
- Replaced the old standalone Luma Band Pass tab with the editor launcher.
- Made the footer Ko-fi support button wider and marked it as optional.

## 1.10.64

- Updated the bundled generator to `KloudysGeneratorV6.exe`.
- Reworked the stock presets to `Shaded Character Art`, `Flat Colors`, and `Smooth Gradients`.
- Presets now keep their own resolution/sample settings by default; Pro settings are the only manual override.
- Added adaptive late-layer workload controls to the shipped preset files.

## 1.10.63

- Finalization now preserves the requested layer budget when covered-layer cleanup has no excess layers to remove.
- Flat opaque/luma runs now stabilize large single-color regions to reduce milky color variation in broad fields.

## 1.10.62

- Launcher version and changelog checks now prefer GitHub contents/raw API responses, with raw file URLs as fallback.
- This avoids stale raw-CDN version text immediately after pushes.

## 1.10.61

- Launcher GitHub checks now read from `refs/heads/main` so version and changelog checks avoid stale raw `main` aliases.

## 1.10.60

- GitHub version and changelog checks now use cache-busted raw URLs so the launcher sees fresh `main` updates more reliably.

## 1.10.59

- Launcher changelog now loads update notes from GitHub `main` instead of reading local updater log files.
- The launcher keeps the live action log small at the bottom while the larger upper pane shows these GitHub update notes.
- If GitHub cannot be reached, the launcher falls back to the bundled local `CHANGELOG.md`.

## 1.10.58

- Added a slim Ko-fi support button to the bottom footer of the main app.
- The Ko-fi button opens the support page in the default browser and stays outside all workflow tabs.
- Restored the shipped generator binary to the tracked main version after local engine testing.

## 1.10.57

- Improved transparent fringe cleanup before generation so bad background-removal pixels have less impact on edges and source matching.
- Kept the generator/output workflow compatible with existing presets and finalized JSON browsing.
