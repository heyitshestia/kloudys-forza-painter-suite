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
