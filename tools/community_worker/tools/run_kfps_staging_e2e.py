from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from check_deployment_contract import check_contract


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
STAGING_CONFIG = WORKER_ROOT / "wrangler.staging.jsonc"
STAGING_STATE = WORKER_ROOT / ".staging"
SUPPORTER_ISSUER = WORKER_ROOT / "tools" / "test_supporter_token.mjs"
SEED = WORKER_ROOT / "tools" / "seed_local.py"
E2E_TEST = REPO_ROOT / "KFPS.UI" / "tests" / "community_e2e.py"


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip('"')
    return values


def public_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "KFPS-Staging-Validator/1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read(256 * 1024).decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read staging configuration from {url}: {error}") from error


def run_logged(arguments: list[str], log_path: Path | None, *, environment: dict[str, str]) -> None:
    if log_path is None:
        subprocess.run(arguments, cwd=REPO_ROOT, env=environment, check=True)
        return
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            arguments, cwd=REPO_ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            output.write(line)
            output.flush()
        return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, arguments)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete KFPS client workflow against an isolated staging Worker.")
    parser.add_argument("--api-url", required=True, help="Staging API URL ending in /v1.")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--report-dir", type=Path, help="Write sanitized per-run logs and results here.")
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 10:
        raise RuntimeError("--repetitions must be between 1 and 10.")
    parsed = urllib.parse.urlsplit(args.api_url.rstrip("/"))
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith("/v1"):
        raise RuntimeError("Staging API URL must be an HTTPS URL ending in /v1.")
    if not STAGING_CONFIG.is_file():
        raise RuntimeError("Run prepare_staging.py before staging validation.")
    check_contract(STAGING_CONFIG)
    values = read_dotenv(STAGING_STATE / "test.env")
    test_token = values.get("KFPS_COMMUNITY_TEST_AUTH_TOKEN", "")
    key_path = STAGING_STATE / "supporter-test-key.json"
    if len(test_token) < 32 or not key_path.is_file():
        raise RuntimeError("Private staging test credentials are incomplete.")

    api = args.api_url.rstrip("/")
    config = public_json(api + "/config")
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if config.get("deployment_environment") != "staging":
        raise RuntimeError("Refusing to test a Worker that does not identify itself as staging.")
    if not config.get("test_auth"):
        raise RuntimeError("Staging test authentication is disabled.")
    if config.get("modern_upload_client_required"):
        raise RuntimeError("The legacy upload bridge is disabled in staging.")
    if config.get("minimum_upload_version") != "3.0.81":
        raise RuntimeError("Staging compatibility upload floor is not 3.0.81.")

    environment = os.environ.copy()
    environment.update({
        "KFPS_COMMUNITY_API_URL": api,
        "KFPS_COMMUNITY_TEST_AUTH_TOKEN": test_token,
        "KFPS_COMMUNITY_SUPPORTER_ISSUER": str(SUPPORTER_ISSUER),
        "KFPS_COMMUNITY_TEST_SUPPORTER_KEY": str(key_path),
        "KFPS_COMMUNITY_UNIQUE_SUPPORTER_ENTITLEMENTS": "1",
        "KFPS_COMMUNITY_EXPECTED_ENVIRONMENT": "staging",
        "KFPS_COMMUNITY_EXPECTED_MINIMUM_UPLOAD_VERSION": "3.0.81",
        "KFPS_APP_VERSION": version,
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
    })
    report_root = args.report_dir.resolve() if args.report_dir else None
    if report_root is not None:
        report_root.mkdir(parents=True, exist_ok=True)
    for index in range(1, args.repetitions + 1):
        print(f"[community-staging] Seeding and validating repetition {index}/{args.repetitions}.", flush=True)
        run_dir = report_root / f"run-{index:02d}" if report_root is not None else None
        if run_dir is not None:
            run_dir.mkdir(parents=True)
        started = time.monotonic()
        success = False
        try:
            run_logged(
                [sys.executable, str(SEED)], run_dir / "seed.log" if run_dir else None,
                environment=environment,
            )
            run_logged(
                [sys.executable, str(E2E_TEST), "-v"], run_dir / "e2e-test.log" if run_dir else None,
                environment=environment,
            )
            success = True
        finally:
            if run_dir is not None:
                (run_dir / "result.json").write_text(json.dumps({
                    "schema": "kfps.community-staging-run.v1",
                    "index": index,
                    "success": success,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "api_url": api,
                    "app_version": version,
                }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[community-staging] {args.repetitions} staging end-to-end run(s) passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[community-staging] FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
