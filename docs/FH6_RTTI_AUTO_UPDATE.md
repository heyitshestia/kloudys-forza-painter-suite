# FH6 Shared Locator Profile Workflow

## Purpose

FH6 game updates can move the MSVC RTTI descriptor and vtable used to locate the editable `CLiveryGroup`. KFPS previously kept one calibrated profile directly in `fh6_probe.py`, so every game update required an application commit before users regained the fast locator.

The shared profile workflow separates that volatile data from the application release cycle:

1. A trusted helper runs the read-only six-step calibrator.
2. The calibrator accepts a result only when one locator identity persists across all six fixed layer counts.
3. It converts full local evidence into a minimal, module-relative profile.
4. The helper's authenticated GitHub account merges that profile into `RTTI.dat`.
5. KFPS refreshes and caches `RTTI.dat` before a live FH6 locator run.
6. KFPS verifies the profile against the running game before using it.

No KFPS version bump or release bundle is required for a data-only profile update.

## Trust Model

The calibrator contains no GitHub token, OAuth secret, signing key, or shared credential. Publication calls the installed GitHub CLI, which uses the operator's own credential store. The operator must be an explicitly trusted repository collaborator.

This is intentionally different from sharing a token for one Gist. A shared Gist credential would let every recipient impersonate the owner and edit all Gists covered by that token. Repository commits provide contributor identity, history, rollback, and normal GitHub access control.

Runtime trust has three layers:

- `RTTI.dat` is fetched only over HTTPS from the configured KFPS repository URL.
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

GitHub's Contents API uses the current blob SHA. If another helper updates `RTTI.dat` concurrently, the publisher refetches, merges, and retries once instead of overwriting the other profile.

## Runtime Refresh

`fh6_rtti_registry.py` reads profiles in this order:

1. last valid remote cache at `runtime/fh6-rtti/RTTI.dat`;
2. packaged repository-root `RTTI.dat`;
3. the built-in profile retained in `fh6_probe.py`.

The remote check is throttled to once every 15 minutes after success and once per minute after failure. Writes are atomic. A failed or invalid download does not replace the last valid cache. Set `KFPS_DISABLE_RTTI_UPDATE=1` to disable network refresh or `KFPS_FORCE_RTTI_UPDATE=1` for one forced check.

Every candidate is verified against live process memory. If no shared profile matches, KFPS continues through `update-codes.dat`, class-name RTTI scanning, and the slower layout/count fallback.

## Trusted Helper Setup

1. Add the helper's GitHub account as a repository collaborator with write access.
2. Have the helper install GitHub CLI:

   ```powershell
   winget install --id GitHub.cli
   ```

3. Have the helper authenticate their own account:

   ```powershell
   gh auth login --hostname github.com --web --git-protocol https
   gh auth status --hostname github.com
   ```

4. Send the standalone calibrator folder. Do not send tokens or any existing `calibration-results` directory.

The maintained source, launcher, build script, and operator guide live in `tools/fh6_rtti_calibrator`. Its `fh6_rtti_registry.py` must remain byte-identical to the repository-root runtime module; the automated tests enforce this contract.

## Validation

The focused suite is:

```powershell
python -m unittest discover -s KFPS.UI\tests -p "test_rtti_registry.py" -v
```

Coverage includes format bounds, profile sanitization, six-scan enforcement, cache preservation, offline fallback, refresh throttling, credential-free GitHub requests, concurrent-update retry, and live type-code verification with mocked process memory.
