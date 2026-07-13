from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Protocol


class ActivationStorageError(RuntimeError):
    pass


class DataProtector(Protocol):
    def protect(self, value: bytes) -> bytes: ...
    def unprotect(self, value: bytes) -> bytes: ...


class DpapiProtector:
    _entropy = b"KFPS-SUPPORTER-ACTIVATION-V1"

    def __init__(self):
        try:
            import win32crypt
        except Exception as exc:
            raise ActivationStorageError("Windows protected storage is unavailable.") from exc
        self._win32crypt = win32crypt

    def protect(self, value: bytes) -> bytes:
        try:
            flags = int(getattr(self._win32crypt, "CRYPTPROTECT_UI_FORBIDDEN", 1))
            protected = self._win32crypt.CryptProtectData(
                value,
                "KFPS local activation state",
                self._entropy,
                None,
                None,
                flags,
            )
            if isinstance(protected, tuple):
                protected = protected[-1]
            return bytes(protected)
        except Exception as exc:
            raise ActivationStorageError("Could not protect local activation data.") from exc

    def unprotect(self, value: bytes) -> bytes:
        try:
            flags = int(getattr(self._win32crypt, "CRYPTPROTECT_UI_FORBIDDEN", 1))
            unprotected = self._win32crypt.CryptUnprotectData(value, self._entropy, None, None, flags)
            if isinstance(unprotected, tuple):
                unprotected = unprotected[-1]
            return bytes(unprotected)
        except Exception as exc:
            raise ActivationStorageError("Local activation data could not be opened for this Windows user and device.") from exc


class PlaintextTestProtector:
    def protect(self, value: bytes) -> bytes:
        return b"KFPS-TEST\x00" + value

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(b"KFPS-TEST\x00"):
            raise ActivationStorageError("Invalid test-protected data.")
        return value[len(b"KFPS-TEST\x00") :]


def default_activation_root() -> Path:
    override = os.environ.get("KFPS_ACTIVATION_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "KFPS" / "state"


def derive_device_id(device_secret: bytes) -> str:
    return hashlib.sha256(b"KFPS-DEVICE-V1\x00" + device_secret).hexdigest()


class ActivationStore:
    def __init__(self, root: Path | None = None, protector: DataProtector | None = None):
        self._root = Path(root) if root is not None else default_activation_root()
        self._identity_file = self._root / "identity.dat"
        self._state_file = self._root / "activation.dat"
        self._protector = protector or DpapiProtector()

    def _atomic_write(self, path: Path, value: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix="kfps-", suffix=".tmp", dir=path.parent)
            os.close(fd)
            temp_path = Path(temp_name)
            temp_path.write_bytes(value)
            os.replace(temp_path, path)
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise ActivationStorageError("Could not save local activation data.") from exc

    def load_or_create_identity(self) -> tuple[bytes, str]:
        if self._identity_file.exists():
            try:
                secret = self._protector.unprotect(self._identity_file.read_bytes())
            except ActivationStorageError:
                raise
            except Exception as exc:
                raise ActivationStorageError("Could not read local activation identity.") from exc
            if len(secret) != 32:
                raise ActivationStorageError("Local activation identity is damaged.")
            return secret, derive_device_id(secret)
        secret = secrets.token_bytes(32)
        self._atomic_write(self._identity_file, self._protector.protect(secret))
        return secret, derive_device_id(secret)

    def _empty_state(self) -> dict:
        return {"schema": "kfps.activation.local.v1", "keys": {}}

    def load(self) -> dict:
        if not self._state_file.exists():
            return self._empty_state()
        try:
            raw = self._protector.unprotect(self._state_file.read_bytes())
            state = json.loads(raw.decode("utf-8"))
        except ActivationStorageError:
            raise
        except Exception as exc:
            raise ActivationStorageError("Local activation state is damaged.") from exc
        if not isinstance(state, dict) or state.get("schema") != "kfps.activation.local.v1" or not isinstance(state.get("keys"), dict):
            raise ActivationStorageError("Local activation state format is invalid.")
        return state

    def save(self, state: dict):
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._atomic_write(self._state_file, self._protector.protect(raw))

    def key_state(self, key_id: str) -> dict:
        state = self.load()
        value = state["keys"].get(key_id, {})
        return dict(value) if isinstance(value, dict) else {}

    def save_key_state(self, key_id: str, value: dict):
        state = self.load()
        state["keys"][key_id] = dict(value)
        self.save(state)

    def remove_key_state(self, key_id: str):
        state = self.load()
        if key_id in state["keys"]:
            del state["keys"][key_id]
            self.save(state)


def encode_receipt(receipt: object) -> str:
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_receipt(value: str) -> object:
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("utf-8"))
