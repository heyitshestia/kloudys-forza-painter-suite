# Livery Thumbnail Grid

The native Liveries page opens on a searchable thumbnail grid. A single click
selects a local FH6 livery without rendering it. Open 3D Preview, double-click,
or Enter explicitly starts the existing preview path. Back to Liveries releases
the viewer and preserves the selected source. Returning from another page opens
the grid rather than restarting an old preview.

The library has separate **In-game saves** and **Packages** tabs. Both have
independent search, exact-car filters and sorting. In-game saves also support
**All / Exportable / Preview only** availability and newest-first sorting.
Packages sort by title, car ID or placement count. Clearing filters leaves the
chosen sort intact. Arrow keys, Home and End select without starting a preview.

Package selection reads cached title, car, placement count, creation time and
declared mesh metadata only. It neither decodes the package nor enables install.
Open 3D Preview, double-click or Enter invokes the existing isolated verification
and preview workflow. Removed or missing packages lose their selection safely.
Back retains the library tab and filters. A failed preview shows its error with
an explicit **Retry Preview** action; retry does not alter save data.

For a selected package, **Open in Studio** appears directly below **Open 3D
Preview** in the details panel. It opens the package's editable artwork on its
exact car through the existing native or Chrome Studio setting. All sections,
nested groups, masks and transforms are retained; the original package is not
modified. Studio asks before replacing unsaved work. Save the imported artwork
as a Studio project to retain further edits. Body paint and materials are not
imported by this action. Unsupported packages report an error rather than being
flattened or silently placed on another car. In-game saves do not show this action.
In Chrome, save your work and select the package's car in Studio first. Package
opening does not automatically switch a shared Chrome backend to another car,
which could interrupt another window's unsaved work. Native Studio retains its
guarded automatic car switch.

Selection details show the exact car ID, placement count, modification time,
header availability and export restrictions. Wide windows keep these beside the
gallery; compact windows expose them through **Details**, with a separate
**Preview** shortcut. Folder selection,
cache cleanup, package-folder access and diagnostics are under **More**.

After preview preparation, the details also show actual paint/mask atlas sizes,
mesh-cache reuse, geometry/UV coverage, material omissions and section counts.
Unknown values remain unknown. UV copy integrity does not establish in-game
mapping equivalence, and unsupported material/mapping counts do not prove a
visible body part is missing. Compatibility details are expandable. Existing
exact-car installation checks and confirmation remain in place.

The blocking work-in-progress popup is replaced with a small Experimental label.
The renderer, vinyl coordinates, save format and export policy are unchanged.

Export Selected creates and verifies the package, then refreshes Saved packages.
It does not open a 3D preview or change the selected source. Opening a preview
remains an explicit action.

## Data And Resource Boundaries

- Each image comes only from that exact C_livery container's bigThumb.webp or
  BigThumb.webp. There is no same-car image guessing or separate cache crawl.
- Existing scan ownership, visibility and export policies remain authoritative.
  Preview-only records are still marked and cannot be exported from the grid.
- Browsing thumbnails requires the save records, not the FH6 game assets. A
  linked installation is still required for a 3D preview.
- Missing, empty, corrupt or over-4-MiB thumbnails show a placeholder. They do not
  trigger rendering, conversion or game writes.
- Images load asynchronously at a bounded 670 x 376 requested size. GridView
  reuses delegates; pooled delegates clear their image source. Qt's global image
  cache is disabled for these images.
- Thumbnail revision URLs use file modification time and length. Rescanning or
  reopening the catalog refreshes the image independently of C_livery changes.
- Search is literal and case-insensitive across title, model code, car ID and path.
  It filters a proxy model without changing source paths or the durable catalog.
- Exported package contents, the save parser, renderer and installer are unchanged.
- Preview and Studio reuse verified prepared-car data on disk when their inputs
  and dependencies still match. Returning to an inactive car in the same Studio
  session can reuse its owned folder within the existing three-folder limit.
  Changed or missing prepared-car artifacts go through preparation again;
  redirected paths are rejected. A corrupt immutable saved-atlas cache must be
  cleared through the existing cache action before reopening.
- Preview can also reuse verified saved paint/mask atlases. First-time preparation
  still takes time. These changes do not raise the inactive canvas budget or
  keep additional models or textures resident, and do not lower preview quality.

## Reference And Provenance

FH6 Assistant v1.4 Source was inspected read-only: scanner.py's _detect_thumbnail,
the thumbnail cards in ui.py, and thumbnail_cache.py. Its original-thumbnail
association was used as a behavioral reference. No explicit license was found;
no reference-project source, assets or dependencies were copied into KFPS.

The 2026-10-29 library refinement also uses the Assistant v1.6 static review as
an organizational reference for explicit preview evidence. The implementation
reads KFPS's own prepared component/UV/material diagnostics. No recovered code
was transplanted. Tune-based configuration, replacement rendering and automatic
part selection are not part of this library change.

## Verification

Run from the KFPS root:

```powershell
py -3.12 -m unittest discover -s KFPS.UI/tests -p '*livery*.py'
py -3.12 KFPS.UI/tools/test_livery_grid_workflow.py --output <validation-directory>
py -3.12 KFPS.UI/tools/test_livery_grid_workflow.py --output <scaled-directory> --theme "Command Prompt" --scale 1.5
```

The native workflow uses isolated settings and temporary fixture records. An
optional --thumbnail-root <ContainersRoot> samples up to 12 original thumbnails
read-only into disposable fixtures. It checks actual Qt image pixels, selection,
search, independent package filters, explicit preview handoff, failure retry,
navigation, missing/broken images, four window sizes, and virtualized scrolling
with 5,000 source rows and 5,000 package rows. Scan/package workers and
3D work are mocked in this focused UI test; the existing livery suite exercises
their contracts. This is not a new end-to-end game import/export qualification.
The package action is checked in both wide and compact details, including pending
state, retry and visible failure feedback after the compact popup closes.

The connected-workspace integration is described in [WORKSPACE.md](WORKSPACE.md).
Keep validation output in an isolated run directory, separate from user saves.
