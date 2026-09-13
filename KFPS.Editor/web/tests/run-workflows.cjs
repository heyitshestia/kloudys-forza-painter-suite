"use strict";
const fs = require("node:fs"), path = require("node:path"), cp = require("node:child_process");
const root = path.resolve(__dirname, "../../..");
const [, , target, ...suites] = process.argv;
if (!target || !suites.length) throw Error("Supply an isolated output root and page regression filenames");
const output = path.resolve(root, target), allowed = path.join(root, "runtime", "test-runs") + path.sep;
if (!output.startsWith(allowed) || fs.existsSync(output)) throw Error("Workflow output must be a new test-run directory");
const contracts = JSON.parse(fs.readFileSync(path.join(__dirname, "workflow-contracts.json"), "utf8"));
if (contracts.schema !== "kfps-editor-workflow-contracts/1") throw Error("Unknown workflow contracts");
const seen = new Set();
for (const suite of suites) {
  if (!/^regression-[a-z0-9-]+\.js$/.test(suite) || !fs.existsSync(path.join(__dirname, suite))) throw Error("Unknown regression: " + suite);
  if (seen.has(suite)) throw Error("Duplicate workflow: " + suite);
  const prerequisite = contracts.cases[suite]?.profileFrom;
  if (prerequisite && !seen.has(prerequisite)) throw Error(`${suite} requires ${prerequisite} first`);
  seen.add(suite);
}
const stage = process.env.KFPS_TEST_APP_ROOT ? path.resolve(process.env.KFPS_TEST_APP_ROOT) : null;
if (stage && !stage.startsWith(allowed)) throw Error("Managed fixture must be under test-runs");
const python = stage ? path.join(stage,'python/python.exe') : cp.execFileSync("py", ["-3.12", "-c", "import sys; print(sys.executable)"], { encoding: "utf8", windowsHide: true }).trim();
fs.mkdirSync(output, { recursive: true });
const results = [];
const profiles = new Map();
for (const suite of suites) {
  const caseRoot = path.join(output, path.basename(suite, ".js"));
  const start = Date.now();
  const contract = contracts.cases[suite] || {};
  const timeout = contract.timeoutSeconds || 180;
  if (!Number.isInteger(timeout) || timeout < 30 || timeout > 900) throw Error('Invalid workflow deadline');
  const args = ["-B", path.join(__dirname, "run-native-page.py"), caseRoot, path.join(__dirname, suite), "--timeout", String(timeout)];
  if (contract.normalClose) args.push("--normal-close");
  if (stage) { args.unshift('-I'); args.push('--app-root',stage); }
  const profile = contract.profileFrom ? profiles.get(contract.profileFrom) : path.join(caseRoot,"profile");
  profiles.set(suite,profile);
  if (contract.profileFrom) args.push("--profile",profile);
  const testOptions = { ...JSON.parse(process.env.KFPS_TEST_OPTIONS || "{}"), preserveStartupNotices: Boolean(contract.preserveStartupNotices) };
  const result = cp.spawnSync(python, args, { cwd: root, encoding: "utf8", windowsHide: true, timeout: (timeout+30)*1000, maxBuffer: 4 * 1024 * 1024,
    env: { ...process.env, KFPS_TEST_OPTIONS: JSON.stringify(testOptions) } });
  fs.mkdirSync(caseRoot, { recursive: true });
  fs.writeFileSync(path.join(caseRoot, "host-stdout.log"), result.stdout || "");
  fs.writeFileSync(path.join(caseRoot, "host-stderr.log"), result.stderr || "");
  results.push({ suite, contract, ms: Date.now() - start, status: result.status, signal: result.signal, error: result.error?.message || null, passed: result.status === 0 });
  fs.writeFileSync(path.join(output, "summary.json"), JSON.stringify({ python, policy: "One real Qt process per workflow. Fresh profiles except declared restart prerequisites. No user data reset or auto-accepted native dialogs.", results }, null, 2));
  console.log(JSON.stringify(results.at(-1)));
}
process.exitCode = results.some(result => !result.passed) ? 1 : 0;
