import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const root = resolve(process.argv[2] || process.cwd());
const readJson = async path => JSON.parse(await readFile(path, "utf8"));
const manifest = await readJson(join(root, "package.json"));
const lock = await readJson(join(root, "package-lock.json"));
const patchedVersion = "0.35.5";
assert.equal(manifest.overrides?.miniflare?.sharp, patchedVersion, "Keep the reviewed image dependency override until an upstream replacement is verified.");
const entries = Object.entries(lock.packages || {});
const sharpEntries = entries.filter(([path]) => /(?:^|\/)node_modules\/sharp$/.test(path));
const miniflareEntries = entries.filter(([path]) => /(?:^|\/)node_modules\/miniflare$/.test(path));
assert.ok(sharpEntries.length, "No locked sharp dependency found.");
assert.ok(miniflareEntries.length, "No locked Miniflare dependency found.");
for (const [path, metadata] of sharpEntries) {
  assert.equal(metadata.version, patchedVersion, `Unexpected locked image dependency at ${path}`);
  assert.equal((await readJson(join(root, path, "package.json"))).version, patchedVersion, `Installation differs from lock at ${path}`);
}

const results = [];
for (const [path, metadata] of miniflareEntries) {
  const require = createRequire(join(root, path, "package.json"));
  const sharp = require("sharp");
  assert.equal(sharp.versions.sharp, patchedVersion, `${path} resolves an unreviewed sharp version`);
  const miniflare = require(join(root, path));
  const original = await sharp({ create: { width: 16, height: 12, channels: 4, background: { r: 32, g: 96, b: 176, alpha: 0.5 } } }).png().toBuffer();
  const avif = await sharp(original).avif({ lossless: true }).toBuffer();
  const decoded = await sharp(avif).metadata();
  assert.equal(decoded.width, 16);
  assert.equal(decoded.height, 12);
  assert.equal(decoded.hasAlpha, true);
  let outboundRequests = 0;
  const options = {
    modules: true,
    host: "127.0.0.1",
    port: 0,
    compatibilityDate: "2026-07-01",
    images: { binding: "IMAGES" },
    script: `export default {
      async fetch(request, env) {
        if (new URL(request.url).pathname === "/binding") {
          const result = await env.IMAGES.input(request.body)
            .transform({ width: 7, height: 5, fit: "cover" })
            .output({ format: "image/png" });
          return result.response();
        }
        return fetch("https://kfps-image-fixture.invalid/source.avif", {
          cf: { image: { width: 7, height: 5, fit: "cover", format: "png" } }
        });
      }
    };`,
    outboundService: async request => {
      assert.equal(request.url, "https://kfps-image-fixture.invalid/source.avif");
      outboundRequests++;
      return new Response(avif, { headers: { "Content-Type": "image/avif" } });
    },
  };
  const worker = new miniflare.Miniflare(miniflare.convertV4MiniflareOptions ? miniflare.convertV4MiniflareOptions(options) : options);
  try {
    for (const route of ["binding", "cf-image"]) {
      const response = await worker.dispatchFetch(`http://image-check.local/${route}`, { method: "POST", body: avif });
      const body = Buffer.from(await response.arrayBuffer());
      assert.equal(response.status, 200, `${path} ${route}: ${body.toString("utf8").slice(0, 200)}`);
      assert.match(response.headers.get("content-type") || "", /^image\/png/);
      const image = await sharp(body).metadata();
      assert.equal(image.width, 7, `${route} did not resize the image`);
      assert.equal(image.height, 5);
      assert.equal(image.hasAlpha, true);
    }
    assert.equal(outboundRequests, 1, "Only the synthetic cf.image origin should be fetched.");
    results.push({ path, miniflare: metadata.version, sharp: sharp.versions.sharp, heif: sharp.versions.heif, pngAvifRoundtrip: true, imagesBinding: true, cfImage: true });
  } finally {
    await worker.dispose();
  }
}
console.log(JSON.stringify({ package: manifest.name, checkedSharpCopies: sharpEntries.length, results }, null, 2));
