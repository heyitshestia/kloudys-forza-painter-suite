# Kloudy's FH6 Painter Changelog

## 3.1.10
- Fixed newly rendered thumbnails appearing in the Outputs browser only after changing folders; Generated, Editor, Game Export, and Library tiles now update immediately without rebuilding the folder view.

## 3.1.9
- Added fail-closed FH6 live-export ownership verification across the complete loaded group hierarchy, preventing content not owned by the current profile from being exported.
- Added authorized recursive flattening for owned grouped vinyls with parent-transform composition, exact layer-count validation, and no partial exports.
- Rechecked ownership and hierarchy identity after every live read, and made ownership refusals terminal so fallback scanners cannot bypass the decision.

## 3.1.8
- Added FH4 Microsoft Store/Xbox offline vinyl-library scanning and additive JSON import with full account-slot backups, concurrent-save protection, atomic index updates, and rollback verification.
- Preserved FH4-specific raw shape identities when returning exported vinyls to FH4 while retaining canonical cross-game normalization for FH5 and FH6.
- Updated Outputs, logging, Help, and supporter information for the complete FH4 offline workflow and its game-closed safety requirements.

## 3.1.7
- Added normalized FH4 online live import and export with the same cross-game JSON shape identities used by FH5, FH6, and FM8.
- Added a dedicated non-supporter Support tab with clearer one-time-purchase benefits, complete offline library workflow details, and automatic hiding after a supporter key activates.
- Removed the repeating top-right supporter advertisement so the Support tab is the single unobtrusive place for supporter information.

## 3.1.6
- Added append-only, content-aware backups of the complete `imgs` folder with a remembered destination and background progress.
- Made large Outputs libraries substantially more responsive when browsing folders and selecting, cutting, or moving hundreds of JSONs.
- Preserved cached thumbnails when JSONs are moved or copied so file management no longer triggers unnecessary preview regeneration.

## 3.1.5
- Rebuilt Outputs as a source-scoped file browser with back, forward, parent-folder, nested-folder jump, search, folder creation, renaming, copying, moving, pasting, and permanent deletion.
- Added File Explorer-style selection for JSONs and folders: single-click selection, Ctrl toggles, Shift ranges, Ctrl+A, keyboard file operations, and selection-aware right-click actions.
- Kept generated, editor, game-export, and Library storage boundaries protected while allowing folders and JSONs to share the same visible name safely.

## 3.1.4
- Fixed the calibrated FH6 live group locator rejecting valid modern shape IDs and translucent layers after it had already found the correct RTTI group.
- Replaced oversized fallback memory scans with exact active-vector validation while retaining count, table, pointer, transform, and mask safety checks.

## 3.1.3
- Rebuilt the Editor page as a searchable project manager with asynchronous previews, clear service status, direct blank-canvas and JSON workflows, and first-run tutorial controls.
- Reorganized the manual editor around a complete tool rail, persistent Layers and Inspector workspace, precise selection and arrangement commands, visible history, recovery, reference images, guides, masks, text, pixel art, and export checks.
- Separated editable projects, temporary recovery, and portable JSON exports with atomic writes, duplicate-name protection, unsaved-work confirmation, serialized preview rendering, and safer local editor endpoints.
- Expanded the in-editor tutorial, Help topics, user manual, editor manual, and automated coverage for project handling, local service security, responsive layout, and editor interaction contracts.

## 3.1.2
- Added a dedicated eight-slot Featured gallery before Browse in the Community Hub, with curated artwork removed from ordinary discovery views while remaining available in personal views.
- Made featured supporter thumbnails visible to everyone with a clear supporter badge and a friendly Ko-fi prompt for locked downloads, while retaining verified access for full previews and JSON files.
- Added live Featured slot tracking and an enforced eight-artwork limit to the moderation panel, plus scope-aware catalog caching so the complete gallery restores immediately on later launches.

## 3.1.1
- Fixed local Forza mask decoding so terminal and nested mask markers render correctly without hiding ordinary colored shapes.
- Made Regenerate Local Thumbnails replace every managed preview across Generated, Editor, Game Export, and Library sources, retain those replacements after restart, and invalidate caches by renderer content instead of file timestamps.
- Fixed the 300-layer editor GPU handoff so source overlays keep their orientation, saved project layer IDs cannot collide during duplication, and rapid duplicate, undo, and redo commands execute in order without losing layers.

## 3.1.0
- Upgraded the manual vinyl editor for responsive work at the full 3,000-layer FH6 limit with indexed canvas state, bounded parallel resource loading, reusable caches, and a virtualized searchable layer browser.
- Added a transient GPU interaction renderer for smooth pan, zoom, transforms, masks, and source overlays while retaining the exact Fabric render after each interaction settles.
- Reworked editor history and autosave around shared unchanged layers, differential object restoration, deferred writes, stable editor IDs, and faster bulk selection, replacement, grouping, and layer-order operations.
- Enforced the 3,000-layer maximum across imports and creation tools, completed all 40 upper-letter resource slots, preserved editable project metadata, and kept exported FH6 JSON free of editor-only fields.
- Added repeatable 3,000-layer performance, project/export compatibility, mask, fallback-renderer, autosave, history, interaction, responsive-layout, and layer-order regression coverage.
- Prevented Git-checkout updates from deleting ignored local state such as worker dependencies, Wrangler databases, `.dev.vars` secrets, local virtual environments, previews, or rollback files, and made file verification independent of the optional `Get-FileHash` PowerShell command.

## 3.0.100
- Replaced the rate-limited GitHub API update check with cache-busted raw version checks, visible connection status, five-minute polling, and patch notes refreshed directly from GitHub.
- Made forced local thumbnail regeneration survive app restarts by preferring the newest valid managed or adjacent preview while preserving newer personal PNG overrides.

## 3.0.99
- Allowed Community Library downloads to use live online import while keeping scanned game-save library items protected as already present in the game.

## 3.0.98
- Replaced the manual UI scale multiplier with native Windows DPI scaling, a freely resizable frameless window, compact responsive layouts down to 960x600, and saved normal/maximized window geometry.
- Made Regenerate Local Thumbnails force-render every browser-visible local JSON without the normal background item or time limits, replace KFPS-managed previews, preserve personal adjacent PNGs, and report partial failures accurately.
- Saved the latest validated FH6 RTTI registry during normal app startup so live importing can reuse it offline without replacing the last good cache after a failed network refresh.

## 3.0.97
- Connected live FH6 locator updates to the Cloudflare registry used by trusted calibrators, while retaining GitHub and every existing cached, packaged, built-in, and live-search fallback.
- Made registry-source changes refresh immediately so an older GitHub cache cannot delay a newly calibrated game build after updating KFPS.

## 3.0.96
- Added a yellow MASKS identifier to Community artwork tiles, derived from validated shape data so existing and future masked vinyls are labeled automatically.
- Added Regenerate Local Thumbnails to Settings, which safely clears the dedicated runtime thumbnail cache, reindexes every local output source, and rebuilds previews in a low-priority worker without changing artwork or JSON files.

## 3.0.95
- Rendered Forza mask layers as ordered cutouts in Outputs, Community uploads, and editor-browser thumbnails while preserving detail layers placed above each mask.
- Kept mask-free preview rendering byte-for-byte compatible with the previous renderer and added focused coverage for legacy mask flags, transparent output, checkerboards, artwork bounds, and layer order.
- Versioned Community preview and thumbnail URLs by their verified hashes so regenerated server assets replace stale cached images immediately.

## 3.0.94
- Added the public Night City 2077 theme for supporters and non-supporters, with original angular controls, packaged Rajdhani typography, saturated red/cyan signals, layered depth, scrolling glyph rails, restrained glitches, and custom page transitions.
- Added theme-owned popup, field, navigation, scrollbar, tooltip, and interaction treatments with clipped glow and readable 105% text while preserving reduced-motion, ambient-motion, and effects preferences.
- Refined every page and Community subtab around a consistent technical hierarchy: major groups use restrained route rails, previews and readouts are enclosed, repeated content stays lightweight, and the live-status channel remains clear of background telemetry.

## 3.0.93
- Added the public Apex Vector theme for supporters and non-supporters, with a flat high-contrast race-control interface, original technical assets, packaged IBM Plex fonts, restrained idle telemetry, and custom page transitions.
- Expanded the modular theme contract with optional theme fonts, isolated foreground telemetry, live semantic navigation colors, and clipped custom control treatments while preserving existing theme behavior.
- Showed the Ko-fi supporter promo throughout public themes when no key is installed, displayed the correct dynamic thank-you or support message, and kept Windows 94 and Overdrive 200X supporter-only.

## 3.0.92
- Added neutral checkerboard backdrops to Outputs and Community thumbnails, upload previews, detail views, and inspectors so transparent white or black vinyls remain visible in every theme.
- Kept preview rendering lightweight with one cached tiled texture while leaving stored preview images unchanged.

## 3.0.91
- Kept the live-status ticker aligned identically across Create and every Community subtab, and added a saved setting to show or hide it.
- Preserved manual generator overrides, reduced motion, ambient motion, and glass-effects choices across theme changes and app restarts instead of allowing theme selection to overwrite them.
- Made available updates blink the complete version pill between its neutral theme styling and a clear red alert treatment across every theme.

## 3.0.90
- Added the supporter-only Windows 94 theme with authentic square controls, classic four-color depth, recessed work areas, pixel-era typography, and Windows-style interaction states.
- Added dedicated classic treatments for the app shell, navigation, fields, previews, lists, dialogs, focus outlines, scrollbars, and title-bar controls while preserving other themes.
- Made the Reduce nonessential motion, Ambient background motion, and Glass shadows and effects settings start unchecked in Windows 94 without changing other themes' defaults.

## 3.0.89
- Added the public Command Prompt theme for supporters and non-supporters, with a square monochrome console interface and an optional theme-only green text mode.
- Restored clear Handmade and Toolmade classification colors and reliable black text on white selected controls throughout Community.
- Changed the fresh-install UI scale default to 105% while preserving each existing user's saved scale and theme preferences.

## 3.0.88
- Added the supporter-only Overdrive 200X theme with custom military-science-fiction hardware, animated perimeter lighting, micro-LED feedback, and theme-specific transitions.
- Expanded the modular theme system with isolated backdrop, foreground, control, icon, link, scrollbar, and page-transition treatments while preserving every existing theme.
- Refined shared QML controls and interaction states for consistent clipping, rounded surfaces, scrolling, hover feedback, reduced-motion behavior, and responsive layouts.

## 3.0.87
- Fixed FH5 Microsoft Store library scans by detecting direct and compressed C_group data inside opaque WGS save files instead of relying on filenames.
- Removed the 180-vinyl save-library scan ceiling and preserved valid cached vinyls that were not part of a later partial scan.

## 3.0.86
- Colored Handmade labels pastel pink and Toolmade labels baby blue throughout Community browsing, details, filters, and uploads.
- Preserved clear selected-filter styling and tuned the classification colors for readable contrast across all themes.

## 3.0.85
- Made Community artwork-grid scrolling as responsive as the Help tab for mouse wheels and touchpads.
- Made selected Community upload classification and audience choices clearly visible across every standard and supporter theme.

## 3.0.84
- Split Community upload classification and audience into independent choices, allowing one selection from each group.
- Cleared stale descriptions, tags, and confirmation state when preparing a different JSON while preserving metadata during revisions.

## 3.0.83
- Fixed release updates incorrectly failing after installing the valid native launcher introduced in 3.0.74.
- Updated launcher verification to recognize the current packaged executable used by both bundled and no-Python releases.

## 3.0.82
- Added a Supporters catalog and supporter-only upload audience to Community, while keeping the tab visible with a clear supporter-key offer for everyone.
- Added short-lived signed Community entitlements so supporter keys and activation receipts remain isolated from the Community service.
- Added owner controls for resetting a key's Community-account binding and immediate access removal when local supporter status becomes inactive.
- Synchronized the Community upload-version floor against the official repository VERSION, including scheduled checks and safe refreshes prompted by newer clients without trusting uploader-provided versions.

## 3.0.81
- Added mandatory Handmade or Toolmade classification for new Community uploads, with dedicated browse filters and classification-aware search.
- Added classification labels to artwork tiles and details while preserving Browse as the complete catalog view.
- Added tag editing for creators under Profile > My uploads while keeping classifications fixed after publication.
- Added client-version reporting so outdated KFPS builds can be blocked from submitting Community uploads.

## 3.0.80
- Fixed KFPS primitive ellipse previews so generated and Community JSON artwork renders at the intended size instead of as separated half-size shapes.
- Kept rectangle primitives and Forza type-code shape previews unchanged, with focused regression coverage for both rendering paths.

## 3.0.79
- Fixed Community uploads for very wide or tall vinyls by centering generated thumbnails on transparent square canvases that meet the server's preview limits.

## 3.0.78
- Added the Community Library for browsing, searching, sorting, inspecting, favoriting, following, uploading, and downloading shared vinyl JSONs directly in KFPS.
- Added GitHub Device Flow sign-in, endpoint-isolated Windows-protected sessions, permanent double-confirmed Community usernames, and restored server-side profiles across fresh KFPS installations.
- Added a tiled local upload browser and manual JSON picker with local preview rendering, schema/game detection, FD6 background conversion, server-side sanitization, duplicate checks, and immediate publication after validation.
- Required an account for both uploads and downloads, verified downloaded JSONs and checksums before saving them to the local Library, and added private reports plus post-publication moderation support.
- Added full-size artwork inspection, creator profiles, compatibility warnings, revision publishing, and clear use-at-your-own-risk guidance without claiming that Community content meets current game enforcement rules.
- Updated the bundled Pillow, pip, and setuptools runtime components to security-audited patched versions.

## 3.0.77
- Restored the previous production Galatea Genesis generator after V5 reduced visual fidelity on real artwork.

## 3.0.76
- Upgraded Galatea Genesis to V5 with qualified color-foundation and layer-order fidelity refinements, while retaining the V4-compatible workflow and exact fallback when a refinement is not beneficial.
- Restored an Open Output Folder shortcut for the shared generated, editor, game-export, and library folders.
- Kept Open Output Folder and Online Export from Game pinned on-screen at compact window sizes, with scrollable setup controls and clipping regression coverage.

## 3.0.75
- Changed the base theme's bottom-left sidebar note to "Consider supporting the project" while preserving supporter thank-you signatures and the Credits button.
- Replaced the rotating lights around the no-key supporter notice with fixed, slow-blinking lights that remain still in reduced-motion and screenshot modes.

## 3.0.74
- Made the advanced no-Python release launch through a validated system-installed 64-bit Python 3.12 when no packaged runtime is present.
- Kept bundled Python as the first choice, added the `KFPS_PYTHON` custom-path override, and rejected wrong-version or dependency-incomplete runtimes with clear recovery instructions.
- Activated the full-window wrong-download guard before normal app startup, including for source archives where a Python folder was added manually.
- Added repeatable launcher and release-layout regression tests covering bundled, system, custom, missing-dependency, source-blocked, and emergency-bypass paths.

## 3.0.73
- Added plain-language hover help to every interactive native app control and custom click target.
- Reworked all 22 Help topics for first-time users, including complete FH6 template setup and clear online/offline workflow guidance.
- Simplified unclear action labels across Create, Outputs, Editor, Reports, Settings, and Update.
- Kept the supporter badge, version pill, and announcement banner aligned consistently across tabs and fixed wrapped Update notes.

## 3.0.72
- Hardened generation saving so every completed V2 checkpoint writes a verified, atomic final JSON and matching preview image.
- Kept checkpoint finalization running if the app window closes or Genesis exits unexpectedly, preserving every usable completed checkpoint.
- Updated live previews every 100 shapes, including reliable same-file refreshes in the Create and Generate pages.
- Changed Force Stop to end the active Genesis search first and safely finalize completed checkpoints before abandoning the run.

## 3.0.71
- Prefilled manual generator override fields with the selected preset's normal values and added a clear label above every field.
- Kept displayed override defaults synchronized with automatic and manual preset changes while retaining seed 0 as normal randomized behavior.
- Restored generated vinyl previews to each run's previews folder, including migration from existing thumbnail-cache previews when available.

## 3.0.70
- Added automatic FH6 locator-profile updates through a validated shared RTTI.dat registry, while retaining cached, packaged, built-in, and slower fallback paths.
- Added the distributable six-step calibrator workflow for trusted maintainers to publish new game-build profiles through their own authenticated GitHub accounts.
- Added strict six-scan, privacy, bounds, cache, and live-memory checks so invalid or unavailable profile updates are ignored without blocking live import or export.

## 3.0.69
- Upgraded the bundled Galatea Genesis generator to V3 while retaining its existing command, JSON, checkpoint, preview, and resume compatibility.
- Added final-visible color reoptimization so overlapping shapes preserve more local contrast, shading, and fine detail.
- Improved verified quality and generation speed at normal 1,000-2,000 shape workloads, with conservative full-corpus shape-count savings.

## 3.0.68
- Replaced the bundled Galatea Genesis generator with the fully compatible Genesis V2 engine.
- Improved detail and edge retention at normal 1,000-2,000 shape workloads while reaching comparable quality with fewer shapes.
- Added export-quantized scoring, multiscale residual search, adaptive source handling, and safer transparent-edge behavior without changing the KFPS generation workflow.

## 3.0.67
- Improved supporter access recovery after registration changes.
- Restored supporter access now returns automatically on the next connected launch.

## 3.0.66
- Improved supporter access reliability across restarts and temporary service interruptions.
- Hardened supporter checks against malformed or unavailable service responses.
- Added owner-side maintenance tools for resolving registration issues.

## 3.0.65
- Added automatic one-device supporter access while keeping public KFPS features available during service problems.
- Added secure local supporter access for reliable offline use.
- Added device-transfer recovery, clearer in-app guidance, and broader Windows compatibility coverage.
- Added automated Ko-fi purchase synchronization to the separate local supporter-management tool.

## 3.0.64
- Added startup output indexing with a short loading splash so large JSON libraries are cached before the Outputs page opens.
- Moved missing JSON thumbnail rendering into a separate worker process and merged newly rendered previews into the open Outputs grid.
- Prioritized thumbnail warming for the currently selected output source, including Library, and added visible thumbnail warm status text.

## 3.0.63
- Queued existing JSON thumbnail URLs one at a time too, preventing generated, exported, and library source switches from loading every cached thumbnail at once.
- Reworked the Update tab into a wide side-by-side layout with update controls beside patch notes.

## 3.0.62
- Deferred missing JSON thumbnail rendering into a throttled background queue so large output folders stay responsive at startup.
- Moved patch notes from Settings into the Update tab, keeping Settings focused on local folders and maintenance shortcuts.

## 3.0.61
- Moved generator seed controls behind Manual generator overrides so normal runs keep the default seed behavior.
- Added hover help for generation options, including guidance that KFPS chooses most options automatically and that 2x Mode is the normal-user option for slower, deeper matching.

## 3.0.60
- Extended the centered supporter badge, version pill, and live status banner alignment from Create/Generate to the other app tabs.
- Reserved the right-side page title area so header banners and pills stay clear across wider tab layouts.

## 3.0.59
- Added an in-app Credits page from the sidebar footer with detailed community, ForzaLiveryStudio, upstream project, and license acknowledgements.
- Reduced the live scrolling status banner by 5 px on each side to tighten its header alignment.

## 3.0.58
- Added background FD6 JSON detection for manual imports.
- Converted FD6 ellipse and rectangle shape JSONs into KFPS type-code JSONs without modifying the original file.
- Manual FD6 imports now appear in Exported with KFPS metadata and shape counts.

## 3.0.57
- Improved Fabric editor responsiveness for large vinyl projects by moving pan, zoom, and transform previews onto the GPU hybrid path sooner.
- Kept layer visibility and selection state intact during GPU preview, then restored the normal Fabric render after interaction settles.
- Prewarmed large-project GPU preview meshes after import/restore to reduce first-interaction stalls.

## 3.0.56
- Centered the supporter badge, version pill, and live status banner over the main Create/Generate panels.
- Made the live status banner scroll continuously with a tighter repeat gap.
- Added a Browse outputs search field that filters vinyls by name within the selected output source.

## 3.0.55
- Improved Fabric editor rendering for transparent Community Vinyls 1, 2, and 3.
- Made selected-shape outlines thinner and steadier across zoom levels.
- Added an experimental GPU preview path for large editor projects to make pan, zoom, and selected-layer movement smoother.

## 3.0.54
- Restored FM8 as a save-library target now that offline imports use the separate FM8 local-save writer.
- Fixed FM8 offline save-library decoding for grouped vinyls so group transforms keep their intended positions.
- FM8 save-library rows now use local header names and show shape counts.

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
