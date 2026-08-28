from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
RUNNER = WORKER_ROOT / "tools" / "run_kfps_e2e.py"


def command_result(arguments: list[str], timeout: int = 20) -> dict:
    executable = shutil.which(arguments[0]) or arguments[0]
    try:
        result = subprocess.run(
            [executable, *arguments[1:]], capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", check=False,
        )
        return {
            "path": executable,
            "exit_code": result.returncode,
            "output": (result.stdout or result.stderr).strip()[:4000],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"path": executable, "error": str(error)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_service_state() -> dict:
    endpoint = os.environ.get("KFPS_COMMUNITY_API_URL", "").strip()
    if not endpoint:
        try:
            endpoint = (REPO_ROOT / "data" / "community_api_url.txt").read_text(encoding="utf-8").strip()
        except OSError:
            endpoint = ""
    result: dict = {"endpoint": endpoint}
    if not endpoint:
        result["error"] = "No packaged Community endpoint was found."
        return result
    for name in ("health", "config"):
        try:
            request = urllib.request.Request(
                endpoint.rstrip("/") + "/" + name,
                headers={"Accept": "application/json", "User-Agent": "KFPS-Community-Diagnostics/1"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                value = json.loads(response.read(256 * 1024).decode("utf-8"))
                if name == "config" and isinstance(value, dict):
                    value = {
                        key: value.get(key) for key in (
                            "protocol", "deployment_environment", "minimum_upload_version",
                            "modern_upload_client_required", "test_auth", "version_sync",
                        )
                    }
                result[name] = {"status": response.status, "value": value}
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            result[name] = {"error": str(error)}
    return result


def windows_hardware() -> dict:
    if os.name != "nt":
        return {}
    script = (
        "$cpu=(Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name);"
        "$gpu=(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM);"
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "@{cpu=$cpu;gpu=$gpu;os_caption=$os.Caption;os_version=$os.Version;"
        "os_build=$os.BuildNumber;ram_bytes=[int64]$os.TotalVisibleMemorySize*1024}"
        "|ConvertTo-Json -Depth 4 -Compress"
    )
    result = command_result(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)
    try:
        return json.loads(str(result.get("output") or "{}"))
    except json.JSONDecodeError:
        return {"collection_error": result}


def collect_system_info() -> dict:
    files = {}
    for relative in (
        "VERSION", "KFPS.exe", "requirements.lock.txt",
        "tools/community_worker/package-lock.json", "tools/community_worker/wrangler.e2e.jsonc",
    ):
        path = REPO_ROOT / relative
        if path.is_file():
            files[relative] = {"size": path.stat().st_size, "sha256": sha256(path)}
    disk = shutil.disk_usage(REPO_ROOT)
    return {
        "schema": "kfps.community-test-diagnostics.v1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "kfps_version": (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "python": {"executable": sys.executable, "version": sys.version, "architecture": platform.architecture()[0]},
        "node": command_result(["node", "--version"]),
        "npm": command_result(["npm", "--version"]),
        "npx": command_result(["npx", "--version"]),
        "platform": {
            "system": platform.system(), "release": platform.release(), "version": platform.version(),
            "machine": platform.machine(), "processor": platform.processor(),
            "locale": locale.getlocale(), "timezone": time.tzname,
        },
        "windows_hardware": windows_hardware(),
        "disk": {"total": disk.total, "free": disk.free},
        "files": files,
        "community_service": public_service_state(),
    }


def tee_process(arguments: list[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            arguments, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return process.wait()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run and package complete Community validation diagnostics.")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    reports_root = REPO_ROOT / "Community-Test-Reports"
    report_dir = reports_root / f"KFPS-Community-Validation-{timestamp}"
    report_dir.mkdir(parents=True)
    info = collect_system_info()
    (report_dir / "system-info.json").write_text(
        json.dumps(info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("KFPS Community validation")
    print(f"KFPS: {info['kfps_version']}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Node: {info['node'].get('output') or info['node'].get('error')}")
    print(f"Windows: {info['windows_hardware'].get('os_caption', platform.platform())}")
    print(f"Reports: {report_dir}")
    print()
    try:
        result = tee_process([
            sys.executable, str(RUNNER), "--repetitions", str(args.repetitions),
            "--report-dir", str(report_dir / "runs"),
        ], report_dir / "validation-console.log")
    except Exception as error:
        result = 1
        message = f"Diagnostic launcher error: {type(error).__name__}: {error}"
        print(message, file=sys.stderr)
        (report_dir / "launcher-error.txt").write_text(message + "\n", encoding="utf-8")
    outcome = {
        "schema": "kfps.community-test-result.v1",
        "success": result == 0,
        "exit_code": result,
        "repetitions": args.repetitions,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (report_dir / "result.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (report_dir / "README.txt").write_text(
        "This archive contains sanitized KFPS Community validation logs and system details.\n"
        "It does not contain Community sessions, supporter keys, admin tokens, or Worker database state.\n",
        encoding="utf-8",
    )
    zip_path = reports_root / f"KFPS-Community-Validation-{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in report_dir.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(report_dir.parent))
    print()
    print(f"Diagnostic ZIP: {zip_path}")
    print("RESULT: PASS" if result == 0 else "RESULT: FAIL")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Community validation launcher FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
