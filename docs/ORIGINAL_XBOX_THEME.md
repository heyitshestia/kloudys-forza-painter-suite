# Original Xbox Theme

## Startup Animation (DIRTY Testing)

With Original Xbox selected, the next KFPS launch opens to an approximately
12-second, 60-fps reactor intro with sound and a KFPS wordmark reveal. The chamber,
moving electrodes, liquid core, camera and lighting are newly rendered in 3D;
there is no standalone K emblem or reused video footage.
This replaces the ordinary splash screen; there is no splash before or after it.
KFPS checks its runtime and loads its output index while the intro plays, then
opens the usual themed menu. If loading outlasts the movie, a silent loading
state holds the handoff; an unavailable output drive cannot block it indefinitely.
Changing themes during an already-running session does not replay the intro.

Settings offers **Mute intro sound** while Original Xbox is active. The saved
preference is independent of the PS2 mute setting. Escape, Enter or Space skips;
there are no visible skip, mute or recording buttons over the movie. Reduced
Motion bypasses it. Minimize pauses both picture and sound; restore resumes.
Window movement and normal close/minimize/maximize controls remain available.
Missing, corrupt or stalled media falls back to the menu.

Playback shares the existing PS2 decoder and ordinary QML image path. There is
no new renderer, GPU requirement or runtime dependency, and no changes to Vinyl
Editor or Studio rendering, project formats or graphics settings.

Only the supplied audio is reused. See the
[startup notice](../KFPS.UI/assets/themes/original-xbox/STARTUP-NOTICE.md).
The maintainer confirmed soundtrack redistribution permission on 26 October 2026.

Silent offscreen regression check:

```powershell
python -B KFPS.UI/tools/test_xbox_startup.py normal 1280 760
```

The same harness supports `packaged`, `muted-start`, `skip`, `skip-enter`,
`skip-space`, `missing`, `corrupt`, `audio-only`, `reduced`, `reduce-live`,
`slow`, `stalled`, `theme`, `close`, `legacy` and `library` scenarios. `production`
uses non-demo startup, the packaged movie, real runtime checks and 1500 synthetic
outputs; `production-warm` reuses that scenario's saved index. Run them in that
order at the same window size and test run root. Network-only services remain
offline in these tests. The cold scan worker is held until two decoded frames
prove concurrent playback, so its elapsed time is not a startup benchmark.
Tests use isolated profiles under `runtime/test-runs`
and never modify normal user settings.

Available from KFPS 3.1.117. This is an original dashboard-inspired theme, not
a Microsoft dashboard or a replacement graphics engine.

## Select The Theme

- KFPS: Settings > Theme > Original Xbox.
- Vinyl Editor: View > Theme > Original Xbox.
- Livery Studio: Appearance > Original Xbox > Apply.

The main application opens at a menu. Select a section with the mouse or use
Up/Down, Home/End and Enter. MENU in the return rail opens the menu again;
Back/Escape returns to the current section. On initial startup, choose a section
first. Credits is in the menu. Normal task-specific navigation remains available.
The title bar continues to support dragging, minimize, maximize, restore and close.

The editors keep their existing working layouts, shortcuts and tool behavior.
Choose any earlier theme to restore its normal appearance and navigation.

## Motion And Compatibility

KFPS's Ambient background motion and Reduce nonessential motion settings remain
authoritative. Ambient work stops while inactive, hidden or minimized. Browser
editor animations respect the browser/system reduced-motion preference.

Existing themes, custom theme IDs, project files, shortcuts and settings remain
valid. No project format, graphics backend or import/export behavior changes.
The new editor preset uses `builtin:xbox`, so existing custom themes called Xbox
are not replaced. Theme editing still uses the existing 33-color format.

New custom themes based on `builtin:xbox` require this updated application.
Older versions do not know that new preset; keep an earlier-compatible copy if
sharing themes with someone who has not updated. Studio's Follow KFPS mode carries
resolved colors and fonts, not the full material preset; choose Original Xbox
explicitly for its full Studio styling.

## Regression Coverage

The automated native test runs the real application offscreen:

```powershell
python -B KFPS.UI/tools/test_xbox_theme.py 1360 820
```

Set `KFPS_TEST_XBOX_MOTION=1` to include the motion/capture suite,
`QT_SCALE_FACTOR` for display-scale checks, and `KFPS_XBOX_TEST_OUTPUT` to choose
an isolated evidence directory. Otherwise evidence stays under
`runtime/test-runs/xbox-theme`. Tests do not activate a desktop window.

These checks cover actual input routing, theme changes, focus, window controls,
saved preferences and menu lifecycle. Physical multi-monitor movement and every
GPU/driver combination still require real-system testing.
