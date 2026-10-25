# Original PS2 Theme

Choose **Original PS2** in Settings. The main window opens to a PS2-inspired
Browser/System Configuration menu. Browser opens the KFPS tools; System
Configuration opens Settings. Return to the main menu to change sections.
Normal window movement, minimize, maximize and close controls remain available.

On the next launch, a sound-timed startup animation plays inside the window while
KFPS indexes outputs. It hands off to the menu when loading is ready. Escape,
Enter or Space skips it. Minimize pauses both picture and sound. Reduced Motion
bypasses it. Missing or invalid media falls back to the menu.

The PS2-only startup-mute setting persists across restarts. Temporary
recording/replay buttons are not included. Switching themes during a session
does not replay the intro.

## Compatibility

The main app, Vinyl Editor and Livery Studio share the new theme. The editors
retain their existing editing layouts and renderers. Existing theme formats,
keys, custom themes, shortcuts, projects and import/export behavior are unchanged.
The new built-in preset is `builtin:ps2`; the mute preference is optional and
defaults to sound enabled.

The startup uses Qt multimedia decoding into the existing QML image path; it
does not change OpenGL, Direct3D or editor graphics selection. The packaged movie
is `KFPS.UI/assets/themes/ps2/startup.mp4`. Its provenance is recorded in the
adjacent [notice](../KFPS.UI/assets/themes/ps2/NOTICE.md).

## Regression Checks

From the repository root with the locked Python dependencies installed:

```powershell
python -B KFPS.UI/tools/test_ps2_theme.py 1360 820
python -B KFPS.UI/tools/test_ps2_startup.py packaged 1280 760
```

These checks use isolated profiles and silent offscreen windows. Further startup
cases include `normal`, `muted-start`, `skip`, `missing`, `corrupt`, `audio-only`,
`reduced`, `reduce-live`, `slow`, `theme`, `close`, `legacy` and `library`.
Results are written under `runtime/test-runs`; tests can override the output
root using `KFPS_STARTUP_TEST_RUN_ROOT` or `KFPS_PS2_TEST_OUTPUT`.

Offscreen checks do not validate physical monitor transitions, every GPU driver
or audible output on every Windows audio device.
