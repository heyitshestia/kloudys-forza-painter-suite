# Xbox Startup Asset

`startup.mp4` has original KFPS-rendered visuals, made on 25 October 2026 using
the supplied Xbox startup movie as a visual/timing reference only.

- Every video frame is rendered from original Three.js geometry, shaders,
  lighting and camera motion. No supplied video frames are used.
- Its supplied stereo soundtrack is copied without re-encoding.
- The scene contains opposing mechanical emitters, independent rotor motion,
  a deformed liquid-green core, chamber lighting and an original KFPS wordmark.
  No standalone K emblem or Xbox/Microsoft logo is included.
- Resolution: 1280 x 720, 60 fps; duration: approximately 11.73 seconds.
- SHA-256: `3dee424574af4b904c92d006add2a4483bab37462b5dcfc264df7faeda68fe37`.

On 26 October 2026, the KFPS maintainer confirmed permission to redistribute the
supplied soundtrack with this KFPS startup animation. This records the
maintainer's authorization; it does not place the soundtrack in the public domain
or grant third-party reuse rights. The separate PS2 soundtrack has its own notice.

Build sources are in `tools/theme-assets/`. Rendering uses the repository's
existing MIT-licensed Three.js vendor copy; authoring dependencies are not added
to the application's runtime. The original supplied movie is not copied into
the repository.
