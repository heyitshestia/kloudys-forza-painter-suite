import { createPublicKey, generateKeyPairSync, randomBytes, randomUUID, sign } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

function base64Url(value) {
  return Buffer.from(value).toString("base64url");
}

function generate(outputPath) {
  const keys = generateKeyPairSync("rsa", {
    modulusLength: 3072,
    publicKeyEncoding: { type: "spki", format: "pem" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });
  const publicJwk = createPublicKey(keys.publicKey).export({ format: "jwk" });
  const value = {
    entitlement_id: randomUUID(),
    key_id: "community-e2e-only",
    modulus_hex: Buffer.from(String(publicJwk.n), "base64url").toString("hex"),
    private_key_pem: keys.privateKey,
  };
  writeFileSync(outputPath, JSON.stringify(value), { encoding: "utf8", mode: 0o600 });
}

function issue(keyPath, subject, unique = false) {
  const key = JSON.parse(readFileSync(keyPath, "utf8"));
  const issued = Date.now();
  const payload = {
    audience: "kfps-community-v1",
    entitlement_id: unique ? randomUUID() : key.entitlement_id,
    expires_at: new Date(issued + 15 * 60 * 1000).toISOString(),
    issued_at: new Date(issued).toISOString(),
    nonce: base64Url(randomBytes(32)),
    schema: "kfps.community.supporter.v1",
    subject,
  };
  const payloadBytes = Buffer.from(canonicalJson(payload), "utf8");
  process.stdout.write(JSON.stringify({
    type: "kfps.supporter.community-entitlement",
    version: 1,
    kid: key.key_id,
    payload: base64Url(payloadBytes),
    signature: sign("RSA-SHA256", payloadBytes, key.private_key_pem).toString("base64url"),
  }));
}

const [command, ...args] = process.argv.slice(2);
if (command === "generate" && args.length === 1) generate(args[0]);
else if (command === "issue" && args.length === 2) issue(args[0], args[1]);
else if (command === "issue-unique" && args.length === 2) issue(args[0], args[1], true);
else {
  process.stderr.write("Usage: node test_supporter_token.mjs generate KEY.json | issue[-unique] KEY.json SUBJECT\n");
  process.exitCode = 2;
}
