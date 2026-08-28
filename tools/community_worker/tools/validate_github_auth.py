from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
USER_AGENT = "KFPS-Community-GitHub-Validation/1"


def request_json(url: str, method: str = "GET", payload: dict | None = None, token: str = "") -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(256 * 1024)
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read(256 * 1024).decode("utf-8", errors="replace")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {"error": "non_json_http_error", "body_excerpt": raw[:1000]}
        return error.code, value


def request_bytes(url: str, token: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(32 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        return error.code, error.read(256 * 1024)


def github_device_handshake(client_id: str) -> tuple[dict, list[str]]:
    body = urllib.parse.urlencode({"client_id": client_id}).encode("ascii")
    request = urllib.request.Request(
        "https://github.com/login/device/code", data=body, method="POST",
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.loads(response.read(64 * 1024).decode("utf-8"))
    device_code = str(value.get("device_code") or "")
    user_code = str(value.get("user_code") or "")
    verification_uri = str(value.get("verification_uri") or "")
    if not device_code or not user_code or verification_uri != "https://github.com/login/device":
        raise RuntimeError("GitHub did not accept the configured device-flow application.")
    return {
        "accepted": True,
        "verification_uri": verification_uri,
        "expires_in_seconds": int(value.get("expires_in") or 0),
        "poll_interval_seconds": int(value.get("interval") or 0),
    }, [device_code, user_code]


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
    parser = argparse.ArgumentParser(description="Validate real GitHub authentication without preserving credentials.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--expected-environment", choices=("staging", "production"), required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Community-Deployment-Reports")
    args = parser.parse_args()
    api = args.api_url.rstrip("/")
    parsed = urllib.parse.urlsplit(api)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith("/v1"):
        raise RuntimeError("API URL must be HTTPS and end in /v1.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.output_dir.resolve() / f"KFPS-Community-GitHub-Auth-{args.expected_environment}-{timestamp}"
    report_dir.mkdir(parents=True)
    result = 1
    error = ""
    secrets: list[str] = []
    evidence: dict = {
        "schema": "kfps.community-github-auth-validation.v1",
        "completed_at_utc": "",
        "environment": args.expected_environment,
        "api_url": api,
        "success": False,
    }
    community_token = ""
    try:
        status, config = request_json(api + "/config")
        if status != 200 or config.get("deployment_environment") != args.expected_environment:
            raise RuntimeError("Community endpoint environment did not match the requested validation target.")
        client_id = str(config.get("github_client_id") or "")
        if not client_id:
            raise RuntimeError("Community endpoint does not publish a GitHub application ID.")
        evidence["device_flow"], device_secrets = github_device_handshake(client_id)
        secrets.extend(device_secrets)

        gh = shutil.which("gh.exe") or shutil.which("gh")
        if not gh:
            raise RuntimeError("GitHub CLI was not found on the deployment machine.")
        token_result = subprocess.run(
            [gh, "auth", "token"], check=True, capture_output=True,
            text=True, encoding="utf-8", errors="strict", timeout=30,
        )
        github_token = token_result.stdout.strip()
        if not 20 <= len(github_token) <= 512:
            raise RuntimeError("GitHub CLI did not return a usable credential.")
        secrets.append(github_token)

        status, auth = request_json(api + "/auth/github", "POST", {"access_token": github_token})
        community_token = str(auth.get("token") or "")
        if status != 200 or not community_token:
            raise RuntimeError(f"Community Worker rejected real GitHub authentication with HTTP {status}.")
        secrets.append(community_token)
        status, session = request_json(api + "/session", token=community_token)
        user = dict(session.get("user") or {})
        if status != 200 or user.get("provider") != "github":
            raise RuntimeError("Community session did not resolve to the GitHub provider.")
        evidence["session"] = {
            "created": True,
            "provider": "github",
            "username_configured": bool(user.get("username")),
        }
        status, catalog = request_json(api + "/artworks?limit=24&sort=name", token=community_token)
        items = [item for item in list(catalog.get("items") or []) if not bool(dict(item).get("supporter_only"))]
        if status != 200 or not items:
            raise RuntimeError("Authenticated public catalog smoke did not return a downloadable artwork.")
        artwork = dict(items[0])
        download_path = str(artwork.get("download_url") or "")
        expected_hash = str(artwork.get("content_sha256") or "")
        if not download_path.startswith("/v1/") or len(expected_hash) != 64:
            raise RuntimeError("Published artwork did not declare a valid download contract.")
        status, design = request_bytes(urllib.parse.urljoin(api + "/", download_path), community_token)
        actual_hash = hashlib.sha256(design).hexdigest()
        if status != 200 or actual_hash != expected_hash:
            raise RuntimeError("Authenticated artwork download did not match its published SHA-256.")
        evidence["catalog_download"] = {
            "catalog_available": True,
            "download_bytes": len(design),
            "sha256_verified": True,
        }
        if args.expected_environment == "production":
            status, _ = request_json(api + "/auth/test", "POST", {
                "installation_id": "production-validation-disabled",
                "display_name": "Production validation",
            })
            if status != 404:
                raise RuntimeError(f"Production test authentication returned HTTP {status} instead of 404.")
            evidence["production_test_auth_disabled"] = True
        status, _ = request_json(api + "/session", "DELETE", token=community_token)
        if status != 200:
            raise RuntimeError(f"Community sign-out failed with HTTP {status}.")
        evidence["session"]["signed_out"] = True
        result = 0
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        print(f"[github-auth] FAILED: {error}", file=sys.stderr)
    finally:
        evidence.update({
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "success": result == 0,
            "exit_code": result,
            "error": error,
        })
        report_path = report_dir / "result.json"
        report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        serialized = report_path.read_text(encoding="utf-8")
        if any(secret and secret in serialized for secret in secrets):
            result = 1
            evidence.update(success=False, exit_code=1, error="Report redaction verification failed.")
            report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (report_dir / "README.txt").write_text(
            "GitHub device-application and Community session validation. No device code, GitHub token, "
            "Community token, account identifier, or private credential is stored.\n",
            encoding="utf-8",
        )
        archive = zip_report(report_dir)
        print(f"[github-auth] Report: {archive}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"[github-auth] FAILED before reporting started: {error}", file=sys.stderr)
        raise SystemExit(1)
