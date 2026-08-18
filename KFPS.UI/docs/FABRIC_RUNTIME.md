# Fabric editor runtime

## Current decision

KFPS currently ships Fabric 5.3 behind `editor-fabric-adapter.js`. Do not replace
the vendored runtime by changing only `vendor/fabric.min.js`. A runtime change must
pass the editor API adapter and the complete product workflow.

KFPS does not use Fabric's SVG import or canvas SVG export paths. Those APIs are
disabled at startup to keep unused SVG parsing outside the local editor's attack
surface. KFPS project JSON remains the source of truth.

## Adapter contract

The adapter owns:

- scene-coordinate pointer conversion;
- object stacking and explicit stack replacement;
- front/back and indexed move operations;
- validation that a replacement stack contains no null or duplicate objects;
- disabling unsupported SVG operations.

Editor code should use this adapter instead of private `_objects` mutation or
version-specific object methods. A missing adapter is a startup error.

## Fabric 7 evaluation

Fabric 7.4 was evaluated in an isolated copy of the editor. Project roundtrip,
pan/zoom, 3000-layer limits, history, masks, and hybrid rendering worked with a
small compatibility layer. It was not promoted because 3000-layer interaction
regressed substantially under the same local benchmark:

| Operation | Fabric 5.3 | Fabric 7.4 trial |
| --- | ---: | ---: |
| 3000-layer multi-select | about 8-14 ms | about 90 ms |
| selected-layer nudge | about 1.7-3 ms | about 47 ms |

The trial improved some history and hybrid drawing paths, but those gains did not
justify the selection and movement regression. The preserved evidence is under
`audit/2026-08-17/evidence/fabric-7.4-spike/` in the development workspace.

## Upgrade gate

A future upgrade must, under identical inputs:

1. preserve exact KFPS project export/import roundtrip;
2. pass pan, zoom, masks, history, layer drag, hybrid fallback, and alpha tests;
3. enforce the 3000-layer limit;
4. keep first interaction, 3000-layer selection, nudge, and layer browser latency
   within the accepted Fabric 5 baseline;
5. keep local-server session and origin protections intact;
6. pass a real editor launch from `EditorService`, not only a static page test.

Until those conditions are met, hardening the existing runtime is safer than a
nominal version upgrade.
