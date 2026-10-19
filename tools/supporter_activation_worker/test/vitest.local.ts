import path from "node:path";
import { generateKeyPairSync } from "node:crypto";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

const root = path.resolve(import.meta.dirname, "..");
const runDirectory = process.env.KFPS_WORKER_TEST_RUN;
if (!runDirectory || !path.isAbsolute(runDirectory)) throw new Error("KFPS_WORKER_TEST_RUN must be an absolute run directory");

export default defineConfig({
  root,
  cacheDir: path.join(runDirectory, "vite-cache"),
  plugins: [cloudflareTest(async () => {
    const { privateKey, publicKey } = generateKeyPairSync("rsa", {
      modulusLength: 3072,
      publicExponent: 0x10001,
      publicKeyEncoding: { type: "spki", format: "pem" },
      privateKeyEncoding: { type: "pkcs8", format: "pem" },
    });
    return {
      main: path.join(root, "src/index.ts"),
      remoteBindings: false,
      miniflare: {
        compatibilityDate: "2026-07-13",
        d1Databases: ["DB"],
        bindings: {
          TEST_MIGRATIONS: await readD1Migrations(path.join(root, "migrations")),
          ACTIVATION_KEY_ID: "activation-rsa-2026-01",
          ACTIVATION_PRIVATE_KEY_PEM: privateKey,
          ADMIN_HMAC_SECRET: "test-admin-secret-that-is-longer-than-thirty-two-characters",
          KOFI_VERIFICATION_TOKEN: "test-kofi-verification-token-2026",
          KOFI_INBOX_PUBLIC_KEY_PEM: publicKey,
        },
      },
    };
  })],
  test: {
    setupFiles: [path.join(root, "test/apply-migrations.ts")],
    sequence: { concurrent: false },
  },
});
