"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
async function main() {
  const calls = [], headers = { "X-KFPS-Editor-Session": "read-session" };
  const context = vm.createContext({ Blob, TextEncoder, TextDecoder, AbortSignal, setTimeout, clearTimeout, performance, self: {},
    indexedDB: { open() { throw Error("not available"); } },
    fetch: async (url, options) => {
      assert.equal(options.headers["X-KFPS-Editor-Session"], headers["X-KFPS-Editor-Session"]);
      calls.push(url);
      return new Response(JSON.stringify({ recovery_revision: 1, payload: { shapes: [] } }));
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../editor-persistence-worker.js"), "utf8"), context);
  const config = { headers, maxBytes: 1024 };
  await context.execute({ operation: "fetchJSON", url: "/api/fabric-editor/project-file?id=test", config });
  await context.execute({ operation: "fetchJSON", url: "/api/fabric-editor/project-receipt?id=test", config });
  await context.execute({ operation: "recoveryHead", config });
  await context.execute({ operation: "readRecovery", config });
  assert.equal(calls.length, 4);
  console.log("Private persistence reads carry the session on projects, receipts and recovery.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
