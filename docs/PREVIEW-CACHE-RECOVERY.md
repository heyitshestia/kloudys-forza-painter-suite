# Preview cache recovery

3.2.2 isolates damaged, inaccessible or untracked per-car viewer caches. A bad
entry no longer prevents admission of every other Garage or Community preview.
Both package/livery previews and stock/fitted Garage previews use this path.

The selected car reuses its existing verified cache. If verification fails, it
uses a deterministic replacement entry and rebuilds from the installed car and
original livery source. Reopening reuses that replacement. Existing artwork,
projects, game saves and unknown files are never adopted, altered or deleted.
No filesystem permissions are changed.

Ownership markers, ordinary-file checks, link/junction rejection, immutable
descriptor hashes, per-entry viewer locks and installation-wide producer leases
remain enforced. An invalid installation root or cache-root redirect still stops
the operation rather than trusting another location.

Recovery is limited to five candidate entries per car and 64 entries across
current/legacy cache roots. The existing 2 GiB budget applies to verified active
entries; preserved unusable content is outside that budget and is reported
separately, not silently claimed as removed. Disk-free admission leaves 64 MiB
of headroom above the producer reservation. Persistently broken storage may still
require manual attention, with an explicit recovery-limit or disk-space error.

Clear Cache removes only verified generated files and leaves inaccessible,
modified or unknown entries alone. Its summary reports preserved entries; preview
logs record the preserved count and verified cache size without source paths.
An access failure is no longer mislabeled as a hard link.

The usual inventory check probes file access without loading full meshes. A
later cache I/O error marks that entry for replacement on retry. Missing or
locked external game/package files do not consume recovery slots; filename-less
stream errors get a bounded cache-read check before an entry is marked.

Regression coverage includes inaccessible selected/unrelated cars, current and
legacy roots, stable replacement reuse, interrupted generation, changed metadata,
unknown files, hard links, Windows junctions, active viewer locks, disk and entry
limits, logging and clear-cache reporting. Real-data qualification also checks
the preparation/server/browser path, not only the cache helper.
