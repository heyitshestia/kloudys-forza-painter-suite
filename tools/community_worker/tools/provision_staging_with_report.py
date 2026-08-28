from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
PREPARE = WORKER_ROOT / "tools" / "prepare_staging.py"


def run(arguments: list[str], log_path: Path) -> str:
    print(f"[staging-provision] {' '.join(arguments)}", flush=True)
    environment = os.environ.copy()
    environment.update({"CI": "true", "NO_COLOR": "1", "PYTHONUTF8": "1"})
    process = subprocess.run(
        arguments, cwd=WORKER_ROOT, env=environment, check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    combined = (process.stdout or "") + (process.stderr or "")
    log_path.write_text(combined, encoding="utf-8")
    print(combined, end="", flush=True)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, arguments)
    return combined


def bucket_names(output: str) -> set[str]:
    return {
        line.split(":", 1)[1].strip()
        for line in output.splitlines() if line.strip().startswith("name:")
    }


def databases(npx: str, log_path: Path) -> list[dict]:
    output = run([npx, "wrangler", "d1", "list", "--json"], log_path)
    value = json.loads(output)
    if not isinstance(value, list):
        raise RuntimeError("Cloudflare returned an invalid D1 inventory.")
    return [item for item in value if isinstance(item, dict)]


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
    parser = argparse.ArgumentParser(description="Provision isolated Community staging with recovery evidence.")
    parser.add_argument("--database-name", default="kfps-community-staging")
    parser.add_argument("--bucket-name", default="kfps-community-assets-staging")
    parser.add_argument("--worker-name", default="kfps-community-library-staging")
    parser.add_argument("--location", default="weur", choices=("weur", "eeur", "apac", "wnam", "enam", "oc"))
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Reports")
    args = parser.parse_args()
    names = (args.database_name.strip(), args.bucket_name.strip(), args.worker_name.strip())
    if not all(names) or not all("staging" in name.lower() for name in names):
        raise RuntimeError("Every resource name must be non-empty and contain 'staging'.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.output_dir.resolve() / f"KFPS-Community-Staging-Provision-{timestamp}"
    report_dir.mkdir(parents=True)
    result = 1
    error = ""
    database_id = ""
    bucket_created = False
    try:
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if not npx:
            raise RuntimeError("npx was not found on the deployment machine.")
        before = databases(npx, report_dir / "d1-before.json")
        if any(str(item.get("name")) == args.database_name for item in before):
            raise RuntimeError(f"D1 database already exists: {args.database_name}")
        bucket_before = run([npx, "wrangler", "r2", "bucket", "list"], report_dir / "r2-before.log")
        if args.bucket_name in bucket_names(bucket_before):
            raise RuntimeError(f"R2 bucket already exists: {args.bucket_name}")

        run([
            npx, "wrangler", "d1", "create", args.database_name,
            "--location", args.location,
        ], report_dir / "d1-create.log")
        after = databases(npx, report_dir / "d1-after.json")
        matches = [item for item in after if str(item.get("name")) == args.database_name]
        if len(matches) != 1:
            raise RuntimeError("Created staging D1 database could not be identified uniquely.")
        database_id = str(matches[0].get("uuid") or "")

        run([
            npx, "wrangler", "r2", "bucket", "create", args.bucket_name,
            "--location", args.location,
        ], report_dir / "r2-create.log")
        bucket_after = run([npx, "wrangler", "r2", "bucket", "list"], report_dir / "r2-after.log")
        bucket_created = args.bucket_name in bucket_names(bucket_after)
        if not bucket_created:
            raise RuntimeError("Created staging R2 bucket did not appear in the inventory.")

        run([
            sys.executable, str(PREPARE), "--database-id", database_id,
            "--database-name", args.database_name, "--bucket-name", args.bucket_name,
            "--worker-name", args.worker_name, "--force",
        ], report_dir / "prepare.log")
        result = 0
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        print(f"[staging-provision] FAILED: {error}", file=sys.stderr)
    finally:
        evidence = {
            "schema": "kfps.community-staging-provision.v1",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "success": result == 0,
            "exit_code": result,
            "error": error,
            "database_name": args.database_name,
            "database_id": database_id,
            "bucket_name": args.bucket_name,
            "bucket_confirmed": bucket_created,
            "worker_name": args.worker_name,
            "location": args.location,
        }
        (report_dir / "result.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        (report_dir / "README.txt").write_text(
            "Staging provisioning evidence. Private staging keys and tokens are not included.\n"
            "A failed partial run is never automatically deleted; inspect result.json before recovery.\n",
            encoding="utf-8",
        )
        secret_values: list[str] = []
        for path in (WORKER_ROOT / ".staging" / "deploy.secrets", WORKER_ROOT / ".staging" / "test.env"):
            if path.is_file():
                secret_values.extend(
                    line.split("=", 1)[1].strip().strip('"')
                    for line in path.read_text(encoding="utf-8").splitlines() if "=" in line
                )
        serialized = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in report_dir.rglob("*") if path.is_file()
        )
        if any(secret and secret in serialized for secret in secret_values):
            result = 1
            evidence.update(success=False, exit_code=1, error="Report redaction verification failed.")
            (report_dir / "result.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            )
        archive = zip_report(report_dir)
        print(f"[staging-provision] Report: {archive}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[staging-provision] FAILED before reporting started: {error}", file=sys.stderr)
        raise SystemExit(1)
