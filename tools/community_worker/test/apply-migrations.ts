import { applyD1Migrations, env, type D1Migration } from "cloudflare:test";
import { beforeAll } from "vitest";

declare global {
  namespace Cloudflare {
    interface Env {
      DB: D1Database;
      ASSETS: R2Bucket;
      TEST_MIGRATIONS: D1Migration[];
      ADMIN_TOKEN: string;
      ALLOW_TEST_AUTH: string;
      AUTO_APPROVE_TEST_UPLOADS: string;
      AUTO_PUBLISH_VALIDATED_UPLOADS: string;
      API_PROTOCOL: string;
      DEPLOYMENT_ENVIRONMENT: string;
      GITHUB_CLIENT_ID: string;
      MINIMUM_UPLOAD_VERSION: string;
      COMPATIBILITY_MINIMUM_UPLOAD_VERSION: string;
      REQUIRE_MODERN_UPLOAD_CLIENT: string;
      TEST_AUTH_TOKEN: string;
      VERSION_SYNC_ENABLED: string;
      VERSION_REPOSITORY: string;
      VERSION_BRANCH: string;
      SUPPORTER_ENTITLEMENT_KEY_ID: string;
      SUPPORTER_ENTITLEMENT_MODULUS_HEX: string;
      TEST_SUPPORTER_PRIVATE_KEY_PEM: string;
    }
  }
}

beforeAll(async () => {
  await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
});
