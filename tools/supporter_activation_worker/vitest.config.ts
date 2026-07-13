import path from "node:path";
import { generateKeyPairSync } from "node:crypto";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest(async () => {
      const migrations = await readD1Migrations(path.join(import.meta.dirname, "migrations"));
      const { privateKey, publicKey } = generateKeyPairSync("rsa", {
        modulusLength: 3072,
        publicExponent: 0x10001,
        publicKeyEncoding: { type: "spki", format: "pem" },
        privateKeyEncoding: { type: "pkcs8", format: "pem" },
      });
      return {
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            ACTIVATION_PRIVATE_KEY_PEM: privateKey,
            ADMIN_HMAC_SECRET: "test-admin-secret-that-is-longer-than-thirty-two-characters",
            KOFI_VERIFICATION_TOKEN: "test-kofi-verification-token-2026",
            KOFI_INBOX_PUBLIC_KEY_PEM: publicKey,
          },
        },
      };
    }),
  ],
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
    sequence: { concurrent: false },
  },
});
