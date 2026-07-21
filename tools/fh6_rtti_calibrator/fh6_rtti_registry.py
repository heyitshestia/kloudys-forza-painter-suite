from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


REGISTRY_FORMAT = "kfps_fh6_rtti_registry_v1"
DEFAULT_REPOSITORY = "heyitshestia/kloudys-forza-painter-suite"
DEFAULT_BRANCH = "main"
DEFAULT_REGISTRY_PATH = "RTTI.dat"
DEFAULT_GITHUB_REMOTE_URL = (
    "https://raw.githubusercontent.com/"
    f"{DEFAULT_REPOSITORY}/{DEFAULT_BRANCH}/{DEFAULT_REGISTRY_PATH}"
)
DEFAULT_RELAY_REMOTE_URL = "https://kfps-fh6-rtti-registry.hestia-cummings.workers.dev/v1/RTTI.dat"
DEFAULT_REMOTE_URL = DEFAULT_RELAY_REMOTE_URL

EXPECTED_CALIBRATION_COUNTS = (3000, 2997, 2994, 2991, 2988, 2985)
MAX_REGISTRY_BYTES = 128 * 1024
MAX_PROFILES = 64
MAX_UPDATE_CODE_BYTES = 128
MIN_MODULE_SIZE = 1024 * 1024
MAX_MODULE_SIZE = 1024 * 1024 * 1024
REMOTE_CACHE_TTL_SECONDS = 15 * 60
REMOTE_FAILURE_TTL_SECONDS = 60


class RegistryError(ValueError):
    pass


class PublishError(RuntimeError):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise RegistryError(f"{label} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return int(text, 0)
            except ValueError:
                pass
    raise RegistryError(f"{label} must be an integer")


def _bounded_text(value: Any, label: str, maximum: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise RegistryError(f"{label} is required")
    if len(text) > maximum:
        raise RegistryError(f"{label} is too long")
    return text


def _normalize_update_code(value: Any) -> str:
    text = _bounded_text(value, "update_code", MAX_UPDATE_CODE_BYTES, required=True)
    try:
        encoded = text.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise RegistryError("update_code must be ASCII") from exc
    if not encoded or len(encoded) > MAX_UPDATE_CODE_BYTES:
        raise RegistryError("update_code has an invalid length")
    if any(byte < 0x21 or byte > 0x7E for byte in encoded):
        raise RegistryError("update_code contains unsupported characters")
    return text


def _profile_identity(profile: dict[str, Any]) -> str:
    identity = {
        "game": "fh6",
        "module_size": profile["module_size"],
        "descriptor_offset": profile["descriptor_offset"],
        "vtable_offsets": profile["vtable_offsets"],
        "update_code": profile["update_code"],
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()[:20]
    return f"fh6-{digest}"


def normalize_profile(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RegistryError("profile must be an object")

    game = _bounded_text(raw.get("game", "fh6"), "game", 16, required=True).lower()
    if game != "fh6":
        raise RegistryError("only FH6 profiles are supported")

    module_size = _parse_int(raw.get("module_size"), "module_size")
    if not MIN_MODULE_SIZE <= module_size <= MAX_MODULE_SIZE:
        raise RegistryError("module_size is outside the supported range")

    descriptor_offset = _parse_int(raw.get("descriptor_offset"), "descriptor_offset")
    if not 0 < descriptor_offset < module_size:
        raise RegistryError("descriptor_offset must be inside the main module")

    raw_vtables = raw.get("vtable_offsets")
    if not isinstance(raw_vtables, list) or not raw_vtables:
        raise RegistryError("vtable_offsets must contain at least one offset")
    if len(raw_vtables) > 16:
        raise RegistryError("vtable_offsets contains too many offsets")
    vtable_offsets = sorted({_parse_int(value, "vtable_offset") for value in raw_vtables})
    if any(offset <= 0 or offset >= module_size for offset in vtable_offsets):
        raise RegistryError("every vtable offset must be inside the main module")

    base_class_count = _parse_int(raw.get("base_class_count", 0), "base_class_count")
    if not 0 <= base_class_count <= 64:
        raise RegistryError("base_class_count is outside the supported range")

    evidence_raw = raw.get("evidence") or {}
    if not isinstance(evidence_raw, dict):
        raise RegistryError("evidence must be an object")
    raw_counts = evidence_raw.get("distinct_counts") or []
    if not isinstance(raw_counts, list) or len(raw_counts) > 32:
        raise RegistryError("evidence distinct_counts is invalid")
    counts = sorted({_parse_int(value, "evidence count") for value in raw_counts}, reverse=True)
    if any(count < 0 or count > 3000 for count in counts):
        raise RegistryError("evidence contains an invalid FH6 layer count")
    scan_count = _parse_int(evidence_raw.get("scan_count", len(counts)), "evidence scan_count")
    if scan_count < len(counts) or scan_count > 256:
        raise RegistryError("evidence scan_count is invalid")

    confidence = _bounded_text(
        evidence_raw.get("confidence", "unknown"), "evidence confidence", 32, required=True
    ).lower()
    if confidence not in {"unknown", "legacy", "medium", "high", "very_high"}:
        raise RegistryError("evidence confidence is unsupported")

    profile = {
        "game": "fh6",
        "module_size": module_size,
        "descriptor_offset": descriptor_offset,
        "vtable_offsets": vtable_offsets,
        "update_code": _normalize_update_code(raw.get("update_code")),
        "base_class_count": base_class_count,
        "game_build": _bounded_text(raw.get("game_build"), "game_build", 64),
        "created_utc": _bounded_text(raw.get("created_utc"), "created_utc", 40),
        "calibrator_version": _bounded_text(raw.get("calibrator_version"), "calibrator_version", 32),
        "evidence": {
            "workflow": _bounded_text(evidence_raw.get("workflow"), "evidence workflow", 64),
            "confidence": confidence,
            "scan_count": scan_count,
            "distinct_counts": counts,
        },
    }
    profile["profile_id"] = _profile_identity(profile)
    return profile


def empty_registry() -> dict[str, Any]:
    return {"format": REGISTRY_FORMAT, "updated_utc": utc_now(), "profiles": []}


def normalize_registry(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RegistryError("registry must be an object")
    if raw.get("format") != REGISTRY_FORMAT:
        raise RegistryError("registry format is unsupported")
    raw_profiles = raw.get("profiles")
    if not isinstance(raw_profiles, list):
        raise RegistryError("registry profiles must be an array")
    if len(raw_profiles) > MAX_PROFILES:
        raise RegistryError("registry contains too many profiles")

    profiles = []
    seen = set()
    for raw_profile in raw_profiles:
        profile = normalize_profile(raw_profile)
        if profile["profile_id"] in seen:
            continue
        seen.add(profile["profile_id"])
        profiles.append(profile)
    return {
        "format": REGISTRY_FORMAT,
        "updated_utc": _bounded_text(raw.get("updated_utc"), "updated_utc", 40),
        "profiles": profiles,
    }


def registry_with_profile(registry: Any, raw_profile: Any) -> dict[str, Any]:
    current = normalize_registry(registry)
    profile = normalize_profile(raw_profile)
    profiles = [profile]
    profiles.extend(item for item in current["profiles"] if item["profile_id"] != profile["profile_id"])
    return {
        "format": REGISTRY_FORMAT,
        "updated_utc": utc_now(),
        "profiles": profiles[:MAX_PROFILES],
    }


def registry_bytes(registry: Any) -> bytes:
    normalized = normalize_registry(registry)
    return (json.dumps(normalized, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def parse_registry_bytes(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_REGISTRY_BYTES:
        raise RegistryError("registry exceeds the maximum size")
    try:
        raw = json.loads(data.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("registry is not valid UTF-8 JSON") from exc
    return normalize_registry(raw)


def load_registry_file(path: Path) -> dict[str, Any]:
    return parse_registry_bytes(Path(path).read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def write_registry_file(path: Path, registry: Any) -> None:
    _atomic_write(Path(path), registry_bytes(registry))


def _parse_game_build(result: dict[str, Any]) -> str:
    process = result.get("process") or {}
    module = result.get("module") or {}
    for value in (module.get("path"), process.get("exe")):
        match = re.search(r"_(\d+\.\d+\.\d+\.\d+)_x64__", str(value or ""), re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def profile_from_calibration_result(result: Any, *, require_complete: bool = True) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RegistryError("calibration result must be an object")
    if result.get("format") != "kfps_clivery_rtti_calibration_v1":
        raise RegistryError("calibration result format is unsupported")

    module = result.get("module") or {}
    rtti = result.get("rtti") or {}
    summary = result.get("lock_summary") or {}
    workflow = result.get("workflow") or {}
    if not isinstance(module, dict) or not isinstance(rtti, dict):
        raise RegistryError("calibration result is missing module or RTTI data")

    module_base = _parse_int(module.get("base"), "module base")
    module_size = _parse_int(module.get("size"), "module size")
    descriptor_offset = rtti.get("descriptor_offset")
    if descriptor_offset is None:
        descriptor_offset = _parse_int(rtti.get("descriptor_address"), "descriptor address") - module_base
    descriptor_offset = _parse_int(descriptor_offset, "descriptor offset")

    raw_vtables = rtti.get("vtables") or []
    if not isinstance(raw_vtables, list):
        raise RegistryError("calibration vtables must be an array")
    vtable_offsets = []
    for raw_vtable in raw_vtables:
        value = _parse_int(raw_vtable, "calibration vtable")
        vtable_offsets.append(value - module_base if value >= module_base else value)

    update_code = (
        rtti.get("hierarchy_update_code")
        or rtti.get("direct_type_name")
        or rtti.get("type_name")
    )
    counts = sorted({_parse_int(value, "calibration count") for value in summary.get("distinct_counts") or []}, reverse=True)
    confidence = str(rtti.get("confidence") or "unknown").strip().lower()
    completed_step = _parse_int(workflow.get("completed_step", 0), "workflow completed_step")
    workflow_name = str(workflow.get("name") or "").strip()

    if require_complete:
        if workflow_name != "six_step_template_calibration":
            raise RegistryError("only the six-step calibration workflow can be published")
        if completed_step < len(EXPECTED_CALIBRATION_COUNTS):
            raise RegistryError("all six calibration scans must complete before publication")
        if counts != list(EXPECTED_CALIBRATION_COUNTS):
            raise RegistryError("the calibration result does not contain all six target counts")
        if confidence not in {"high", "very_high"}:
            raise RegistryError("the calibration result is not high confidence")

    profile = {
        "game": "fh6",
        "module_size": module_size,
        "descriptor_offset": descriptor_offset,
        "vtable_offsets": vtable_offsets,
        "update_code": update_code,
        "base_class_count": rtti.get("base_class_count", 0),
        "game_build": _parse_game_build(result),
        "created_utc": result.get("created_utc") or utc_now(),
        "calibrator_version": result.get("calibrator_version") or "",
        "evidence": {
            "workflow": workflow_name,
            "confidence": confidence,
            "scan_count": summary.get("scans", len(counts)),
            "distinct_counts": counts,
        },
    }
    return normalize_profile(profile)


def _read_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    data = (json.dumps(state, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    _atomic_write(Path(path), data)


def _try_write_state(path: Path, state: dict[str, Any]) -> None:
    try:
        _write_state(path, state)
    except OSError:
        pass


def download_registry(
    url: str,
    *,
    timeout: float = 2.5,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not str(url).lower().startswith("https://"):
        raise RegistryError("remote registry URL must use HTTPS")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "KFPS-RTTI-Updater/1",
        },
    )
    with opener(request, timeout=timeout) as response:
        data = response.read(MAX_REGISTRY_BYTES + 1)
    return parse_registry_bytes(data)


def refresh_registry_cache(
    cache_path: Path,
    *,
    remote_url: str = DEFAULT_REMOTE_URL,
    state_path: Path | None = None,
    now: float | None = None,
    force: bool = False,
    success_ttl: int = REMOTE_CACHE_TTL_SECONDS,
    failure_ttl: int = REMOTE_FAILURE_TTL_SECONDS,
    downloader: Callable[[str], dict[str, Any]] | None = None,
    fallback_urls: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    cache_path = Path(cache_path)
    state_path = Path(state_path or cache_path.with_suffix(cache_path.suffix + ".state.json"))
    now = float(time.time() if now is None else now)
    state = _read_state(state_path)
    last_attempt = float(state.get("last_attempt_epoch") or 0)
    previous_primary = str(state.get("primary_source") or "")
    previous_source = str(state.get("source") or "")
    primary_unchanged = previous_primary == remote_url
    primary_succeeded = state.get("last_result") == "ok" and previous_source == remote_url
    cooldown = success_ttl if primary_succeeded else failure_ttl
    if not force and primary_unchanged and last_attempt and now - last_attempt < cooldown:
        return {"attempted": False, "updated": False, "result": "throttled", "error": ""}

    if fallback_urls is None:
        fallback_urls = (DEFAULT_GITHUB_REMOTE_URL,) if remote_url == DEFAULT_RELAY_REMOTE_URL else ()
    source_urls = [remote_url]
    source_urls.extend(url for url in fallback_urls if url and url not in source_urls)
    registry = None
    source_url = remote_url
    errors = []
    for candidate_url in source_urls:
        try:
            registry = downloader(candidate_url) if downloader else download_registry(candidate_url)
            source_url = candidate_url
            break
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    try:
        if registry is None:
            raise RegistryError("; ".join(errors) or "all remote registry sources failed")
        write_registry_file(cache_path, registry)
        _try_write_state(
            state_path,
            {
                "last_attempt_epoch": now,
                "last_success_epoch": now,
                "last_result": "ok",
                "source": source_url,
                "primary_source": remote_url,
            },
        )
        return {
            "attempted": True,
            "updated": True,
            "result": "ok",
            "error": "",
            "source": source_url,
            "profile_count": len(registry["profiles"]),
        }
    except Exception as exc:
        _try_write_state(
            state_path,
            {
                "last_attempt_epoch": now,
                "last_success_epoch": state.get("last_success_epoch", 0),
                "last_result": "error",
                "source": remote_url,
                "primary_source": remote_url,
                "error": f"{type(exc).__name__}: {exc}"[:240],
            },
        )
        return {
            "attempted": True,
            "updated": False,
            "result": "error",
            "error": f"{type(exc).__name__}: {exc}"[:240],
        }


def _truthy_environment(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_profiles(
    root: Path,
    fallback_profile: Any,
    *,
    refresh: bool = True,
    remote_url: str | None = None,
    downloader: Callable[[str], dict[str, Any]] | None = None,
    now: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(root)
    cache_path = root / "runtime" / "fh6-rtti" / DEFAULT_REGISTRY_PATH
    local_path = root / DEFAULT_REGISTRY_PATH
    update_url = remote_url or os.environ.get("KFPS_RTTI_UPDATE_URL", "").strip() or DEFAULT_REMOTE_URL
    disabled = _truthy_environment("KFPS_DISABLE_RTTI_UPDATE")
    force = _truthy_environment("KFPS_FORCE_RTTI_UPDATE")

    refresh_status = {"attempted": False, "updated": False, "result": "disabled" if disabled else "not_requested", "error": ""}
    if refresh and not disabled:
        refresh_status = refresh_registry_cache(
            cache_path,
            remote_url=update_url,
            now=now,
            force=force,
            downloader=downloader,
        )

    profiles = []
    seen = set()
    load_errors = []
    for source, path in (("remote_cache", cache_path), ("packaged", local_path)):
        if not path.is_file():
            continue
        try:
            registry = load_registry_file(path)
        except Exception as exc:
            load_errors.append(f"{source}: {type(exc).__name__}")
            continue
        for item in registry["profiles"]:
            if item["profile_id"] in seen:
                continue
            seen.add(item["profile_id"])
            profile = dict(item)
            profile["_registry_source"] = source
            profiles.append(profile)

    fallback = normalize_profile(fallback_profile)
    if fallback["profile_id"] not in seen:
        fallback["_registry_source"] = "built_in"
        profiles.append(fallback)

    return profiles, {
        "refresh": refresh_status,
        "load_errors": load_errors,
        "profile_count": len(profiles),
        "cache_path": str(cache_path),
    }


def _run_command(
    command: list[str],
    *,
    input_text: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> Any:
    return runner(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def github_publish_readiness(
    gh_executable: str = "gh",
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[bool, str]:
    executable = shutil.which(gh_executable) if not Path(gh_executable).is_file() else gh_executable
    if not executable:
        return False, "GitHub CLI is not installed or is not on PATH"
    result = _run_command([str(executable), "auth", "status", "--hostname", "github.com"], runner=runner)
    if result.returncode != 0:
        return False, "GitHub CLI is not authenticated"
    return True, str(executable)


def _github_file_endpoint(repository: str, path: str, branch: str) -> str:
    safe_repository = _bounded_text(repository, "repository", 200, required=True)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", safe_repository):
        raise PublishError("repository must use owner/name format")
    safe_path = "/".join(urllib.parse.quote(part, safe="") for part in Path(path).as_posix().split("/"))
    return f"repos/{safe_repository}/contents/{safe_path}?ref={urllib.parse.quote(branch, safe='')}"


def _read_github_registry(executable: str, endpoint: str, runner: Callable[..., Any]) -> tuple[dict[str, Any], str]:
    get_result = _run_command([executable, "api", endpoint], runner=runner)
    if get_result.returncode == 0:
        try:
            remote_file = json.loads(get_result.stdout)
            remote_sha = str(remote_file.get("sha") or "")
            remote_data = base64.b64decode(str(remote_file.get("content") or ""), validate=False)
            return parse_registry_bytes(remote_data), remote_sha
        except Exception as exc:
            raise PublishError(f"existing remote registry could not be read: {exc}") from exc
    if "HTTP 404" in f"{get_result.stdout}\n{get_result.stderr}":
        return empty_registry(), ""
    detail = (get_result.stderr or get_result.stdout or "GitHub API request failed").strip()
    raise PublishError(detail[:400])


def publish_profile_to_github(
    raw_profile: Any,
    *,
    repository: str = DEFAULT_REPOSITORY,
    branch: str = DEFAULT_BRANCH,
    path: str = DEFAULT_REGISTRY_PATH,
    gh_executable: str = "gh",
    runner: Callable[..., Any] = subprocess.run,
    existing_registry: Any | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    profile = normalize_profile(raw_profile)
    ready, executable_or_reason = github_publish_readiness(gh_executable, runner=runner)
    if not ready and existing_registry is None:
        raise PublishError(executable_or_reason)
    executable = executable_or_reason if ready else gh_executable
    endpoint = _github_file_endpoint(repository, path, branch)
    attempts = 1 if existing_registry is not None else 2
    for attempt in range(attempts):
        if existing_registry is None:
            current, remote_sha = _read_github_registry(executable, endpoint, runner)
        else:
            current, remote_sha = normalize_registry(existing_registry), ""

        merged = registry_with_profile(current, profile)
        data = registry_bytes(merged)
        if dry_run:
            return {
                "published": False,
                "dry_run": True,
                "profile_id": profile["profile_id"],
                "registry": merged,
                "data": data,
            }

        payload = {
            "message": f"Update FH6 locator profile {profile['profile_id']}",
            "branch": branch,
            "content": base64.b64encode(data).decode("ascii"),
        }
        if remote_sha:
            payload["sha"] = remote_sha
        put_endpoint = endpoint.split("?", 1)[0]
        put_result = _run_command(
            [executable, "api", "--method", "PUT", put_endpoint, "--input", "-"],
            input_text=json.dumps(payload, separators=(",", ":")),
            runner=runner,
        )
        if put_result.returncode == 0:
            try:
                response = json.loads(put_result.stdout)
            except json.JSONDecodeError as exc:
                raise PublishError("GitHub returned an unreadable publication response") from exc
            return {
                "published": True,
                "dry_run": False,
                "profile_id": profile["profile_id"],
                "commit_url": str((response.get("commit") or {}).get("html_url") or ""),
                "registry": merged,
            }

        detail = (put_result.stderr or put_result.stdout or "GitHub API update failed").strip()
        conflict = any(marker in detail.lower() for marker in ("http 409", "does not match", "sha", "conflict"))
        if conflict and attempt + 1 < attempts:
            continue
        raise PublishError(detail[:400])
    raise PublishError("GitHub publication did not complete")
