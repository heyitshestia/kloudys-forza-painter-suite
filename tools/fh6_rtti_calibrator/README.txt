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
GitHub, GitHub CLI, and a GitHub account are not required. The standard helper
folder already contains a reusable, expiring rtti-enrollment.json campaign file.
The administrator can copy that prepared folder for each trusted helper without
creating or approving that computer first.

On the first normal run on a new PC, the calibrator silently registers that
Windows account with the isolated KFPS Cloudflare relay. The returned per-device
credential is protected by Windows DPAPI outside this portable folder. The
reusable campaign file remains so clean copies can register other trusted PCs;
it is never used again on a PC that already has a working credential.

Each registered PC appears separately in the KFPS Operations Console and can be
renamed or revoked immediately. The administrator can revoke or rotate the whole
campaign to prevent the folder from registering more PCs. Existing registered
PCs remain individually controlled. A seven-day one-time enrollment file is
used only when the administrator deliberately resets or recovers one helper.

After enrollment, publication is automatic. If one stable high-confidence
profile is independently rediscovered at all six counts, the relay validates,
normalizes, audits, and merges it into the shared RTTI.dat registry. The relay
stores no process paths, PIDs, absolute addresses, or diagnostic samples.

If enrollment or the network is unavailable, calibration still saves all local
files. After the administrator restores access or supplies a reset file, publish
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
  Validate the publication payload without changing the Cloudflare relay.

--publish-result PATH
  Validate and publish an already completed six-step result.

TROUBLESHOOTING
---------------
Exit code 0: calibration and requested publication completed.
Exit code 1: scans were incomplete, ambiguous, or not high confidence.
Exit code 2: calibration succeeded locally but publication needs attention.

If a run is ambiguous, keep the complete calibration-results folder for
private analysis. Do not manually edit offsets into RTTI.dat.
