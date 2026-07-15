KFPS FH6 6-Step Shared Locator Calibrator
=========================================

PURPOSE
-------
This read-only Windows tool rediscovers the FH6 live-import locator after a
game update. It never writes to the game. When all six scans agree, it creates
a privacy-safe RTTI.dat profile and can publish that one file to KFPS so every
user receives the new locator automatically.

The detailed calibration evidence stays on the computer that ran the tool.
It is never uploaded by the calibrator because it contains process paths,
temporary addresses, and diagnostic samples.

REQUIRED GAME SETUP
-------------------
1. Open Forza Horizon 6.
2. Open a flat, ungrouped 3000-layer plain-circle template in the vinyl editor.
3. Keep FH6 on that editor screen.
4. Run Run_KFPS_FH6_6-Step_Locator_Calibrator.bat.
5. Follow the fixed sequence exactly:

   3000 -> 2997 -> 2994 -> 2991 -> 2988 -> 2985

The tool asks you to delete three layers between scans. Do not group layers,
load another vinyl, or leave the editor while it is scanning.

AUTOMATIC PUBLICATION FOR TRUSTED HELPERS
-----------------------------------------
Publication never uses an embedded or shared token. Each helper publishes
through their own GitHub account, so every RTTI.dat update has an audit trail.

The repository owner must first add the helper as a collaborator with write
access to:

  https://github.com/heyitshestia/kloudys-forza-painter-suite

One-time setup on the helper's computer:

  winget install --id GitHub.cli
  gh auth login --hostname github.com --web --git-protocol https
  gh auth status --hostname github.com

Never send anyone a GitHub token and never place a token in this folder.

After setup, normal calibration is automatic. If one stable high-confidence
profile is seen at all six counts, the tool merges it into the shared RTTI.dat
registry and creates one GitHub commit. Existing game-build profiles remain in
the registry. Concurrent updates are refetched and retried once.

If GitHub CLI is unavailable, authentication expired, or repository access is
missing, calibration still saves its local files. After fixing access, publish
the completed result with:

  KFPS_FH6_Locator_Calibrator.exe --publish-result "path\clivery-rtti-latest.json"

Or use the Python script with the same arguments.

OUTPUT FILES
------------
Each run creates a timestamped folder under calibration-results:

- RTTI.dat
  The only privacy-safe publication payload. Contains module-relative offsets,
  type code, build metadata, and scan counts. No paths or absolute addresses.

- clivery-rtti-latest.json
  Full local diagnostic evidence. Do not publish this file publicly.

- clivery-rtti-offsets.txt
  Human-readable local diagnostics.

- update-codes.dat
  Legacy single-code compatibility output.

PUBLICATION SAFETY GATES
------------------------
The tool refuses automatic publication unless all conditions pass:

- all six fixed layer counts were scanned;
- the same locator identity appeared across all six counts;
- exactly one publishable identity remains;
- descriptor and vtable offsets are inside the FH6 main module;
- the update code is bounded printable ASCII;
- confidence is high or very high;
- RTTI.dat passes the shared registry parser before upload.

KFPS then independently verifies the downloaded type code in live FH6 memory
before using its offsets. Invalid, stale, malformed, oversized, unavailable,
or non-HTTPS updates are ignored. KFPS retains its last good cache, packaged
profile, built-in profile, and slower pattern/layout fallbacks.

USEFUL OPTIONS
--------------
--no-publish
  Run all calibration checks and save RTTI.dat locally only.

--dry-run-publish
  Validate the publication payload without changing GitHub.

--publish-result PATH
  Validate and publish an already completed six-step result.

TROUBLESHOOTING
---------------
Exit code 0: calibration and requested publication completed.
Exit code 1: scans were incomplete, ambiguous, or not high confidence.
Exit code 2: calibration succeeded locally but publication needs attention.

If a run is ambiguous, keep the complete calibration-results folder for
private analysis. Do not manually edit offsets into RTTI.dat.
