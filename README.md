# KFPS

> **Support KFPS**
>
> Hi! Enjoying KFPS? Supporting me on Ko-fi helps me keep improving it and bringing new ideas to life. Thank you for being part of the community!
>
> <a href="https://ko-fi.com/s/2d1507698d"><img src="docs/screenshots/showcase/ko-fi-support.avif" alt="Support me on Ko-fi" width="240"></a>

**Kloudy's Forza Painter Suite**

Turn an image into Forza vinyl shapes, build artwork by hand, and keep your designs together in one Windows app. KFPS combines GPU-assisted generation, a standalone vinyl editor, file management, community sharing, and game-specific import and export tools.

**[Download KFPS](https://github.com/heyitshestia/kloudys-forza-painter-suite/releases/latest)** · **[Community Discord](https://discord.gg/hRu8AtzD9j)**

![KFPS Create page showing a freshly generated Mini Kloudy vinyl and completed generation results](docs/screenshots/showcase/create.png)

*Mini Kloudy, generated with the Shaded Character Art preset at 3,000 shapes. Screenshots throughout this page are fresh captures of KFPS 3.1.75, not mockups. Artwork shown with Kloudy's permission.*

## Contents

- [Get Started](#get-started)
- [Create a Vinyl](#create-a-vinyl)
- [The Standalone Editor](#the-standalone-editor)
- [Outputs and Game Transfer](#outputs-and-game-transfer)
- [Full-Car Liveries](#full-car-liveries)
- [Community](#community)
- [Image Tools](#image-tools)
- [Themes](#themes)
- [Support KFPS](#support-kfps)
- [Help and Updates](#help-and-updates)
- [Credits and Licenses](#credits-and-licenses)

## Get Started

1. **Download the official bundled ZIP** from [Releases](https://github.com/heyitshestia/kloudys-forza-painter-suite/releases/latest). Extract the whole archive into a writable folder. GitHub's **Source code** ZIP is not the ready-to-run app.
2. **Start `KFPS.exe` and check Update.** The public updater can be newer than the downloadable bundle; not every patch gets a new bundle. Keep the executables and application folder together.
3. **Choose your starting point.** Use **Create** to turn an image into shapes, or **Editor** to draw by hand or edit an existing JSON.
4. **Inspect your output.** Wait for generation to finish finalizing, then choose a finished JSON in **Outputs**. Save an editor **project** as well if you want to keep editing later.
5. **Move it into the game.** For live import, open your saved 3,000-circle template in the game's **Vinyl Group Editor**, leave KFPS's import count at **3000**, and import the selected JSON. Save and reopen the vinyl in-game before judging the result.

**You need:** Windows, enough free disk space for the bundle and your artwork, and a working OpenCL-capable GPU driver for image generation. The manual editor does not need a generation job. Live transfers need a supported game running on the same PC; local-save tools have different requirements [below](#supported-transfer-paths).

> **Template setup:** Save and reopen a newly created template once. Ungrouping it is still recommended for easy inspection and troubleshooting, but is no longer mandatory for supported group layouts. An empty canvas is not a 3,000-layer template.

## Create a Vinyl

KFPS approximates your image using shapes the game understands. Choose a source, let the source check suggest suitable settings, and select how many shapes to spend on the result.

- **Presets for different artwork:** shaded characters, flat-color designs, and smooth gradients.
- **Live preview and progress:** see the result develop and keep the generation log close by.
- **Several finished versions from one run:** save checkpoints at different shape counts and choose the version that balances detail and complexity.
- **Image queues and optional extra search:** process multiple sources or try 2x Mode when more search time is worthwhile. It does not double the final layer count.

Transparent PNGs are a useful starting point for cutout artwork. More layers can help, but cannot recover details missing from a blurry source. Leave advanced preparation options at their defaults until there is a specific problem to solve.

**Wait for finalization.** Use **Generated finals** in Outputs, not the raw recovery checkpoints. Finishing the shape search and finishing the import-ready files are separate steps.

## The Standalone Editor

![The standalone KFPS editor with the generated Mini Kloudy design, layer controls, and native shape library](docs/screenshots/showcase/editor-workspace.png)

Open it from KFPS's **Editor** page or run **`KFPS Editor.exe` beside `KFPS.exe`**. Both entry points use the same workspace. The editor has its own window and can keep running after KFPS closes; you do not need to work in a browser tab.

| Work on | What the editor provides |
| --- | --- |
| Shapes and layers | Native shape library, search, favorites, grouping, locks, visibility, and layer ordering. |
| Precise placement | Position, size, rotation, alignment, snapping, guides, and reference-image tracing. |
| Text and pixels | Native Forza lettering and pixel-art conversion within the shape budget. |
| Color | Recoloring, saved favorites, an eyedropper, and reference-color sampling. |
| Reusable pieces | Save selections or groups to an independent **Assets** library and insert them into other projects. |
| Working history | Undo/redo, visible history, named projects, Save As, and automatic recovery checkpoints. |
| Finishing | Export Check highlights problems before producing the flat JSON used by KFPS's transfer tools. |

### Projects, Assets, and Export JSON

**Share the project if you want to preserve editor groups.** A project keeps your editable organization, reference image, and other working information. An exported JSON is a flat shape list for game transfer; it cannot carry editor groups. Adding grouped structures to an export makes it incompatible with KFPS's flat import mechanism.

Assets are stored separately from projects, generated outputs, and exported JSONs. Removing an exported file does not remove a saved asset. Shape and color favorites also survive editor restarts.

![Mini Kloudy saved in the editor's reusable Assets library](docs/screenshots/showcase/editor-assets.png)

### Saving and Recovery

The editor makes frequent background recovery checkpoints and can resume the last successfully stored session after closing or a crash. Previous completed recovery data provides a fallback if a newer write fails.

**Recovery is a safety net, not a replacement for Save or backups.** The newest edits can still be lost if the editor crashes before their checkpoint finishes, storage is unavailable, or you replace the session. Save a named project before sharing, updating, or moving your work.

Reference images no longer have a 16-megapixel cap. The project allows **100 MiB of encoded embedded-reference data** and **150 MiB total**. Because embedding adds size, a normal PNG or JPEG reference can be **just under 75 MiB, about 79 MB as a source file**, not 100 MB. Large images can still use substantial memory and take longer to load or save.

**English and Korean** are available through the editor's lower-left language menu. This switch localizes the editor, not every page of the main app.

## Outputs and Game Transfer

![KFPS Outputs showing the generated Mini Kloudy checkpoint files and live transfer controls](docs/screenshots/showcase/outputs.png)

Outputs brings **Generated finals**, **Editor exports**, **Game exports**, and the **Library** into one file browser. Search, preview, organize, and choose a JSON before transferring it. The game-save vinyl library is a supporter feature; community downloads have their own access rules.

**Online/live** means reading or editing the memory of a game running on your PC. It does **not** mean uploading your design to the internet. **Offline** means processing supported local save files.

### Supported Transfer Paths

| Game | Live import | Live export | Offline vinyl import | Offline vinyl export |
| --- | --- | --- | --- | --- |
| Forza Horizon 4 | Yes | Yes | Microsoft Store/Xbox WGS | Yes |
| Forza Horizon 5 | Yes | Yes | **Not available** | **Yes** |
| Forza Horizon 6 | Yes | Yes | Yes | Yes |
| Forza Motorsport (FM8) | Yes | Yes | Yes | Yes |

Live transfers are free. Offline **vinyl-group** library tools require a [supporter key](#support-kfps). Support depends on the game's build and save format; this table is not a promise for every store version or future game update. FH4's live support is build-specific, and its offline import requires the game to be closed and uses the Microsoft Store/Xbox WGS save path.

### Enter the Right Layer Count

The **Template layers** field serves both live actions, but the number you enter depends on what is open in-game:

| Action | Count to enter | Example |
| --- | --- | --- |
| **Live import** | Actual layers in the open placeholder template | Import a 1,842-shape JSON into the standard 3,000-circle template: enter **3000**. |
| **Live export** | Actual shape layers in the open artwork | Export a vinyl containing 1,842 layers: enter **1842**, not 3000. |

Count the shapes inside groups, not the group headers. Keep **only one supported game** running, open the intended vinyl group, and do not change game screens during a transfer. Leave **Clear Extra Template Layers** enabled for normal imports. A design cannot fit into fewer template slots than it needs.

Offline tools avoid the live template workflow. Close the game before offline vinyl-group writes, follow the tool's save checks, and keep backups. A save folder is not the game's installed `media` or `Content` folder.

## Full-Car Liveries

![KFPS Liveries showing the approved KFPS car design using its actual game thumbnail](docs/screenshots/showcase/liveries.png)

The public **Liveries** page is a separate, **experimental FH6 full-car workflow**, not the individual vinyl-group library.

- **Recognize the design before opening it:** browse actual game thumbnails in the livery grid.
- **Export without rendering first:** **Export Selected** creates the package without launching the 3D preview.
- **Inspect when useful:** **Open 3D Preview** uses the matching car from your own FH6 installation. Previewing is optional.
- **Share a complete package:** `.kfpslivery` retains the original FH6 livery record for installation onto the **same exact FH6 car**.

**A missing preview detail is not automatically missing export data.** This path preserves the original game livery record rather than rebuilding it from what the renderer happens to show. Details omitted or misdisplayed by the 3D preview are not discarded from that preserved record.

![The approved KFPS livery on its matching FH6 car in the optional experimental 3D preview](docs/screenshots/showcase/livery-preview.png)

*The KFPS livery in the optional 3D viewer. This particular saved example is marked preview-only by the app's ownership checks; showing a preview does not make a livery eligible for export.*

Ownership checks still apply: another player's livery cannot be exported, and an owned livery containing someone else's vinyls is preview-only until those are removed in-game. Different-car and cross-game full-livery installation are not supported. The FH6 livery installer creates a new entry with save-change checks and recovery data; unlike FH4 offline vinyl import, it can allow FH6 to remain open, with a save reload needed afterward.

## Community

Browse artwork, search by tags or creator, inspect previews, and find handmade or toolmade vinyls from other users. Public browsing does not need an account.

Connect a GitHub identity to download, favorite, follow creators, report listings, or publish your own work. Publishing renders a preview from the selected JSON and lets you provide a title, description, tags, and revisions. Your Community username is permanent, so check it before confirming.

Supporters can also connect their entitlement to use the supporter catalog. Share only work you created or have permission to distribute. A listing in KFPS is not a guarantee that the artwork complies with a game's rules.

## Image Tools

![KFPS Image Tools with local background-removal and upscaling options](docs/screenshots/showcase/tools.png)

Prepare the source before spending time generating it. KFPS includes **local background removal and upscaling**, plus source checks to help identify unsuitable images. Models may need downloading on first use; these local operations do not upload your artwork.

The separate resize/compress shortcut opens **Squoosh** in a browser. Keep your original image and inspect fine edges after preparation: removal can erase pale details, and upscaling cannot recreate information that was never present.

## Themes

The main app has **eight themes: four public and four supporter themes**. They change more than an accent color, from the default Night Blossom workspace to retro desktop and console-inspired layouts. Choose them in Settings; motion and visual-effect preferences are also available.

### Public Themes

| Night Blossom | Command Prompt |
| --- | --- |
| ![Night Blossom theme](docs/screenshots/showcase/create.png) | ![Command Prompt theme](docs/screenshots/showcase/theme-command-prompt.png) |
| **Apex Vector** | **Night City 2077** |
| ![Apex Vector theme](docs/screenshots/showcase/theme-apex-vector.png) | ![Night City 2077 theme](docs/screenshots/showcase/theme-night-city.png) |

### Supporter Themes

| Windows 94 | Patron's Atelier |
| --- | --- |
| ![Windows 94 theme](docs/screenshots/showcase/theme-windows94.png) | ![Patron's Atelier theme](docs/screenshots/showcase/theme-atelier.png) |
| **Carbon Dark** | **Overdrive 200X** |
| ![Carbon Dark theme](docs/screenshots/showcase/theme-carbon.png) | ![Overdrive 200X theme](docs/screenshots/showcase/theme-overdrive.png) |

### Editor Themes

The editor has its own **Signature Pink, Dark, Blackout, and Whiteout** themes, plus adjustable colors for a custom look. These editor themes do not require a supporter key.

| Whiteout | Blackout |
| --- | --- |
| ![Editor Whiteout theme](docs/screenshots/showcase/editor-whiteout.png) | ![Editor Blackout theme](docs/screenshots/showcase/editor-blackout.png) |

## Support KFPS

**[Get a supporter key on Ko-fi](https://ko-fi.com/s/2d1507698d)** to support development and unlock:

- **Offline vinyl libraries:** export supported FH4, FH5, FH6, and FM8 libraries, and import compatible JSON into supported FH4, FH6, or FM8 saves without starting the game. **FH5 offline import is not included because it is not available.**
- **Four extra main-app themes:** Windows 94, Patron's Atelier, Carbon Dark, and Overdrive 200X.
- **Supporter Community access:** browse, download, and share supporter-only vinyls with a connected Community profile.

**One-time purchase, not a subscription.** Add your key in KFPS Settings after purchase. Generation, the standalone editor, output management, public Community browsing, and live import/export remain available without a key. The experimental full-car Liveries page is also public.

![KFPS Support page explaining the one-time purchase, its benefits, and the features that stay free](docs/screenshots/showcase/support.png)

## Help and Updates

Use the app's **Help** page for searchable steps covering templates, exact counts, projects, recovery, transfers, and troubleshooting. This README is the overview; Help is where the task-specific instructions live.

**Report a Problem** opens a KFPS review window with troubleshooting information and retained logs loaded automatically. Discord sign-in opens in your Windows default browser so an existing login can be reused. Nothing is sent until you press **Send report**. The issue description, Discord display name, version, report ID, and screenshots you explicitly attach are public in the [KFPS Support Discord](https://discord.gg/XT8dG8bDKy); additional technical details and logs you choose to include are private to Kloudy and authorized support staff. Any logs excluded by size or access limits are clearly identified.

For a useful report, include the version, exact steps, expected result, actual result, and relevant hardware. For transfer issues, include the game, live/offline route, actual layer count, and the JSON with its report/manifest when available. Never share keys, credentials, or private saves publicly.

**Updating:** save projects and close the editor and active generation first, then use KFPS's **Update** page. If the main app cannot start, use the updater beside it. Keep the bundle together and back up personal work before repairing an installation. See [updater recovery and diagnostics](docs/BOOTSTRAP_UPDATER.md) for technical details.

KFPS is an unofficial Forza tool. Game updates can change memory layouts and save formats, rendering remains an approximation, and no recovery system can guarantee against every crash or disk failure. Keep backups and use the tools responsibly.

## Credits and Licenses

KFPS builds on the work of [Forza Painter](https://github.com/forza-painter/forza-painter), [BVZRays' FH6 work](https://github.com/bvzrays/forza-painter-fh6), [GPU Geometrize](https://github.com/zjl88858/forza-painter-geometrize-gpu), [Sam Twidale](https://samcodes.co.uk/), [Michael Fogleman's primitive](https://github.com/fogleman/primitive), and [Fabric.js](https://fabricjs.com/).

Special thanks to [Arstz / ForzaLiveryStudio](https://github.com/Arstz/ForzaLiveryStudio) and its contributors for public save-format research and documentation that helped clarify the offline workflow. Thanks also to the source-tool authors, localization contributors, testers, artists, and community members credited in the app's **Credits** page.

License notices: [KFPS / Forza Painter](LICENSE), [GPU generator](LICENSE.geometrize-gpu), [custom import tools](LICENSE.custom-importer), and [Fabric.js](LICENSE.fabricjs). Image-tool dependencies retain their notices in their respective tool folders. Mini Kloudy and the KFPS livery are shown with their creator's permission; code licenses do not grant separate rights to that artwork.
