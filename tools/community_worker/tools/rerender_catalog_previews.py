#!/usr/bin/env python3
"""Regenerate Community preview assets with the current KFPS renderer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_API_URL = "https://kfps-community-library.hestia-cummings.workers.dev/v1"
MAX_JSON_BYTES = 24 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class MaintenanceError(RuntimeError):
    pass


def _secret_from_file(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MaintenanceError(f"Could not read the admin token file: {path}") from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "ADMIN_TOKEN":
            token = value.strip().strip('"').strip("'")
            if len(token) >= 32:
                return token
    raise MaintenanceError(f"ADMIN_TOKEN is missing or too short in {path}")


def _safe_api_url(value: str) -> str:
    url = value.rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise MaintenanceError("The maintenance API must use HTTPS unless it is localhost.")
    if not parsed.netloc or not parsed.path.endswith("/v1"):
        raise MaintenanceError("The maintenance API URL must end in /v1.")
    return url


def _request(
    api_url: str,
    token: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    maximum: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes, dict[str, str]]:
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": "KFPS-Community-Preview-Maintenance/1",
        "X-Community-Admin-Token": token,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{api_url}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > maximum:
                raise MaintenanceError(f"Worker response exceeded {maximum} bytes.")
            raw = response.read(maximum + 1)
            if len(raw) > maximum:
                raise MaintenanceError(f"Worker response exceeded {maximum} bytes.")
            return raw, {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read(64 * 1024)
        try:
            body = json.loads(raw.decode("utf-8"))
            message = str(body.get("message") or body.get("error") or exc.reason)
        except Exception:
            message = str(exc.reason)
        raise MaintenanceError(f"Worker returned HTTP {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise MaintenanceError(f"Could not reach the Community Worker: {exc.reason}") from exc


def _json_request(api_url: str, token: str, path: str, **kwargs) -> dict:
    raw, _headers = _request(api_url, token, path, **kwargs)
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise MaintenanceError("Worker returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise MaintenanceError("Worker returned an unexpected response.")
    return value


def _find_kfps_root(explicit: str, script_root: Path) -> Path:
    candidates = [Path(explicit)] if explicit else [
        script_root / "KFPS CLEAN",
        script_root / "KFPS DIRTY",
    ]
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "json_preview_renderer.py").is_file() and (root / "KFPS.UI" / "src" / "kfps_ui").is_dir():
            return root
    raise MaintenanceError("Could not find a KFPS root containing the shared preview renderer.")


def _load_inspector(kfps_root: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(kfps_root))
    sys.path.insert(0, str(kfps_root / "KFPS.UI" / "src"))
    try:
        from kfps_ui.community_validation import inspect_upload
    except Exception as exc:
        raise MaintenanceError(
            "Could not load KFPS preview dependencies. Run this script with the selected KFPS Python runtime."
        ) from exc
    return inspect_upload


def _artwork_ids(values: list[str]) -> set[str]:
    selected = {value.strip() for value in values if value.strip()}
    if any("/" in value or "\\" in value or len(value) > 64 for value in selected):
        raise MaintenanceError("An artwork ID contains unsupported characters.")
    return selected


def _design_uses_masks(value: object) -> bool:
    if isinstance(value, list):
        shapes = value
    elif isinstance(value, dict):
        shapes = next((value.get(key) for key in ("shapes", "layers", "items") if isinstance(value.get(key), list)), [])
    else:
        shapes = []
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        explicit_mask = False
        for key in ("mask", "is_mask", "isMask"):
            if key in shape:
                explicit_mask = True
                if bool(shape.get(key)):
                    return True
                break
        if explicit_mask:
            continue
        data = shape.get("data")
        if isinstance(data, list) and len(data) > 6:
            try:
                if bool(int(float(data[6]))):
                    return True
            except (TypeError, ValueError):
                if bool(data[6]):
                    return True
    return False


def run(args: argparse.Namespace) -> int:
    script_root = Path(__file__).resolve().parents[2]
    api_url = _safe_api_url(args.api_url)
    token = os.environ.get("KFPS_COMMUNITY_ADMIN_TOKEN", "").strip() or _secret_from_file(Path(args.token_file))
    kfps_root = _find_kfps_root(args.kfps_root, script_root)
    inspect_upload = _load_inspector(kfps_root)
    renderer_version = (kfps_root / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    selected_ids = _artwork_ids(args.artwork_id)
    queue = _json_request(api_url, token, f"/admin/rerender?status={urllib.parse.quote(args.status)}")
    items = [item for item in queue.get("items", []) if isinstance(item, dict)]
    if selected_ids:
        items = [item for item in items if str(item.get("id") or "") in selected_ids]
        missing = selected_ids - {str(item.get("id") or "") for item in items}
        if missing:
            raise MaintenanceError(f"Artwork IDs were not found in the selected status: {', '.join(sorted(missing))}")
    if args.limit:
        items = items[: args.limit]

    print(f"Renderer: KFPS {renderer_version} from {kfps_root}")
    print(f"Catalog: {len(items)} artwork(s), status={args.status}, dry_run={args.dry_run}")
    changed = 0
    unchanged = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="kfps-community-rerender-") as temporary:
        workspace = Path(temporary)
        for position, item in enumerate(items, 1):
            artwork_id = str(item.get("id") or "")
            title = str(item.get("title") or artwork_id)
            revision = int(item.get("current_revision") or 0)
            content_hash = str(item.get("content_hash") or "").lower()
            label = f"[{position}/{len(items)}] {title} ({artwork_id})"
            try:
                encoded_id = urllib.parse.quote(artwork_id, safe="")
                design, headers = _request(
                    api_url,
                    token,
                    f"/admin/artworks/{encoded_id}/design",
                    maximum=MAX_JSON_BYTES,
                )
                actual_content_hash = hashlib.sha256(design).hexdigest()
                if actual_content_hash != content_hash or headers.get("x-content-sha256", "").lower() != content_hash:
                    raise MaintenanceError("Stored design hash does not match the catalog record.")
                if int(headers.get("x-artwork-revision", "0")) != revision:
                    raise MaintenanceError("Stored design revision changed during the maintenance run.")
                try:
                    uses_masks = _design_uses_masks(json.loads(design.decode("utf-8")))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise MaintenanceError("Stored design is not valid UTF-8 JSON.") from exc
                source = workspace / f"{position:04d}-{artwork_id}.json"
                source.write_bytes(design)
                inspection = inspect_upload(source, workspace / "runtime")
                preview_hash = hashlib.sha256(inspection.preview_bytes).hexdigest()
                thumbnail_hash = hashlib.sha256(inspection.thumbnail_bytes).hexdigest()
                assets_same = (
                    preview_hash == str(item.get("preview_hash") or "").lower()
                    and thumbnail_hash == str(item.get("thumbnail_hash") or "").lower()
                )
                masks_same = uses_masks == bool(item.get("uses_masks"))
                if assets_same and masks_same:
                    unchanged += 1
                    print(f"{label}: unchanged")
                    continue
                changed += 1
                if args.dry_run:
                    operation = "update mask metadata" if assets_same else "replace preview and thumbnail"
                    print(f"{label}: would {operation}")
                    continue
                result = _json_request(
                    api_url,
                    token,
                    f"/admin/artworks/{encoded_id}/rendered-assets",
                    method="POST",
                    payload={
                        "expected_revision": revision,
                        "expected_content_sha256": content_hash,
                        "renderer_version": renderer_version,
                        "uses_masks": uses_masks,
                        "preview_base64": base64.b64encode(inspection.preview_bytes).decode("ascii"),
                        "thumbnail_base64": base64.b64encode(inspection.thumbnail_bytes).decode("ascii"),
                    },
                )
                if str(result.get("preview_sha256") or "") != preview_hash:
                    raise MaintenanceError("Worker confirmed an unexpected preview hash.")
                if bool(result.get("uses_masks")) != uses_masks:
                    raise MaintenanceError("Worker confirmed unexpected mask metadata.")
                print(f"{label}: {'updated mask metadata' if assets_same else 'replaced'}")
            except Exception as exc:
                failed += 1
                print(f"{label}: FAILED: {exc}", file=sys.stderr)

    print(f"Summary: changed={changed}, unchanged={unchanged}, failed={failed}")
    return 1 if failed else 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    worker_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("KFPS_COMMUNITY_API_URL", DEFAULT_API_URL))
    parser.add_argument("--token-file", default=str(worker_root / ".deploy.secrets"))
    parser.add_argument("--kfps-root", default="")
    parser.add_argument("--status", choices=("published", "pending", "rejected", "removed", "all"), default="published")
    parser.add_argument("--artwork-id", action="append", default=[], help="Limit the run to one artwork ID; repeat as needed.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit cannot be negative")
    try:
        return run(args)
    except MaintenanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
