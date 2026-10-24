# Original Xbox Theme

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
