from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path


class CommunityCredentialStore:
    """Stores the community bearer token with Windows DPAPI, separate from supporter state."""

    def __init__(self, runtime_root: Path, service_url: str = ""):
        self.root = Path(runtime_root) / "community"
        endpoint_key = hashlib.sha256(service_url.encode("utf-8")).hexdigest()[:20] if service_url else ""
        self.session_file = (self.root / "sessions" / f"{endpoint_key}.dpapi"
                             if endpoint_key else self.root / "session.dpapi")
        self.installation_file = self.root / "installation.json"

    def installation_id(self) -> str:
        try:
            payload = json.loads(self.installation_file.read_text(encoding="utf-8"))
            value = str(payload.get("installation_id") or "")
            if 24 <= len(value) <= 128 and all(ch.isalnum() or ch in "_-" for ch in value):
                return value
        except Exception:
            pass
        value = uuid.uuid4().hex + uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.installation_file, json.dumps({"version": 1, "installation_id": value}).encode("utf-8"))
        return value

    def load_token(self) -> str:
        if os.name != "nt" or not self.session_file.is_file():
            return ""
        try:
            import win32crypt

            _description, clear = win32crypt.CryptUnprotectData(
                self.session_file.read_bytes(), None, None, None, 0
            )
            token = clear.decode("utf-8")
            return token if token.startswith("kfc_") and len(token) == 47 else ""
        except Exception:
            return ""

    def save_token(self, token: str) -> bool:
        if os.name != "nt" or not token.startswith("kfc_") or len(token) != 47:
            return False
        try:
            import win32crypt

            encrypted = win32crypt.CryptProtectData(
                token.encode("utf-8"), "KFPS Community Session", None, None, None, 0
            )
            self.root.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.session_file, encrypted)
            return True
        except Exception:
            return False

    def clear_token(self) -> None:
        try:
            self.session_file.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)
