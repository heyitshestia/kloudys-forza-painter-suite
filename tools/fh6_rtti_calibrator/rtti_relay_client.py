from __future__ import annotations

import ctypes
import hashlib
import json
import os
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Protocol

from fh6_rtti_registry import EXPECTED_CALIBRATION_COUNTS, RegistryError, normalize_profile


DEFAULT_RELAY_URL = "https://kfps-fh6-rtti-registry.hestia-cummings.workers.dev"
DEFAULT_ENROLLMENT_FILE = "rtti-enrollment.json"
MAX_RESPONSE_BYTES = 64 * 1024


class RelayError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect()).open


class DataProtector(Protocol):
    def protect(self, value: bytes) -> bytes: ...
    def unprotect(self, value: bytes) -> bytes: ...


class DpapiProtector:
    _entropy = b"KFPS-FH6-RTTI-RELAY-V1"
    _forbid_ui = 0x1

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    @classmethod
    def _input_blob(cls, value: bytes):
        if not value:
            return cls._Blob(0, None), None
        buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        return cls._Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer

    @staticmethod
    def _apis():
        if os.name != "nt":
            raise RelayError("Windows protected storage is unavailable on this operating system.")
        try:
            crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except Exception as exc:
            raise RelayError("Windows protected storage is unavailable.") from exc
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DpapiProtector._Blob), wintypes.LPCWSTR,
            ctypes.POINTER(DpapiProtector._Blob), wintypes.LPVOID, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(DpapiProtector._Blob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DpapiProtector._Blob), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DpapiProtector._Blob), wintypes.LPVOID, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(DpapiProtector._Blob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        return crypt32, kernel32

    @staticmethod
    def _output(blob, kernel32) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData) if blob.cbData else b""
        finally:
            if blob.pbData:
                kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))

    def protect(self, value: bytes) -> bytes:
        crypt32, kernel32 = self._apis()
        source, source_buffer = self._input_blob(value)
        entropy, entropy_buffer = self._input_blob(self._entropy)
        output = self._Blob()
        if not crypt32.CryptProtectData(
            ctypes.byref(source), "KFPS FH6 RTTI helper credential", ctypes.byref(entropy),
            None, None, self._forbid_ui, ctypes.byref(output),
        ):
            raise RelayError(f"Windows could not protect the helper credential (error {ctypes.get_last_error()}).")
        return self._output(output, kernel32)

    def unprotect(self, value: bytes) -> bytes:
        crypt32, kernel32 = self._apis()
        source, source_buffer = self._input_blob(value)
        entropy, entropy_buffer = self._input_blob(self._entropy)
        output = self._Blob()
        description = wintypes.LPWSTR()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(source), ctypes.byref(description), ctypes.byref(entropy),
            None, None, self._forbid_ui, ctypes.byref(output),
        ):
            raise RelayError(
                "The helper credential cannot be opened by this Windows account on this machine "
                f"(error {ctypes.get_last_error()})."
            )
        try:
            return self._output(output, kernel32)
        finally:
            if description:
                kernel32.LocalFree(ctypes.cast(description, wintypes.HLOCAL))


class PlaintextTestProtector:
    def protect(self, value: bytes) -> bytes:
        return b"KFPS-RTTI-TEST\0" + value

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(b"KFPS-RTTI-TEST\0"):
            raise RelayError("Invalid test-protected helper state.")
        return value[len(b"KFPS-RTTI-TEST\0") :]


def normalize_relay_url(value: str) -> str:
    endpoint = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise RelayError("The RTTI relay URL is invalid.")
    local = parsed.hostname.lower() in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local:
        raise RelayError("The production RTTI relay URL must use HTTPS.")
    if parsed.query or parsed.fragment or (parsed.path and parsed.path != "/"):
        raise RelayError("The RTTI relay URL must not include a path, query, or fragment.")
    return endpoint


def default_state_root() -> Path:
    override = os.environ.get("KFPS_RTTI_RELAY_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "KFPS" / "fh6-rtti-calibrator"


def portable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_enrollment_path() -> Path:
    return portable_root() / DEFAULT_ENROLLMENT_FILE


def _atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="kfps-rtti-", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temp = Path(name)
    try:
        temp.write_bytes(value)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


class RelayStateStore:
    def __init__(self, root: Path | None = None, protector: DataProtector | None = None):
        self.root = Path(root) if root is not None else default_state_root()
        self.path = self.root / "relay-state.dat"
        self.protector = protector or DpapiProtector()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema": "kfps.rtti.relay-state.v1", "device_secret": secrets.token_hex(32)}
        try:
            raw = self.protector.unprotect(self.path.read_bytes())
            value = json.loads(raw.decode("utf-8"))
        except RelayError:
            raise
        except Exception as exc:
            raise RelayError("The protected RTTI helper state is damaged.") from exc
        if not isinstance(value, dict) or value.get("schema") != "kfps.rtti.relay-state.v1":
            raise RelayError("The protected RTTI helper state has an unsupported format.")
        if not isinstance(value.get("device_secret"), str) or not re_full_hex(value["device_secret"], 64):
            raise RelayError("The protected RTTI helper identity is damaged.")
        return value

    def save(self, value: dict[str, Any]) -> None:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        _atomic_write(self.path, self.protector.protect(raw))

    def load_or_create(self) -> dict[str, Any]:
        value = self.load()
        if not self.path.is_file():
            self.save(value)
        return value


def re_full_hex(value: str, length: int) -> bool:
    return len(value) == length and all(character in "0123456789abcdef" for character in value)


def device_id_from_state(state: dict[str, Any]) -> str:
    secret = bytes.fromhex(str(state["device_secret"]))
    return hashlib.sha256(b"KFPS-FH6-RTTI-HELPER-V1\0" + secret).hexdigest()


def _read_json_response(response) -> dict[str, Any]:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise RelayError("The RTTI relay returned an oversized response.")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RelayError("The RTTI relay returned an invalid response.") from exc
    if not isinstance(value, dict):
        raise RelayError("The RTTI relay returned an invalid response.")
    return value


def _request_json(
    endpoint: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    credential: str = "",
    timeout: float = 10.0,
    opener: Callable[..., Any] = _NO_REDIRECT_OPENER,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "KFPS-FH6-RTTI-Calibrator/3"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    request = urllib.request.Request(
        normalize_relay_url(endpoint) + path,
        data=data,
        headers=headers,
        method="GET" if body is None else "POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            return _read_json_response(response)
    except urllib.error.HTTPError as exc:
        try:
            error = _read_json_response(exc).get("error")
        except RelayError:
            error = None
        raise RelayError(str(error or f"RTTI relay request failed with HTTP {exc.code}.")) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RelayError(f"Could not reach the RTTI relay: {exc}") from exc


def _strict_profile(raw_profile: Any) -> dict[str, Any]:
    try:
        profile = normalize_profile(raw_profile)
    except RegistryError as exc:
        raise RelayError(str(exc)) from exc
    evidence = profile.get("evidence") or {}
    if evidence.get("workflow") != "six_step_template_calibration":
        raise RelayError("Only a completed six-step calibration can be published.")
    if evidence.get("confidence") not in {"high", "very_high"}:
        raise RelayError("The calibration profile is not high confidence.")
    if int(evidence.get("scan_count") or 0) < 6:
        raise RelayError("The calibration profile does not contain six independent scans.")
    if tuple(evidence.get("distinct_counts") or ()) != EXPECTED_CALIBRATION_COUNTS:
        raise RelayError("The calibration profile is missing one or more fixed layer counts.")
    return profile


def _pending_enrollment(path: Path, relay_url: str) -> tuple[str, str, str] | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise RelayError("The trusted-helper enrollment file is damaged.") from exc
    if not isinstance(value, dict):
        raise RelayError("The trusted-helper enrollment file is invalid.")
    endpoint = normalize_relay_url(str(value.get("endpoint") or relay_url))
    one_time_code = str(value.get("enrollment_code") or "").strip()
    auto_code = str(value.get("auto_enrollment_code") or "").strip()
    if one_time_code and auto_code:
        raise RelayError("The trusted-helper enrollment file contains conflicting enrollment modes.")
    code = one_time_code or auto_code
    if not code:
        return None
    return endpoint, "enrollment_code" if one_time_code else "auto_enrollment_code", code


def ensure_enrolled(
    *,
    relay_url: str = DEFAULT_RELAY_URL,
    enrollment_file: Path | None = None,
    store: RelayStateStore | None = None,
    requester: Callable[..., dict[str, Any]] = _request_json,
) -> dict[str, Any]:
    store = store or RelayStateStore()
    state = store.load_or_create()
    configured_endpoint = normalize_relay_url(relay_url)
    enrollment_path = Path(enrollment_file) if enrollment_file is not None else default_enrollment_path()
    pending = _pending_enrollment(enrollment_path, configured_endpoint)
    if pending is not None and pending[0] != configured_endpoint:
        raise RelayError("The enrollment file belongs to a different RTTI relay.")
    if state.get("credential") and (pending is None or pending[1] == "auto_enrollment_code"):
        endpoint = normalize_relay_url(str(state.get("endpoint") or configured_endpoint))
        if endpoint != configured_endpoint:
            raise RelayError("The protected helper credential belongs to a different RTTI relay.")
        return {"endpoint": endpoint, "device_id": device_id_from_state(state), "credential": state["credential"], "helper_id": state.get("helper_id", "")}

    if pending is None:
        raise RelayError(f"Trusted-helper enrollment file was not found or has no unused code: {enrollment_path}")
    endpoint, code_field, code = pending
    device_id = device_id_from_state(state)
    response = requester(endpoint, "/v1/enroll", body={"protocol": 1, code_field: code, "device_id": device_id})
    credential = str(response.get("credential") or "")
    helper_id = str(response.get("helper_id") or "")
    if len(credential) < 60 or not helper_id:
        raise RelayError("The RTTI relay returned an invalid enrollment response.")
    state.update({"endpoint": endpoint, "credential": credential, "helper_id": helper_id, "enrollment_kind": code_field})
    store.save(state)
    if code_field == "enrollment_code":
        try:
            sanitized = {"endpoint": endpoint, "enrolled": True, "helper_id": helper_id}
            _atomic_write(enrollment_path, (json.dumps(sanitized, indent=2) + "\n").encode("utf-8"))
        except OSError:
            pass
    return {"endpoint": endpoint, "device_id": device_id, "credential": credential, "helper_id": helper_id}


def relay_publish_readiness(
    *,
    relay_url: str = DEFAULT_RELAY_URL,
    enrollment_file: Path | None = None,
    store: RelayStateStore | None = None,
    requester: Callable[..., dict[str, Any]] = _request_json,
) -> tuple[bool, str]:
    try:
        session = ensure_enrolled(
            relay_url=relay_url,
            enrollment_file=enrollment_file,
            store=store,
            requester=requester,
        )
        health = requester(session["endpoint"], "/v1/health")
        if health.get("service") != "kfps-fh6-rtti-registry" or health.get("status") != "ok":
            raise RelayError("The RTTI relay health response is invalid.")
    except RelayError as exc:
        return False, str(exc)
    return True, "Cloudflare relay connected; this trusted helper is enrolled"


def publish_profile_to_relay(
    raw_profile: Any,
    *,
    relay_url: str = DEFAULT_RELAY_URL,
    enrollment_file: Path | None = None,
    dry_run: bool = False,
    store: RelayStateStore | None = None,
    requester: Callable[..., dict[str, Any]] = _request_json,
) -> dict[str, Any]:
    profile = _strict_profile(raw_profile)
    if dry_run:
        return {"published": False, "dry_run": True, "profile_id": profile["profile_id"]}
    session = ensure_enrolled(
        relay_url=relay_url,
        enrollment_file=enrollment_file,
        store=store,
        requester=requester,
    )
    response = requester(
        session["endpoint"],
        "/v1/submit",
        body={"protocol": 1, "device_id": session["device_id"], "profile": profile},
        credential=session["credential"],
    )
    if response.get("accepted") is not True or response.get("profile_id") != profile["profile_id"]:
        raise RelayError("The RTTI relay did not confirm the submitted profile.")
    return {
        "published": True,
        "dry_run": False,
        "profile_id": profile["profile_id"],
        "updated_utc": response.get("updated_utc", ""),
    }
