from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from check_deployment_contract import check_contract


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
CONFIG = WORKER_ROOT / "wrangler.staging.jsonc"
STATE = WORKER_ROOT / ".staging"
VALIDATOR = WORKER_ROOT / "tools" / "run_kfps_staging_e2e.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_values() -> list[str]:
    values: list[str] = []
    for path in (STATE / "deploy.secrets", STATE / "test.env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            if "=" in raw:
                value = raw.split("=", 1)[1].strip().strip('"')
                if value:
                    values.append(value)
    return values


def redact(value: str, secrets: list[str]) -> str:
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    return value


def run_logged(arguments: list[str], log_path: Path, secrets: list[str]) -> None:
    printable = " ".join(arguments)
    print(f"[staging-deploy] {printable}", flush=True)
    environment = os.environ.copy()
    environment.update({"CI": "true", "NO_COLOR": "1", "PYTHONUTF8": "1"})
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            arguments, cwd=WORKER_ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            safe = redact(line, secrets)
            print(safe, end="", flush=True)
            output.write(safe)
            output.flush()
        return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, arguments)


def command_output(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            arguments, cwd=REPO_ROOT, check=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return (result.stdout or result.stderr).strip()[:4096]
    except (OSError, subprocess.SubprocessError) as error:
        return f"unavailable: {error}"


def deployment_environment(npx: str) -> dict:
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.splitlines()[0],
        "node": command_output(["node", "--version"]),
        "npm": command_output(["npm.cmd" if os.name == "nt" else "npm", "--version"]),
        "wrangler": command_output([npx, "wrangler", "--version"]),
        "git_commit": command_output(["git", "rev-parse", "HEAD"]),
        "git_branch": command_output(["git", "branch", "--show-current"]),
        "git_changes": [
            line for line in command_output(["git", "status", "--short"]).splitlines() if line
        ],
    }


def public_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "KFPS-Staging-Deployment/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"status": response.status, "value": json.loads(response.read(256 * 1024).decode("utf-8"))}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        return {"error": str(error)}


def wait_until_ready(api_url: str, log_path: Path, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict] = []
    while True:
        health = public_json(api_url.rstrip("/") + "/health")
        config = public_json(api_url.rstrip("/") + "/config")
        catalog = public_json(api_url.rstrip("/") + "/artworks?limit=1&sort=name")
        attempt = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "health": health,
            "config": config,
            "catalog": catalog,
        }
        attempts.append(attempt)
        log_path.write_text(json.dumps(attempts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        healthy = health.get("status") == 200 and dict(health.get("value") or {}).get("status") == "ok"
        staged = config.get("status") == 200 and dict(config.get("value") or {}).get("deployment_environment") == "staging"
        catalog_ready = catalog.get("status") == 200 and isinstance(dict(catalog.get("value") or {}).get("items"), list)
        if healthy and staged and catalog_ready:
            print(f"[staging-deploy] Worker became ready after {len(attempts)} check(s).")
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Staging Worker was not ready after {len(attempts)} checks.")
        time.sleep(2)


def write_zip(report_dir: Path) -> Path:
    target = report_dir.parent / f"{report_dir.name}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in report_dir.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(report_dir.parent))
    return target


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Deploy isolated Community staging and preserve sanitized evidence.")
    parser.add_argument("--api-url", required=True, help="Staging HTTPS API URL ending in /v1.")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Reports")
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 10:
        raise RuntimeError("--repetitions must be between 1 and 10.")
    if not CONFIG.is_file() or not (STATE / "deploy.secrets").is_file() or not (STATE / "test.env").is_file():
        raise RuntimeError("Prepare the isolated staging configuration before deployment.")
    check_contract(CONFIG)
    secrets = private_values()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_root = args.output_dir.resolve()
    report_dir = report_root / f"KFPS-Community-Staging-Deployment-{timestamp}"
    report_dir.mkdir(parents=True)
    result = 1
    error = ""
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    environment_evidence = deployment_environment(npx) if npx else {
        "error": "npx was not found on the deployment machine.",
    }
    try:
        if not npx:
            raise RuntimeError("npx was not found on the deployment machine.")
        run_logged([
            npx, "wrangler", "d1", "migrations", "apply", "DB", "--remote",
            "--config", str(CONFIG),
        ], report_dir / "migration.log", secrets)
        run_logged([
            npx, "wrangler", "deploy", "--config", str(CONFIG),
            "--secrets-file", str(STATE / "deploy.secrets"),
        ], report_dir / "deployment.log", secrets)
        wait_until_ready(args.api_url, report_dir / "readiness.json")
        run_logged([
            sys.executable, str(VALIDATOR), "--api-url", args.api_url,
            "--repetitions", str(args.repetitions), "--report-dir", str(report_dir / "runs"),
        ], report_dir / "validation.log", secrets)
        result = 0
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        print(f"[staging-deploy] FAILED: {error}", file=sys.stderr)
    finally:
        evidence = {
            "schema": "kfps.community-staging-deployment.v1",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "success": result == 0,
            "exit_code": result,
            "error": redact(error, secrets),
            "api_url": args.api_url.rstrip("/"),
            "kfps_version": (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "config_sha256": sha256(CONFIG),
            "migrations": {
                path.name: sha256(path) for path in sorted((WORKER_ROOT / "migrations").glob("*.sql"))
            },
            "environment": environment_evidence,
            "health": public_json(args.api_url.rstrip("/") + "/health"),
            "config": public_json(args.api_url.rstrip("/") + "/config"),
        }
        (report_dir / "result.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        (report_dir / "README.txt").write_text(
            "Sanitized Community staging deployment evidence. Secret values and private test keys are excluded.\n",
            encoding="utf-8",
        )
        serialized = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in report_dir.rglob("*") if path.is_file()
        )
        leaked = [secret for secret in secrets if secret and secret in serialized]
        if leaked:
            result = 1
            evidence["success"] = False
            evidence["exit_code"] = 1
            evidence["error"] = "Report redaction verification failed."
            (report_dir / "result.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )
            print("[staging-deploy] FAILED: report redaction verification failed.", file=sys.stderr)
        archive = write_zip(report_dir)
        print(f"[staging-deploy] Report: {archive}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[staging-deploy] FAILED before reporting started: {error}", file=sys.stderr)
        raise SystemExit(1)
