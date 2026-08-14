# Livery Inspector Third-Party Files

The inspector vendors only the browser runtime files needed to render a portable
GLB package without a network connection.

| Component | Version | License | Source |
| --- | --- | --- | --- |
| Three.js | 0.185.1 | MIT | https://github.com/mrdoob/three.js/tree/r185 |

Vendored files:

- `vendor/three/build/three.module.min.js`
- `vendor/three/build/three.core.min.js`
- `vendor/three/examples/jsm/controls/OrbitControls.js`
- `vendor/three/examples/jsm/loaders/GLTFLoader.js`
- `vendor/three/examples/jsm/utils/BufferGeometryUtils.js`
- `vendor/three/examples/jsm/utils/SkeletonUtils.js`
- `vendor/three/LICENSE`

No Forza model, texture, game asset, or external importer is stored in this
directory. A portable mesh is created from the user's local installation only
when explicitly exporting an inspection-ready package.
