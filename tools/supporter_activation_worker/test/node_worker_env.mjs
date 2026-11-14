// Offline fallback for running the real fetch handler when workerd cannot start.
import { generateKeyPairSync } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import worker from "../src/index.ts";

const database = new DatabaseSync(":memory:");
const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 3072,
  publicExponent: 0x10001,
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});

class Statement {
  constructor(sql, values = []) {
    this.sql = sql;
    this.values = values;
  }
  bind(...values) { return new Statement(this.sql, values); }
  native() { return database.prepare(this.sql); }
  parameters() { return Object.fromEntries(this.values.map((value, index) => [`?${index + 1}`, value])); }
  async first(column) {
    const row = this.native().get(this.parameters());
    return column ? row?.[column] ?? null : row ?? null;
  }
  async all() {
    return { results: this.native().all(this.parameters()), success: true, meta: { changes: 0 } };
  }
  async run() {
    const result = this.native().run(this.parameters());
    return { results: [], success: true, meta: { changes: Number(result.changes) } };
  }
}

export const env = {
  DB: {
    prepare: (sql) => new Statement(sql),
    batch: (statements) => Promise.all(statements.map((statement) =>
      /^\s*SELECT\b/i.test(statement.sql) ? statement.all() : statement.run())),
  },
  TEST_MIGRATIONS: [],
  ACTIVATION_KEY_ID: "activation-rsa-2026-01",
  ACTIVATION_PRIVATE_KEY_PEM: privateKey,
  ADMIN_HMAC_SECRET: "test-admin-secret-that-is-longer-than-thirty-two-characters",
  KOFI_VERIFICATION_TOKEN: "test-kofi-verification-token-2026",
  KOFI_INBOX_PUBLIC_KEY_PEM: publicKey,
};

export async function applyD1Migrations() {
  const directory = new URL("../migrations/", import.meta.url);
  for (const name of readdirSync(directory).filter((name) => name.endsWith(".sql")).sort()) {
    database.exec(readFileSync(new URL(name, directory), "utf8"));
  }
}

export const SELF = {
  fetch(input, init) {
    const request = input instanceof Request && !init ? input : new Request(input, { ...init, duplex: "half" });
    return worker.fetch(request, env);
  },
};
