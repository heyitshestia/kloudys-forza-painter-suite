# Garage

Garage brings the installed FH6 car catalogue, owned copies, saved liveries and
local packages together. It reads local information; browsing Garage does not
change your game saves.

## First Visit

Open **Garage > My Cars**. KFPS loads stock catalogue thumbnails from the selected
FH6 installation and discovers local accounts in the background. Choose your
account explicitly the first time. That choice is remembered; the dropdown
switches accounts later. A reliable local gamertag is shown when available.

You can browse stock cars without an account. Saved Liveries, Packages and the
normal transfer tools remain independent of account selection. **Choose File**
is the manual fallback. **Rescan FH6 accounts** updates the account choices;
Garage **Refresh** also revalidates catalogue inputs.

If a newly added car is missing, check that KFPS is linked to the updated FH6
installation, then refresh. Different installed copies can contain different
cars. KFPS does not combine assets from those installations.

## Finding Cars And Artwork

- **All cars** includes the installed catalogue, with owned copies kept separate.
- **Is owned** limits the view to the selected account's owned copies.
- **Has livery** means a saved livery in that account's scanned library or a local
  package exists for the model. Without a selected account, scanned local save
  libraries can contribute. This is not an authorship claim or an export permission.
- **Duplicate models** helps find multiple owned copies.

Manufacturer, ownership-priority and livery-priority sorting are remembered.
Stock thumbnails are distinct from saved-livery previews; missing stock artwork
uses a placeholder rather than an unrelated design.

## Opening A Build

**Open 3D Preview** and **Open in Studio** use the selected owned copy's current
body configuration. A catalogue-only car opens with stock defaults. These actions
open the body without artwork.

For an owned copy, choose compatible local artwork and use **Open Artwork in
Studio** to combine it with the current body. **Show Applied Livery** requires an
exact local reference match. An older livery does not prove which parts were
fitted when it was originally saved.

Represented groups are body kit, chassis/cage, front bumper, hood, rear bumper,
rear wing and side skirts. Wheels and tyres are not fitted by this workflow.
Names come from installed catalogue data where available. Unknown or conflicting
choices stop with an error instead of silently substituting stock.

Native Studio supports guarded car switching. A separately opened Chrome Studio
keeps its existing car-selection restrictions; select the matching car there
before importing when prompted. Existing unsaved-work confirmation applies.

## Comparisons And Linked Projects

**Compare From Here** compares saved part IDs. **Save Comparison** keeps a named
local note. Link a same-car Studio project, then check it, reveal its folder, or
use **Open Linked Project**. Managed links follow valid saved revisions.

Opening a linked project is detached from the original file and retains its
complete authoring data. Saving is still explicit. Removing a comparison does
not delete the linked project. Automatic history is unavailable for current
native snapshots; use named comparisons instead.

## Studio Controls

The inspector has Placement, Design, Car, View and Project tabs. Right-click a
vinyl source to delete it from the current project; confirmation, locked-layer
checks and Undo apply. Original files are not deleted. Surface inspection's
**Highlight section** follows the close-up section without moving the camera.

KFPS stops its managed Studio backend when the workspace closes normally. A
standalone Studio window or Chrome-connected session can keep its own backend
alive. Close those windows before updating.

## Caches And Limits

Garage work starts on entry or refresh. Cached records, installed part names and
stock thumbnails are reused when valid. Validation still reads source data to
detect changes; it is not a promise of zero disk activity. No continuous Garage
scan or bulk thumbnail rendering runs while idle.

Supported vector packages can be edited, but previewability is not editability.
Raster decals and some unsupported authorship metadata remain restricted. Full
design export is experimental, wheel rendering is incomplete, and not every
car/body-kit combination has been checked in game. Original artwork and game
saves are not rewritten to work around those restrictions.
