# Theme Media Authoring

These are offline authoring tools, not application dependencies. The application
uses its existing Qt multimedia player and does not run Three.js at startup.

`build_xbox_startup.cjs` accepts three arguments: the supplied soundtrack's source
movie, an FFmpeg executable, and a named build-output directory. It uses Node.js,
Playwright with installed Chrome, and the existing vendored Three.js. Chrome is
headless with software rendering; encoding uses two CPU threads. No visible
window or audible playback is launched.

```powershell
node tools/theme-assets/build_xbox_startup.cjs "reference.mp4" "ffmpeg.exe" "runtime/theme-builds/xbox"
```

The audio source must be the reviewed 11.73-second supplied movie.
Its source SHA-256 is
`a0e81ed471e300b948c759575eb1a51c40a58c18ff0b74c24fa2461c21a71e7c`.
Do not substitute a different audio edit without reviewing synchronization.
The supplied video's pixels are never decoded or composited into the output:
FFmpeg maps only the authored movie's video and the supplied movie's audio.
`xbox-startup-scene.mjs` owns all geometry, shaders, lighting and animation.
The full movie has 704 rendered frames at 60 fps, like the PS2 offline-render
approach. There is no live Three.js scene in the application.

Append `--preview` for twelve inexpensive keyframe renders before full encoding.
The output includes a manifest, representative frames, motion samples, encoding
log, an intermediate silent authored movie and `startup.mp4`.

The final movie is installed at
`KFPS.UI/assets/themes/original-xbox/startup.mp4`. The player
also supports a local override at `runtime/theme-assets/original-xbox/startup.mp4`.
Neither file is required to launch: missing media opens the menu directly.

The maintainer confirmed permission to redistribute the supplied soundtrack with
KFPS on 26 October 2026. This does not grant third-party reuse rights. See
`KFPS.UI/assets/themes/original-xbox/STARTUP-NOTICE.md` for provenance.
