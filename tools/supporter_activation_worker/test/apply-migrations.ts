import { applyD1Migrations, env, type D1Migration } from "cloudflare:test";
import { beforeAll } from "vitest";

declare global {
  namespace Cloudflare {
    interface Env {
      DB: D1Database;
      TEST_MIGRATIONS: D1Migration[];
      ACTIVATION_PRIVATE_KEY_PEM: string;
      ADMIN_HMAC_SECRET: string;
      ACTIVATION_KEY_ID: string;
    }
  }
}

beforeAll(async () => {
  await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
});
