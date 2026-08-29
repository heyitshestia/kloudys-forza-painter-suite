from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from check_deployment_contract import check_contract, load_config


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
CONFIG = WORKER_ROOT / "wrangler.jsonc"
WORKER_NAME = "kfps-community-library"
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SIGNED_EXPORT_URL_PATTERN = re.compile(r"https://\S+\?X-Amz-[^\s]+")
AUTHORITATIVE_TABLES = (
    "users", "sessions", "artworks", "artwork_revisions", "favorites", "follows", "ignored_users",
    "reports", "moderation_events", "rate_limits", "reserved_usernames",
    "download_events", "service_settings",
)
PENDING_MIGRATION_TABLES = frozenset({"ignored_users"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_text(value: str) -> str:
    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    return SIGNED_EXPORT_URL_PATTERN.sub("[REDACTED_TEMPORARY_EXPORT_URL]", value)


def command_output(arguments: list[str], cwd: Path = WORKER_ROOT) -> str:
    environment = os.environ.copy()
    environment.update({"CI": "true", "NO_COLOR": "1", "PYTHONUTF8": "1"})
    process = subprocess.run(
        arguments, cwd=cwd, env=environment, check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, arguments, process.stdout, process.stderr)
    return safe_text((process.stdout or "") + (process.stderr or ""))


def run_logged(arguments: list[str], log_path: Path) -> None:
    print(f"[production-deploy] {' '.join(arguments)}", flush=True)
    try:
        output = command_output(arguments)
    except subprocess.CalledProcessError as error:
        output = safe_text(str(error.output or "") + str(error.stderr or ""))
        log_path.write_text(output, encoding="utf-8")
        print(output, end="", flush=True)
        raise
    log_path.write_text(output, encoding="utf-8")
    print(output, end="", flush=True)


def public_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "KFPS-Production-Deployment/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"status": response.status, "value": json.loads(response.read(256 * 1024).decode("utf-8"))}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        return {"error": safe_text(str(error))}


def wait_until_ready(api_url: str, log_path: Path, timeout_seconds: int = 120) -> dict:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict] = []
    while True:
        health = public_json(api_url + "/health")
        config = public_json(api_url + "/config")
        catalog = public_json(api_url + "/artworks?limit=1&sort=name")
        config_value = dict(config.get("value") or {})
        catalog_value = dict(catalog.get("value") or {})
        attempt = {
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "health_status": health.get("status"),
            "health_value": health.get("value") or health.get("error"),
            "config_status": config.get("status"),
            "environment": config_value.get("deployment_environment"),
            "test_auth": config_value.get("test_auth"),
            "modern_upload_client_required": config_value.get("modern_upload_client_required"),
            "minimum_upload_version": config_value.get("minimum_upload_version"),
            "catalog_status": catalog.get("status"),
            "catalog_total": catalog_value.get("total"),
        }
        attempts.append(attempt)
        log_path.write_text(json.dumps(attempts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        healthy = health.get("status") == 200 and dict(health.get("value") or {}).get("status") == "ok"
        compatible = (
            config.get("status") == 200
            and config_value.get("deployment_environment") == "production"
            and config_value.get("test_auth") is False
            and config_value.get("modern_upload_client_required") is False
            and config_value.get("minimum_upload_version") == "3.0.81"
        )
        catalog_ready = catalog.get("status") == 200 and isinstance(catalog_value.get("items"), list)
        if healthy and compatible and catalog_ready:
            print(f"[production-deploy] Worker became ready after {len(attempts)} check(s).")
            return attempt
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Production Worker was not ready after {len(attempts)} checks.")
        time.sleep(2)


def deployments(npx: str) -> list[dict]:
    value = json.loads(command_output([npx, "wrangler", "deployments", "list", "--name", WORKER_NAME, "--json"]))
    if not isinstance(value, list) or not value:
        raise RuntimeError("Cloudflare returned no production deployment history.")
    return value


def current_version(values: list[dict]) -> str:
    latest = max(values, key=lambda item: str(item.get("created_on") or ""))
    versions = [item for item in list(latest.get("versions") or []) if float(item.get("percentage") or 0) == 100]
    version = str(versions[0].get("version_id") or "") if len(versions) == 1 else ""
    if not re.fullmatch(r"[0-9a-f-]{36}", version):
        raise RuntimeError("Could not identify the current 100% production Worker version.")
    return version


def deployment_summary(values: list[dict]) -> list[dict]:
    return [
        {
            "deployment_id": item.get("id"),
            "created_on": item.get("created_on"),
            "versions": item.get("versions"),
        }
        for item in values
    ]


def d1_query_rows(npx: str, query: str) -> list[dict]:
    value = json.loads(command_output([
        npx, "wrangler", "d1", "execute", "DB", "--remote", "--config", str(CONFIG),
        "--command", query, "--json",
    ]))
    batches = value if isinstance(value, list) else [value]
    rows: list[dict] = []
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        results = batch.get("results")
        if isinstance(results, list):
            rows.extend(item for item in results if isinstance(item, dict))
    return rows


def remote_table_names(npx: str) -> set[str]:
    return {
        str(row.get("name") or "")
        for row in d1_query_rows(
            npx,
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
        )
        if row.get("name")
    }


def pre_migration_backup_tables(existing_tables: set[str]) -> tuple[str, ...]:
    unexpected_missing_tables = sorted(
        set(AUTHORITATIVE_TABLES) - existing_tables - PENDING_MIGRATION_TABLES
    )
    if unexpected_missing_tables:
        raise RuntimeError(
            "Production D1 is missing required pre-migration tables: "
            + ", ".join(unexpected_missing_tables)
        )
    return tuple(table for table in AUTHORITATIVE_TABLES if table in existing_tables)


def zip_report(report_dir: Path) -> Path:
    target = report_dir.with_suffix(".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in report_dir.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(report_dir.parent))
    return target


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Back up, deploy, validate, and if necessary roll back Community production.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--confirm-production", required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Reports")
    parser.add_argument("--backup-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Backups")
    args = parser.parse_args()
    api = args.api_url.rstrip("/")
    parsed = urllib.parse.urlsplit(api)
    if args.confirm_production != WORKER_NAME:
        raise RuntimeError(f"--confirm-production must exactly equal {WORKER_NAME}.")
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith("/v1") or "staging" in parsed.hostname:
        raise RuntimeError("Production API URL must be HTTPS, end in /v1, and not name staging.")
    check_contract()
    config = load_config(CONFIG)
    if config.get("name") != WORKER_NAME or dict(config.get("vars") or {}).get("DEPLOYMENT_ENVIRONMENT") != "production":
        raise RuntimeError("Production Worker configuration identity is invalid.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.output_dir.resolve() / f"KFPS-Community-Production-Deployment-{timestamp}"
    private_dir = args.backup_dir.resolve() / f"KFPS-Community-Production-{timestamp}"
    report_dir.mkdir(parents=True)
    private_dir.mkdir(parents=True)
    result = 1
    error = ""
    rollback = {"attempted": False, "success": False, "error": ""}
    previous_version = ""
    deployed = False
    backup_path = private_dir / "kfps-community.sql"
    evidence: dict = {
        "schema": "kfps.community-production-deployment.v1",
        "api_url": api,
        "success": False,
    }
    try:
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if not npx:
            raise RuntimeError("npx was not found on the deployment machine.")
        secrets = json.loads(command_output([
            npx, "wrangler", "secret", "list", "--name", WORKER_NAME, "--format", "json",
        ]))
        secret_names = {str(item.get("name") or "") for item in secrets if isinstance(item, dict)}
        if "ADMIN_TOKEN" not in secret_names:
            raise RuntimeError("Production Worker does not retain the required ADMIN_TOKEN secret.")

        before_public = public_json(api + "/config")
        if before_public.get("status") != 200 or dict(before_public.get("value") or {}).get("test_auth") is not False:
            raise RuntimeError("Production public preflight failed or test authentication is enabled.")
        before_deployments = deployments(npx)
        previous_version = current_version(before_deployments)
        evidence["before"] = {
            "worker_version": previous_version,
            "deployments": deployment_summary(before_deployments),
            "public_config": before_public,
        }

        tables_before_migration = remote_table_names(npx)
        backup_tables = pre_migration_backup_tables(tables_before_migration)
        backup_command = [
            npx, "wrangler", "d1", "export", "DB", "--remote", "--config", str(CONFIG),
            "--output", str(backup_path), "--skip-confirmation",
        ]
        for table in backup_tables:
            backup_command.extend(("--table", table))
        run_logged(backup_command, report_dir / "database-backup.log")
        if not backup_path.is_file() or backup_path.stat().st_size < 1024:
            raise RuntimeError("Production D1 backup was not created correctly.")
        backup_sql = backup_path.read_text(encoding="utf-8", errors="strict")
        missing_tables = [
            table for table in backup_tables
            if not re.search(rf"(?im)^CREATE TABLE (?:\"?){re.escape(table)}(?:\"?)\s*\(", backup_sql)
        ]
        if missing_tables:
            raise RuntimeError(f"Production D1 backup omitted required tables: {', '.join(missing_tables)}")
        (private_dir / "RESTORE.txt").write_text(
            "Private authoritative D1 backup. Keep restricted: it contains account and session data.\n"
            "The rebuildable FTS5 artwork_search virtual table and its shadow tables are intentionally excluded "
            "because Cloudflare cannot export databases containing virtual tables. Apply all migrations, import "
            "this SQL, then repopulate artwork_search from the authoritative artwork/user rows before recovery is complete.\n",
            encoding="utf-8",
        )
        evidence["private_database_backup"] = {
            "path": str(backup_path),
            "bytes": backup_path.stat().st_size,
            "sha256": sha256(backup_path),
            "included_in_report": False,
            "authoritative_tables": list(backup_tables),
            "pending_migration_tables": sorted(set(AUTHORITATIVE_TABLES) - set(backup_tables)),
            "excluded_rebuildable_index": "artwork_search (FTS5)",
        }
        inventory = command_output([
            npx, "wrangler", "d1", "execute", "DB", "--remote", "--config", str(CONFIG),
            "--command", "SELECT COUNT(*) AS revisions, COALESCE(SUM(design_bytes),0) AS design_bytes, COALESCE(SUM(preview_bytes),0) AS preview_bytes, COALESCE(SUM(thumbnail_bytes),0) AS thumbnail_bytes FROM artwork_revisions", "--json",
        ])
        (report_dir / "asset-inventory.json").write_text(inventory, encoding="utf-8")

        run_logged([
            npx, "wrangler", "d1", "migrations", "apply", "DB", "--remote", "--config", str(CONFIG),
        ], report_dir / "migration.log")
        missing_after_migration = sorted(set(AUTHORITATIVE_TABLES) - remote_table_names(npx))
        if missing_after_migration:
            raise RuntimeError(
                "Production D1 migrations did not create required tables: "
                + ", ".join(missing_after_migration)
            )
        run_logged([npx, "wrangler", "deploy", "--config", str(CONFIG)], report_dir / "deployment.log")
        deployed = True
        evidence["readiness"] = wait_until_ready(api, report_dir / "readiness.json")

        after_deployments = deployments(npx)
        new_version = current_version(after_deployments)
        if new_version == previous_version:
            raise RuntimeError("Production deployment did not create a new active Worker version.")
        after_secrets = json.loads(command_output([
            npx, "wrangler", "secret", "list", "--name", WORKER_NAME, "--format", "json",
        ]))
        if "ADMIN_TOKEN" not in {str(item.get("name") or "") for item in after_secrets if isinstance(item, dict)}:
            raise RuntimeError("Production ADMIN_TOKEN secret did not survive deployment.")
        evidence["after"] = {
            "worker_version": new_version,
            "deployments": deployment_summary(after_deployments),
            "admin_secret_preserved": True,
        }
        result = 0
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        print(f"[production-deploy] FAILED: {error}", file=sys.stderr)
        if deployed and previous_version:
            rollback["attempted"] = True
            try:
                npx = shutil.which("npx.cmd") or shutil.which("npx")
                if not npx:
                    raise RuntimeError("npx unavailable for automatic rollback.")
                run_logged([
                    npx, "wrangler", "rollback", previous_version, "--name", WORKER_NAME,
                    "--message", "Automatic rollback after failed KFPS production deployment gate", "--yes",
                ], report_dir / "rollback.log")
                rollback["success"] = True
            except Exception as rollback_error:
                rollback["error"] = safe_text(f"{type(rollback_error).__name__}: {rollback_error}")
    finally:
        evidence.update({
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "success": result == 0,
            "exit_code": result,
            "error": safe_text(error),
            "rollback": rollback,
            "source": {
                "git_commit": command_output(["git", "rev-parse", "HEAD"], REPO_ROOT).strip(),
                "git_branch": command_output(["git", "branch", "--show-current"], REPO_ROOT).strip(),
                "kfps_version": (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                "os": platform.platform(),
                "machine": platform.machine(),
            },
        })
        (report_dir / "result.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (report_dir / "README.txt").write_text(
            "Sanitized production deployment evidence. The authoritative D1 backup is stored separately in the ignored "
            "private backup directory and is not included in this report. R2 is inventoried but not mutated by deployment.\n",
            encoding="utf-8",
        )
        archive = zip_report(report_dir)
        print(f"[production-deploy] Report: {archive}")
        if backup_path.is_file():
            print(f"[production-deploy] Private database backup: {backup_path}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"[production-deploy] FAILED before reporting started: {error}", file=sys.stderr)
        raise SystemExit(1)
