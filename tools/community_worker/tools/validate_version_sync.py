from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
DEFAULT_SECRETS = WORKER_ROOT / ".staging" / "deploy.secrets"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def read_secret(path: Path, name: str) -> str:
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith(name + "="):
            return raw.split("=", 1)[1].strip().strip('"')
    return ""


def request_json(url: str, admin_token: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": "KFPS-Community-Version-Validation/1",
        "X-Community-Admin-Token": admin_token,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read(256 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read(256 * 1024).decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {"error": "non_json_http_error", "body_excerpt": raw[:1000]}
        return error.code, value


def policy(value: dict) -> dict:
    return dict(value.get("version") or {})


def zip_report(report_dir: Path) -> Path:
    target = report_dir.with_suffix(".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in report_dir.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(report_dir.parent))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Force and verify one exact repository VERSION synchronization.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--expected-environment", choices=("staging", "production"), required=True)
    parser.add_argument("--secrets-file", type=Path, default=DEFAULT_SECRETS)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Reports")
    args = parser.parse_args()
    api = args.api_url.rstrip("/")
    parsed = urllib.parse.urlsplit(api)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith("/v1"):
        raise RuntimeError("API URL must be HTTPS and end in /v1.")
    admin_token = read_secret(args.secrets_file.resolve(), "ADMIN_TOKEN")
    if len(admin_token) < 32:
        raise RuntimeError("The selected secrets file does not contain a valid admin token.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.output_dir.resolve() / f"KFPS-Community-Version-Sync-{args.expected_environment}-{timestamp}"
    report_dir.mkdir(parents=True)
    result = 1
    error = ""
    evidence: dict = {
        "schema": "kfps.community-version-sync-validation.v1",
        "api_url": api,
        "environment": args.expected_environment,
        "success": False,
    }
    try:
        with urllib.request.urlopen(urllib.request.Request(
            api + "/config", headers={"Accept": "application/json", "User-Agent": "KFPS-Community-Version-Validation/1"},
        ), timeout=30) as response:
            config = json.loads(response.read(256 * 1024).decode("utf-8"))
        if config.get("deployment_environment") != args.expected_environment:
            raise RuntimeError("Community endpoint environment did not match the requested target.")

        status, before_value = request_json(api + "/admin/version", admin_token)
        before = policy(before_value)
        if status != 200:
            raise RuntimeError(f"Could not read version policy: HTTP {status}.")
        status, synced_value = request_json(api + "/admin/version", admin_token, "POST", {"action": "sync"})
        synced = policy(synced_value)
        if status != 200:
            raise RuntimeError(f"Repository version synchronization failed: HTTP {status}.")
        if not COMMIT_PATTERN.fullmatch(str(synced.get("source_commit") or "")):
            raise RuntimeError("Version synchronization did not retain an exact source commit.")
        if synced.get("source_transport") not in {"github_api", "git_smart_http"}:
            raise RuntimeError("Version synchronization did not report a recognized source transport.")
        expected_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if synced.get("minimum_upload_version") != expected_version:
            raise RuntimeError("Synchronized version does not match this repository VERSION.")

        after = synced
        if not bool(before.get("automatic")):
            status, after_value = request_json(api + "/admin/version", admin_token, "POST", {"action": "pause"})
            after = policy(after_value)
            if status != 200 or bool(after.get("automatic")):
                raise RuntimeError("Version policy could not be restored to its original paused state.")
        evidence.update({
            "before": before,
            "synchronized": synced,
            "after": after,
        })
        result = 0
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        print(f"[version-sync] FAILED: {error}", file=sys.stderr)
    finally:
        evidence.update({
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "success": result == 0,
            "exit_code": result,
            "error": error,
        })
        report_path = report_dir / "result.json"
        report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if admin_token in report_path.read_text(encoding="utf-8"):
            result = 1
            evidence.update(success=False, exit_code=1, error="Report redaction verification failed.")
            report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (report_dir / "README.txt").write_text(
            "Repository VERSION synchronization evidence. The admin credential is not stored.\n",
            encoding="utf-8",
        )
        archive = zip_report(report_dir)
        print(f"[version-sync] Report: {archive}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[version-sync] FAILED before reporting started: {error}", file=sys.stderr)
        raise SystemExit(1)
