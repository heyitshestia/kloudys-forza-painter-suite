# KFPS Startup / Update Collector

Send `Collect_KFPS_Diagnostics.bat` on its own. The recipient places it beside
`KFPS.exe` and double-clicks it; both outer and inner release layouts work.
It needs only Windows PowerShell 5.1, not Python, admin access or a working KFPS.

The ZIP is created beside the BAT, or in `%TEMP%\KFPS-Diagnostics` when that is
not possible. It is reopened and all entries are hash-verified. No update,
application launch or upload occurs. Recent allowlisted logs/reports, version,
Windows build and executable locations/hashes are included. Common secrets are
redacted, but paths/filenames may still be personal: send the ZIP privately.

Artwork, saves, settings, credentials files, caches and rollback backups are
excluded. Collection is bounded to 2 MiB per file / 16 MiB source text total.
Current installation evidence takes priority over other updater copies. Missing,
locked or linked logs are skipped and recorded, not treated as fatal.

Screenshots, shortcut targets and antivirus detections still need to be provided
separately; this collector does not inspect the desktop or security history.
`--no-pause` is available for automation. Integration tests:
`python tools/diagnostics/test_collect_diagnostics.py` on Windows, with hidden
processes, isolated synthetic installations and redirected local app data.

# FH6 Local Recovery Test

`Run_FH6_Local_RTTI_Recovery_Test.bat` launches KFPS with one forced FH6
compatibility-recovery test armed. Existing profile files are not deleted or
modified before the test.

1. Close KFPS, keep FH6 running, and open a grouped vinyl in the editor.
2. Run the diagnostic launcher.
3. Perform one FH6 live export. This first FH6 transfer ignores known profiles,
   recovers locally, and revalidates through the normal exact locator.
4. Repeat the export in the same KFPS launch. The force flag has been consumed,
   so the recovered profile should be reused immediately.

The transfer log identifies the forced pass. Canonical reports are stored below
`runtime/live-memory/reports`, and a verified local profile is stored separately
at `runtime/fh6-rtti/local-recovery-RTTI.dat`. Nothing is published.
