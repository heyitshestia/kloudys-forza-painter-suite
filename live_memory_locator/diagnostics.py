from __future__ import annotations

import csv
import io
import json
import os
import platform
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import psutil

from .contracts import (
    DIAGNOSTIC_SCHEMA,
    ENGINE_VERSION,
    LocatorRequest,
    LocatorSelection,
    REPORT_INDEX_SCHEMA,
    parse_address,
)


_USER_PATH = re.compile(r"(?i)([a-z]:\\users\\)[^\\/]+")
_REPORT_COMPONENT = re.compile(r"[^a-z0-9-]+")
_REPORT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def runtime_identity(root: str | Path) -> dict[str, str]:
    root = Path(root)

    def read_text(name: str) -> str:
        try:
            return (root / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    return {"kfps_version": read_text("VERSION"), "build_commit": read_text("BUILD_COMMIT")}


def scrub_user_path(value: object) -> str:
    return _USER_PATH.sub(r"\1<user>", str(value or ""))


def scrub_payload_paths(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): scrub_payload_paths(child) for key, child in value.items()}
    if isinstance(value, list):
        return [scrub_payload_paths(child) for child in value]
    if isinstance(value, tuple):
        return [scrub_payload_paths(child) for child in value]
    if isinstance(value, str):
        return scrub_user_path(value)
    return value


def infer_store_variant(process: Mapping[str, Any]) -> str:
    name = str(process.get("name") or "").casefold()
    executable = str(process.get("executable") or "").replace("/", "\\").casefold()
    if "steamworks" in name or "\\steamapps\\" in executable:
        return "steam"
    if (
        "\\windowsapps\\" in executable
        or "\\packages\\" in executable
        or "\\xboxgames\\" in executable
    ):
        return "microsoft_xbox"
    return "unknown"


def _windows_registry_gpu_snapshot() -> list[dict[str, str]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    discovered: dict[tuple[str, str], dict[str, str]] = {}
    root_path = r"SYSTEM\CurrentControlSet\Control\Video"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
    except OSError:
        return []
    try:
        guid_index = 0
        while True:
            try:
                guid = winreg.EnumKey(root, guid_index)
            except OSError:
                break
            guid_index += 1
            try:
                guid_key = winreg.OpenKey(root, guid)
            except OSError:
                continue
            try:
                adapter_index = 0
                while True:
                    try:
                        adapter_key_name = winreg.EnumKey(guid_key, adapter_index)
                    except OSError:
                        break
                    adapter_index += 1
                    if not adapter_key_name.isdigit():
                        continue
                    try:
                        adapter_key = winreg.OpenKey(guid_key, adapter_key_name)
                    except OSError:
                        continue
                    try:
                        name = ""
                        for field in ("AdapterString", "DriverDesc"):
                            try:
                                name = str(winreg.QueryValueEx(adapter_key, field)[0] or "").strip()
                            except OSError:
                                continue
                            if name:
                                break
                        try:
                            driver = str(
                                winreg.QueryValueEx(adapter_key, "DriverVersion")[0] or ""
                            ).strip()
                        except OSError:
                            driver = ""
                        if name:
                            discovered[(name.casefold(), driver)] = {
                                "name": name,
                                "driver_version": driver,
                                "source": "registry_fallback",
                            }
                    finally:
                        winreg.CloseKey(adapter_key)
            finally:
                winreg.CloseKey(guid_key)
    finally:
        winreg.CloseKey(root)
    return sorted(discovered.values(), key=lambda item: item["name"].casefold())


@lru_cache(maxsize=1)
def _windows_gpu_snapshot() -> list[dict[str, str]]:
    if os.name != "nt":
        return []
    system_root = Path(os.environ.get("SystemRoot") or r"C:\Windows")
    wmic = system_root / "System32" / "wbem" / "WMIC.exe"
    if wmic.is_file():
        try:
            completed = subprocess.run(
                [
                    str(wmic),
                    "path",
                    "Win32_VideoController",
                    "get",
                    "Name,DriverVersion",
                    "/format:csv",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is not None and completed.returncode == 0:
            discovered: dict[tuple[str, str], dict[str, str]] = {}
            for row in csv.DictReader(io.StringIO(completed.stdout.lstrip())):
                name = str(row.get("Name") or "").strip()
                driver = str(row.get("DriverVersion") or "").strip()
                if name:
                    discovered[(name.casefold(), driver)] = {
                        "name": name,
                        "driver_version": driver,
                        "source": "active_video_controller",
                    }
            if discovered:
                return sorted(
                    discovered.values(), key=lambda item: item["name"].casefold()
                )

    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if powershell.is_file():
        script = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
            "@(Get-CimInstance Win32_VideoController | "
            "Select-Object Name,DriverVersion) | ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                [
                    str(powershell),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is not None and completed.returncode == 0:
            try:
                rows = json.loads(completed.stdout.lstrip("\ufeff\r\n "))
            except (TypeError, ValueError):
                rows = []
            if isinstance(rows, Mapping):
                rows = [rows]
            discovered = {}
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, Mapping):
                    continue
                name = str(row.get("Name") or "").strip()
                driver = str(row.get("DriverVersion") or "").strip()
                if name:
                    discovered[(name.casefold(), driver)] = {
                        "name": name,
                        "driver_version": driver,
                        "source": "active_video_controller",
                    }
            if discovered:
                return sorted(
                    discovered.values(), key=lambda item: item["name"].casefold()
                )
    return _windows_registry_gpu_snapshot()


def environment_snapshot(process: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_bytes": int(psutil.virtual_memory().total),
        "gpus": _windows_gpu_snapshot(),
        "store_variant": infer_store_variant(process),
    }


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _canonical_game(report: Mapping[str, Any]) -> str:
    profile = report.get("profile_match")
    request = report.get("request")
    game = profile.get("game") if isinstance(profile, Mapping) else ""
    if not game and isinstance(request, Mapping):
        game = request.get("game")
    return str(game or "unknown").strip().lower()


def _report_record(report: Mapping[str, Any], relative_path: str) -> dict[str, Any]:
    request = report.get("request") if isinstance(report.get("request"), Mapping) else {}
    outcome = report.get("outcome") if isinstance(report.get("outcome"), Mapping) else {}
    environment = (
        report.get("environment") if isinstance(report.get("environment"), Mapping) else {}
    )
    return {
        "diagnostic_id": str(report.get("diagnostic_id") or ""),
        "created_utc": str(report.get("created_utc") or ""),
        "created": float(report.get("created") or 0.0),
        "game": _canonical_game(report),
        "purpose": str(request.get("purpose") or "diagnostic"),
        "layer_count": int(request.get("layer_count") or 0),
        "status": str(outcome.get("status") or "error"),
        "store_variant": str(environment.get("store_variant") or "unknown"),
        "process": str(report.get("process") or ""),
        "path": relative_path.replace("\\", "/"),
    }


def _report_sort_key(item: Mapping[str, Any]) -> tuple[float, str]:
    try:
        created = float(item.get("created") or 0.0)
    except (TypeError, ValueError):
        created = 0.0
    return created, str(item.get("diagnostic_id") or "")


def _report_time(value: object) -> tuple[str, str]:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    except ValueError:
        parsed = datetime.now(timezone.utc).replace(microsecond=0)
    created_utc = parsed.isoformat().replace("+00:00", "Z")
    return created_utc, parsed.strftime("%Y%m%dT%H%M%SZ")


def _indexed_report_path(reports_root: Path, relative: object) -> Path:
    candidate = PurePosixPath(str(relative or "").replace("\\", "/"))
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 2
        or not _REPORT_DATE.fullmatch(candidate.parts[0])
        or candidate.parts[1] in {"", ".", ".."}
        or candidate.suffix.casefold() != ".json"
    ):
        raise ValueError(f"invalid archived locator report path: {relative}")
    path = (reports_root / candidate.parts[0] / candidate.parts[1]).resolve()
    if not path.is_relative_to(reports_root.resolve()):
        raise ValueError(f"archived locator report escaped its report root: {relative}")
    return path


def _load_or_rebuild_report_index(reports_root: Path) -> dict[str, Any]:
    index_path = reports_root / "index.json"
    try:
        value = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    if isinstance(value, dict) and value.get("schema") == REPORT_INDEX_SCHEMA:
        indexed_reports = value.get("reports")
        try:
            valid_index = isinstance(indexed_reports, list) and all(
                isinstance(item, Mapping)
                and _indexed_report_path(reports_root, item.get("path")).is_file()
                for item in indexed_reports
            )
        except ValueError:
            valid_index = False
        if valid_index:
            value.setdefault("latest_by_game_purpose", {})
            return value

    records = []
    for path in sorted(reports_root.glob("????-??-??/*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(report, dict) or report.get("schema") != DIAGNOSTIC_SCHEMA:
            continue
        records.append(_report_record(report, path.relative_to(reports_root).as_posix()))
    records.sort(key=_report_sort_key, reverse=True)
    latest_by_operation: dict[str, str] = {}
    for record in records:
        key = f"{record['game']}:{record['purpose']}"
        latest_by_operation.setdefault(key, record["path"])
    return {
        "schema": REPORT_INDEX_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "updated_utc": utc_now(),
        "latest": records[0]["path"] if records else "",
        "latest_by_game_purpose": latest_by_operation,
        "reports": records,
    }


def persist_diagnostic(
    root: str | Path,
    output_path: str | Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(root).resolve()
    report = scrub_payload_paths(dict(payload))
    process = (
        report.get("process_identity")
        if isinstance(report.get("process_identity"), Mapping)
        else {}
    )
    if not isinstance(report.get("environment"), Mapping):
        report["environment"] = environment_snapshot(process)
    report.setdefault("store_variant", infer_store_variant(process))
    request = report.get("request") if isinstance(report.get("request"), Mapping) else {}
    outcome = report.get("outcome") if isinstance(report.get("outcome"), Mapping) else {}
    created_utc, stamp = _report_time(report.get("created_utc"))
    report["created_utc"] = created_utc
    date = created_utc[:10]
    game = _REPORT_COMPONENT.sub("-", _canonical_game(report)).strip("-") or "unknown"
    purpose = _REPORT_COMPONENT.sub(
        "-", str(request.get("purpose") or "diagnostic").lower()
    ).strip("-")
    status = _REPORT_COMPONENT.sub(
        "-", str(outcome.get("status") or "error").lower()
    ).strip("-")
    count = int(request.get("layer_count") or 0)
    diagnostic_id = _REPORT_COMPONENT.sub(
        "-", str(report.get("diagnostic_id") or uuid.uuid4().hex).lower()
    ).strip("-")
    if not diagnostic_id:
        diagnostic_id = uuid.uuid4().hex
    report["diagnostic_id"] = diagnostic_id
    filename = f"{stamp}-{game}-{purpose}-{count}-{status}-{diagnostic_id[:12]}.json"
    reports_root = root / "runtime" / "live-memory" / "reports"
    archive_path = reports_root / date / filename
    latest_path = reports_root / "latest.json"
    operation_latest_path = reports_root / "latest" / f"{game}-{purpose}.json"
    index_path = reports_root / "index.json"
    archive_metadata = {
        "archive_path": archive_path.relative_to(root).as_posix(),
        "index_path": index_path.relative_to(root).as_posix(),
        "latest_path": latest_path.relative_to(root).as_posix(),
        "operation_latest_path": operation_latest_path.relative_to(root).as_posix(),
    }
    report["report_archive"] = archive_metadata
    atomic_write_json(output_path, report)

    try:
        atomic_write_json(archive_path, report)
        index = _load_or_rebuild_report_index(reports_root)
        relative_path = archive_path.relative_to(reports_root).as_posix()
        record = _report_record(report, relative_path)
        records = []
        for item in index.get("reports") or []:
            if not isinstance(item, Mapping) or item.get("diagnostic_id") == diagnostic_id:
                continue
            normalized = dict(item)
            if not normalized.get("path") or not normalized.get("game"):
                continue
            records.append(normalized)
        records.append(record)
        records.sort(key=_report_sort_key, reverse=True)
        latest_by_operation: dict[str, str] = {}
        for item in records:
            key = f"{item.get('game', 'unknown')}:{item.get('purpose', 'diagnostic')}"
            latest_by_operation.setdefault(key, str(item.get("path") or ""))
        index.update(
            {
                "schema": REPORT_INDEX_SCHEMA,
                "engine_version": ENGINE_VERSION,
                "updated_utc": utc_now(),
                "latest": records[0]["path"] if records else "",
                "latest_by_game_purpose": latest_by_operation,
                "reports": records,
            }
        )
        atomic_write_json(index_path, index)

        def archived_report(relative: str) -> dict[str, Any]:
            if relative == relative_path:
                return report
            value = json.loads(
                _indexed_report_path(reports_root, relative).read_text(encoding="utf-8")
            )
            if not isinstance(value, dict) or value.get("schema") != DIAGNOSTIC_SCHEMA:
                raise ValueError(f"archived locator report is invalid: {relative}")
            return value

        if index.get("latest"):
            atomic_write_json(latest_path, archived_report(str(index["latest"])))
        operation_key = f"{game}:{purpose}"
        operation_latest = latest_by_operation.get(operation_key)
        if operation_latest:
            atomic_write_json(
                operation_latest_path,
                archived_report(str(operation_latest)),
            )
    except (OSError, TypeError, ValueError) as exc:
        report["report_archive"] = {**archive_metadata, "write_error": str(exc)}
        atomic_write_json(output_path, report)
    return report


def build_diagnostic(
    *,
    request: LocatorRequest,
    root: str | Path,
    process: Mapping[str, Any],
    profile: Mapping[str, Any],
    status: str,
    reason: str,
    authoritative: bool,
    attempts: list[Mapping[str, Any]],
    selection: LocatorSelection | None,
    cache: Mapping[str, Any] | None = None,
    backend_diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status = str(status)
    selected = selection.as_dict() if selection else None
    payload: dict[str, Any] = {
        "schema": DIAGNOSTIC_SCHEMA,
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "diagnostic_id": uuid.uuid4().hex,
        "created_utc": utc_now(),
        "type": "kfps_live_memory_locator_session_v1",
        "request": request.as_dict(),
        "process_identity": dict(process),
        "environment": environment_snapshot(process),
        "profile_match": dict(profile),
        "outcome": {
            "status": status,
            "reason": str(reason or ""),
            "authoritative": bool(authoritative),
        },
        "attempts": [dict(item) for item in attempts],
        "selected": selected,
        "cache": dict(cache or {}),
        "backend_diagnostics": dict(backend_diagnostics or {}),
        "pid": request.pid,
        "process": str(process.get("name") or ""),
        "store_variant": infer_store_variant(process),
        "game": request.game,
        "layer_count": request.layer_count,
        "purpose": request.purpose,
        "created": time.time(),
        **runtime_identity(root),
        "refused": status == "refused",
        "no_match": status == "no_match",
        "authoritative_no_match": status == "no_match" and bool(authoritative),
        "failure_reason": str(reason or "") if status in {"no_match", "error"} else "",
        "refusal_reason": str(reason or "") if status == "refused" else "",
    }
    if selected:
        payload.update({key: value for key, value in selected.items() if key != "details"})
        details = selected.get("details") or {}
        payload.update(
            {
                "score": details.get("score"),
                "samples": details.get("samples") or [],
                "shape_word_counts": details.get("shape_word_counts") or {},
                "group_graph": details.get("group_graph"),
                "vtable": details.get("vtable"),
                "rtti_source": details.get("rtti_source"),
                "rtti_profile_id": details.get("rtti_profile_id"),
                "rtti_update_code": details.get("rtti_update_code"),
                "rtti_descriptor_offset": details.get("rtti_descriptor_offset"),
            }
        )
    return scrub_payload_paths(payload)


def wrap_backend_payload(
    payload: Mapping[str, Any],
    *,
    root: str | Path,
    purpose: str = "diagnostic",
) -> dict[str, Any]:
    """Add the canonical envelope to a direct low-level probe report."""
    if payload.get("schema") == DIAGNOSTIC_SCHEMA:
        return dict(payload)
    selected = payload.get("selected")
    if not isinstance(selected, Mapping) and payload.get("group_address") and payload.get("table_address"):
        selected = {
            key: payload.get(key)
            for key in (
                "group_address",
                "table_address",
                "count_address",
                "table_pointer_field",
                "locator",
                "validated_entries",
                "vector_count",
                "capacity_count",
                "import_group_address",
                "import_count_address",
                "import_table_pointer_field",
                "import_table_address",
                "import_vector_count",
                "import_capacity_count",
                "import_target_verified",
                "export_access_verified",
                "flattened_from_groups",
            )
        }
    status = "located" if isinstance(selected, Mapping) else "no_match"
    reason = ""
    if payload.get("refused") is True:
        status = "refused"
        reason = str(payload.get("refusal_reason") or "live vinyl was refused")
    elif payload.get("no_match") is True:
        status = "no_match"
        reason = str(payload.get("failure_reason") or "no live vinyl group matched")
    elif status == "no_match":
        reason = "The low-level scanner did not produce an engine-validated selection."
    request = {
        "game": str(payload.get("game") or "fh6"),
        "pid": int(payload.get("pid") or 0),
        "layer_count": int(payload.get("layer_count") or payload.get("count") or 0),
        "purpose": purpose,
    }
    wrapped = dict(payload)
    wrapped.update(
        {
            "schema": DIAGNOSTIC_SCHEMA,
            "schema_version": 1,
            "engine_version": ENGINE_VERSION,
            "diagnostic_id": str(payload.get("diagnostic_id") or uuid.uuid4().hex),
            "created_utc": str(payload.get("created_utc") or utc_now()),
            "request": request,
            "outcome": {
                "status": status,
                "reason": reason,
                "authoritative": bool(payload.get("authoritative_no_match")),
            },
            "attempts": list(payload.get("attempts") or []),
            "selected": dict(selected) if isinstance(selected, Mapping) else None,
            **runtime_identity(root),
        }
    )
    return wrapped


def write_backend_diagnostic(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    root: str | Path,
    purpose: str = "diagnostic",
) -> Path:
    return atomic_write_json(path, wrap_backend_payload(payload, root=root, purpose=purpose))


def read_diagnostic(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != DIAGNOSTIC_SCHEMA:
        raise ValueError("locator report does not use the supported diagnostic schema")
    outcome = value.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("status") not in {
        "located",
        "refused",
        "no_match",
        "error",
    }:
        raise ValueError("locator report has an invalid outcome")
    request = value.get("request")
    if not isinstance(request, dict):
        raise ValueError("locator report has no request identity")
    try:
        if int(request.get("pid") or 0) <= 0:
            raise ValueError
        if not 0 < int(request.get("layer_count") or 0) <= 3000:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("locator report has an invalid request identity") from None
    if str(request.get("purpose") or "") not in {"import", "export", "diagnostic"}:
        raise ValueError("locator report has an invalid request purpose")
    if outcome.get("status") == "located":
        selected = value.get("selected")
        if not isinstance(selected, dict):
            raise ValueError("located locator report has no selected group")
        try:
            parse_address(selected.get("group_address"))
            parse_address(selected.get("table_address"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"located locator report has invalid selected addresses: {exc}") from None
        requested_count = int(request["layer_count"])
        if int(selected.get("validated_entries") or 0) != requested_count:
            raise ValueError("located locator report does not validate the exact requested layer count")
        flattened = selected.get("flattened_from_groups") is True
        vector_count = selected.get("vector_count")
        capacity_count = selected.get("capacity_count")
        if not flattened and int(vector_count or -1) != requested_count:
            raise ValueError("located locator report has a mismatched vector count")
        required_capacity = int(vector_count or 0) if flattened else requested_count
        if int(capacity_count or -1) < required_capacity:
            raise ValueError("located locator report has insufficient vector capacity")
        if request.get("purpose") == "import":
            try:
                parse_address(selected.get("import_group_address"))
                parse_address(selected.get("import_table_address"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"located import report has invalid selected import addresses: {exc}"
                ) from None
            if selected.get("import_target_verified") is not True:
                raise ValueError("located import report has no verified import target")
            if int(selected.get("import_vector_count") or -1) != requested_count:
                raise ValueError("located import report has a mismatched import vector count")
            if int(selected.get("import_capacity_count") or -1) < requested_count:
                raise ValueError("located import report has insufficient import capacity")
    return value
