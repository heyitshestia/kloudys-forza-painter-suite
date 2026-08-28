from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ROOT = Path(
    os.environ.get(
        "KFPS_COMMUNITY_E2E_RUN_ROOT",
        str(Path(tempfile.gettempdir()) / "kfps-community-e2e"),
    )
).resolve()
WRANGLER_CONFIG = WORKER_ROOT / "wrangler.e2e.jsonc"
SUPPORTER_ISSUER = WORKER_ROOT / "tools" / "test_supporter_token.mjs"
E2E_TEST = REPO_ROOT / "KFPS.UI" / "tests" / "community_e2e.py"
CONTRACT_CHECK = WORKER_ROOT / "tools" / "check_deployment_contract.py"


def command(name: str) -> str:
    candidates = [f"{name}.cmd", name] if os.name == "nt" else [name]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError(f"Required command was not found: {name}")


def run(arguments: list[str], *, cwd: Path = WORKER_ROOT, env: dict[str, str] | None = None) -> None:
    printable = " ".join(arguments)
    print(f"[community-e2e] {printable}", flush=True)
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def run_logged(
    arguments: list[str], log_path: Path, *, cwd: Path = WORKER_ROOT, env: dict[str, str] | None = None,
) -> None:
    printable = " ".join(arguments)
    print(f"[community-e2e] {printable}", flush=True)
    with log_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            output.write(line)
            output.flush()
        return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, arguments)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(url: str, process: subprocess.Popen, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Community Worker exited during startup with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("status") == "ok":
                return
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(0.2)
    raise RuntimeError(f"Community Worker did not become healthy: {last_error}")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def safe_remove(path: Path) -> None:
    resolved_root = RUN_ROOT.resolve()
    resolved = path.resolve()
    if resolved.parent != resolved_root:
        raise RuntimeError(f"Refusing to remove unexpected E2E path: {resolved}")
    if not resolved.exists():
        return
    last_error = None
    for _attempt in range(50):
        try:
            shutil.rmtree(resolved)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.2)
    if last_error is not None:
        raise last_error


def tail(path: Path, lines: int = 80) -> str:
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def copy_sanitized_log(source: Path, destination: Path, secret_values: list[str]) -> None:
    if not source.is_file():
        return
    text = source.read_text(encoding="utf-8", errors="replace")
    for value in secret_values:
        if value:
            text = text.replace(value, "[REDACTED]")
    destination.write_text(text, encoding="utf-8")


def run_once(index: int, *, keep_success: bool, report_dir: Path | None) -> None:
    run_id = f"{os.getpid()}-{index}-{uuid.uuid4().hex[:8]}"
    run_dir = RUN_ROOT / run_id
    state_dir = run_dir / "state"
    run_dir.mkdir(parents=True)
    state_dir.mkdir()
    worker_log = run_dir / "worker.log"
    migration_log = run_dir / "migration.log"
    seed_log = run_dir / "seed.log"
    test_log = run_dir / "e2e-test.log"
    key_path = run_dir / "supporter-test-key.json"
    env_path = run_dir / "community.env"
    app_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    node = command("node")
    npx = command("npx")
    worker = None
    success = False
    started = time.monotonic()
    admin_token = secrets.token_urlsafe(48)
    test_auth_token = secrets.token_urlsafe(48)

    try:
        run([node, str(SUPPORTER_ISSUER), "generate", str(key_path)])
        key = json.loads(key_path.read_text(encoding="utf-8"))
        env_path.write_text(
            "\n".join([
                f"ADMIN_TOKEN={admin_token}",
                "API_PROTOCOL=1",
                "DEPLOYMENT_ENVIRONMENT=local-e2e",
                "ALLOW_TEST_AUTH=1",
                f"TEST_AUTH_TOKEN={test_auth_token}",
                "AUTO_APPROVE_TEST_UPLOADS=1",
                "AUTO_PUBLISH_VALIDATED_UPLOADS=1",
                "GITHUB_CLIENT_ID=",
                f"MINIMUM_UPLOAD_VERSION={app_version}",
                "COMPATIBILITY_MINIMUM_UPLOAD_VERSION=3.0.81",
                "REQUIRE_MODERN_UPLOAD_CLIENT=0",
                "VERSION_SYNC_ENABLED=0",
                "VERSION_REPOSITORY=local/e2e",
                "VERSION_BRANCH=main",
                f"SUPPORTER_ENTITLEMENT_KEY_ID={key['key_id']}",
                f"SUPPORTER_ENTITLEMENT_MODULUS_HEX={key['modulus_hex']}",
                "",
            ]),
            encoding="utf-8",
        )

        process_env = os.environ.copy()
        process_env.update({"CI": "true", "NO_COLOR": "1"})
        run_logged([
            npx, "wrangler", "d1", "migrations", "apply", "DB",
            "--config", str(WRANGLER_CONFIG), "--local", "--persist-to", str(state_dir),
            "--env-file", str(env_path),
        ], migration_log, env=process_env)

        port = free_port()
        inspector_port = free_port()
        log_handle = worker_log.open("w", encoding="utf-8")
        creation_flags = 0
        start_new_session = False
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            )
        else:
            start_new_session = True
        worker = subprocess.Popen(
            [
                npx, "wrangler", "dev", "--config", str(WRANGLER_CONFIG), "--local",
                "--ip", "127.0.0.1", "--port", str(port), "--inspector-port", str(inspector_port),
                "--persist-to", str(state_dir), "--env-file", str(env_path), "--log-level", "info",
            ],
            cwd=WORKER_ROOT,
            env=process_env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            start_new_session=start_new_session,
        )
        api = f"http://127.0.0.1:{port}/v1"
        wait_for_health(f"{api}/health", worker)

        test_env = process_env.copy()
        test_env.update({
            "KFPS_COMMUNITY_API_URL": api,
            "KFPS_APP_VERSION": app_version,
            "KFPS_COMMUNITY_SUPPORTER_ISSUER": str(SUPPORTER_ISSUER),
            "KFPS_COMMUNITY_TEST_SUPPORTER_KEY": str(key_path),
            "KFPS_COMMUNITY_TEST_AUTH_TOKEN": test_auth_token,
            "KFPS_COMMUNITY_EXPECTED_ENVIRONMENT": "local-e2e",
            "KFPS_COMMUNITY_EXPECTED_MINIMUM_UPLOAD_VERSION": "3.0.81",
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONUTF8": "1",
        })
        run_logged(
            [sys.executable, str(WORKER_ROOT / "tools" / "seed_local.py")],
            seed_log,
            cwd=REPO_ROOT,
            env=test_env,
        )
        run_logged([sys.executable, str(E2E_TEST), "-v"], test_log, cwd=REPO_ROOT, env=test_env)
        success = True
        print(f"[community-e2e] Disposable run {index} passed.", flush=True)
    finally:
        if worker is not None:
            stop_process(worker)
        if "log_handle" in locals():
            log_handle.close()
        if report_dir is not None:
            evidence = report_dir / f"run-{index:02d}"
            evidence.mkdir(parents=True, exist_ok=True)
            for source in (migration_log, worker_log, seed_log, test_log):
                copy_sanitized_log(source, evidence / source.name, [admin_token, test_auth_token])
            (evidence / "result.json").write_text(json.dumps({
                "schema": "kfps.community-e2e-run.v1",
                "index": index,
                "success": success,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "app_version": app_version,
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if success and not keep_success:
            safe_remove(run_dir)
        elif not success:
            print(f"[community-e2e] Failure evidence retained at {run_dir}", file=sys.stderr)
            log_tail = tail(worker_log)
            if log_tail:
                print("[community-e2e] Worker log tail:\n" + log_tail, file=sys.stderr)
            test_tail = tail(test_log)
            if test_tail:
                print("[community-e2e] Test log tail:\n" + test_tail, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run KFPS against a disposable local Community Worker.")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of fresh-state E2E runs.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run npm ci when dependencies are absent.")
    parser.add_argument("--skip-worker-checks", action="store_true", help="Skip Worker typecheck and unit tests.")
    parser.add_argument("--keep-success", action="store_true", help="Retain successful disposable state and logs.")
    parser.add_argument("--report-dir", type=Path, help="Copy sanitized logs and per-run results here.")
    return parser.parse_args()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if args.repetitions < 1 or args.repetitions > 20:
        raise SystemExit("--repetitions must be between 1 and 20")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    report_dir = args.report_dir.resolve() if args.report_dir else None
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(CONTRACT_CHECK)], cwd=REPO_ROOT)
    npm = command("npm")
    if not (WORKER_ROOT / "node_modules" / ".bin" / ("wrangler.cmd" if os.name == "nt" else "wrangler")).exists():
        if args.skip_install:
            raise RuntimeError("Worker dependencies are missing and --skip-install was requested.")
        run([npm, "ci"])
    if not args.skip_worker_checks:
        run([npm, "run", "typecheck"])
        run([npm, "test"])
    for index in range(1, args.repetitions + 1):
        run_once(index, keep_success=args.keep_success, report_dir=report_dir)
    print(f"[community-e2e] {args.repetitions} clean disposable run(s) passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[community-e2e] FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
