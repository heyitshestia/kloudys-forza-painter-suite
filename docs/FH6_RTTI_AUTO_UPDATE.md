# FH6 Shared Locator Profile Workflow

KFPS reads the canonical profile registry from an isolated Cloudflare relay.
The checked-in GitHub `RTTI.dat`, the last-good runtime cache, the packaged
registry, the built-in profile, and the slower live-search paths remain ordered
fallbacks. A relay or network outage does not remove an already known locator.

Trusted calibrator helpers enroll automatically from a bounded reusable campaign
file in the prepared helper folder. Each Windows installation receives its own
random, revocable credential protected for that Windows account with DPAPI.
Helpers do not need prior approval, GitHub, GitHub CLI, or a repository account.

## Purpose

FH6 game updates can move the MSVC RTTI descriptor and vtable used to locate the editable `CLiveryGroup`. KFPS previously kept one calibrated profile directly in `fh6_probe.py`, so every game update required an application commit before users regained the fast locator.

The shared profile workflow separates that volatile data from the application release cycle:

1. A trusted helper runs the read-only six-step calibrator.
2. The calibrator accepts a result only when one locator identity persists across all six fixed layer counts.
3. It converts full local evidence into a minimal, module-relative profile.
4. The helper's enrolled calibrator submits that profile to the isolated Cloudflare relay.
5. KFPS refreshes and caches `RTTI.dat` before a live FH6 locator run.
6. KFPS verifies the profile against the running game before using it.

No KFPS version bump or release bundle is required for a data-only profile update.

## Trust Model

The calibrator contains no GitHub token, OAuth secret, signing key, administrator
secret, or Cloudflare account credential. The owner creates an expiring
auto-enrollment campaign with a fixed device limit and saves its reusable
`rtti-enrollment.json` in the clean BASE package. A new PC presents that campaign
code once; the relay creates an individual helper identity and returns a unique
credential exactly once. The credential is stored with Windows DPAPI under the
helper's Windows account, outside the portable calibrator folder.

The campaign file is a bounded invitation: anyone who obtains it can consume an
available device slot until it expires, is revoked, or its code is rotated. The
owner sends it only to intended helpers. Every enrolled PC can be renamed,
revoked, or restored independently. Campaign revocation and rotation stop new
registrations but do not silently disable already enrolled PCs. Resetting one
helper invalidates that PC's old credential and issues a targeted one-time file.
Accepted and rejected profile submissions are audited by helper name, while the
public registry contains no helper identity.

Runtime trust has three layers:

- `RTTI.dat` is fetched only over HTTPS from the Cloudflare relay, with raw GitHub as a read-only fallback.
- The parser rejects malformed, oversized, absolute/out-of-module, non-ASCII, or unsupported data.
- `fh6_probe.py` reads the candidate descriptor in the live FH6 module and requires its update code to match before accepting the vtables. Existing group/table/layer validation still runs afterward.

Compromise or corruption therefore falls back rather than bypassing locator validation.

## Privacy Boundary

Full calibration evidence is local-only. It can include:

- process ID;
- executable and package paths;
- randomized module and heap addresses;
- candidate group/table/layer addresses;
- diagnostic samples.

The publisher extracts only:

- main-module size;
- module-relative descriptor offset;
- module-relative vtable offsets;
- bounded RTTI update code;
- base-class count;
- optional game package version;
- calibrator version and aggregate scan evidence.

The output profile contains no username, machine identifier, file path, PID, absolute memory address, artwork, or layer contents.

## Registry Format

`RTTI.dat` is UTF-8 JSON using `kfps_fh6_rtti_registry_v1`:

```json
{
  "format": "kfps_fh6_rtti_registry_v1",
  "updated_utc": "2026-07-15T00:00:00Z",
  "profiles": [
    {
      "game": "fh6",
      "module_size": 187719680,
      "descriptor_offset": 165857600,
      "vtable_offsets": [109116416],
      "update_code": "91173565759607",
      "base_class_count": 4,
      "game_build": "3.382.893.0",
      "created_utc": "2026-07-06T16:17:49Z",
      "calibrator_version": "2.0.0",
      "evidence": {
        "workflow": "six_step_template_calibration",
        "confidence": "high",
        "scan_count": 6,
        "distinct_counts": [3000, 2997, 2994, 2991, 2988, 2985]
      },
      "profile_id": "fh6-..."
    }
  ]
}
```

`profile_id` is recomputed from the identity fields and never trusted from downloaded input. New profiles are inserted first; previous game-build profiles remain available. Exact duplicates are replaced, and the registry is capped at 64 profiles and 128 KiB.

## Publication Gate

The calibrator publishes only when:

- the workflow is exactly `six_step_template_calibration`;
- scans completed at `3000, 2997, 2994, 2991, 2988, 2985` layers;
- one locator identity is stable across all counts;
- confidence is `high` or `very_high`;
- descriptor and vtable offsets are inside the recorded module;
- the sanitized profile passes the same parser used by KFPS.

The Worker validates and recomputes the profile identity, then uses D1 upserts
so concurrent submissions cannot overwrite unrelated profiles. It stores only
the normalized privacy-safe profile, never the original calibration evidence.

## Runtime Refresh

`fh6_rtti_registry.py` obtains and reads profiles in this order:

1. Cloudflare relay, saved atomically to `runtime/fh6-rtti/RTTI.dat`;
2. raw GitHub `RTTI.dat` if the relay request fails;
3. the previous last-good runtime cache if every network request fails;
4. packaged repository-root `RTTI.dat`;
5. the built-in profile retained in `fh6_probe.py`.

The remote check is throttled to once every 15 minutes after success and once per minute after failure. Writes are atomic. A failed or invalid download does not replace the last valid cache. Set `KFPS_DISABLE_RTTI_UPDATE=1` to disable network refresh or `KFPS_FORCE_RTTI_UPDATE=1` for one forced check.

Every candidate is verified against live process memory. If no shared profile matches, KFPS continues through `update-codes.dat`, class-name RTTI scanning, and the slower layout/count fallback.

## Trusted Helper Setup

Normal distribution requires no per-PC console action:

1. Keep the prepared `KFPS FH6 RTTI Cloudflare Calibrator BASE` folder clean.
2. In `KFPS Operations Console` -> `FH6 RTTI` -> `Auto Enrollment`, confirm its
   reusable campaign is active and has an available device slot.
3. Copy the complete BASE folder for the helper. Do not include an existing
   `calibration-results` directory.
4. The helper opens the batch file and follows the six fixed layer counts. The
   first run silently registers that PC. No GitHub installation, login, browser
   authorization, token entry, or owner approval is required.
5. Refresh the console and rename the new `Auto helper ...` row if desired.

Use the console to revoke one helper immediately if that PC should stop
publishing. Revoke the campaign to stop all new registrations from existing
copies. `Rotate and Save` invalidates the old campaign file and writes a
replacement into BASE. Already registered PCs remain controlled by their own
rows.

`One-Time Enrollment` is the targeted fallback. Use it when recovering a known
helper after a Windows reset or lost DPAPI state. It expires after seven days,
works once, and invalidates the helper's previous credential when issued through
`Reset Enrollment`.

The maintained source, launcher, build script, and operator guide live in `tools/fh6_rtti_calibrator`. Its `fh6_rtti_registry.py` must remain byte-identical to the repository-root runtime module; the automated tests enforce this contract.

## Validation

The focused suite is:

```powershell
python KFPS.UI\tests\test_rtti_registry.py
python KFPS.UI\tests\test_rtti_relay_client.py
cd tools\fh6_rtti_relay_worker
npm test
npm run typecheck
```

Coverage includes format bounds, profile sanitization, six-scan enforcement,
DPAPI-backed automatic and one-time enrollment, campaign capacity/race handling,
code rotation, helper revocation/reset behavior, cache preservation,
Cloudflare-to-GitHub fallback, refresh throttling, D1 merge behavior, and live
type-code verification with mocked process memory.
