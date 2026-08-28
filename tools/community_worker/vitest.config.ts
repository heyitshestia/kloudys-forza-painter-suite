import path from "node:path";
import { createPublicKey, generateKeyPairSync } from "node:crypto";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

const supporterTestKeys = generateKeyPairSync("rsa", {
  modulusLength: 3072,
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});
const supporterPublicJwk = createPublicKey(supporterTestKeys.publicKey)
  .export({ format: "jwk" });
const supporterModulusHex = Buffer.from(String(supporterPublicJwk.n), "base64url").toString("hex");

export default defineConfig({
  plugins: [
    cloudflareTest(async () => ({
      wrangler: { configPath: "./wrangler.e2e.jsonc" },
      miniflare: {
        bindings: {
          TEST_MIGRATIONS: await readD1Migrations(path.join(import.meta.dirname, "migrations")),
          ADMIN_TOKEN: "local-test-admin-token-that-is-at-least-32-characters",
          ALLOW_TEST_AUTH: "1",
          AUTO_APPROVE_TEST_UPLOADS: "1",
          AUTO_PUBLISH_VALIDATED_UPLOADS: "1",
          API_PROTOCOL: "1",
          DEPLOYMENT_ENVIRONMENT: "local-unit-test",
          GITHUB_CLIENT_ID: "",
          MINIMUM_UPLOAD_VERSION: "3.0.81",
          COMPATIBILITY_MINIMUM_UPLOAD_VERSION: "3.0.81",
          REQUIRE_MODERN_UPLOAD_CLIENT: "1",
          TEST_AUTH_TOKEN: "",
          VERSION_SYNC_ENABLED: "1",
          VERSION_REPOSITORY: "heyitshestia/kloudys-forza-painter-suite",
          VERSION_BRANCH: "main",
          SUPPORTER_ENTITLEMENT_KEY_ID: "activation-test-2026",
          SUPPORTER_ENTITLEMENT_MODULUS_HEX: supporterModulusHex,
          TEST_SUPPORTER_PRIVATE_KEY_PEM: supporterTestKeys.privateKey,
        },
      },
    })),
  ],
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
    sequence: { concurrent: false },
  },
});
