from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, Signal, Slot, QTimer
from PySide6.QtWidgets import QFileDialog

from .theme_catalog import DEFAULT_THEME, SUPPORTER_THEME_NAMES, available_theme_names


PUBLIC_KEY_MODULUS_HEX = (
    "934C0F9B6DF5151523EC46C982E9B2800F97CB8E6F977D2A79582B70F385E419"
    "ECB407D8999672387CC26BB08E64CC6BA961304047E741A0FD9CCE9231A4D25F"
    "D495791CEBA2D416E8C2856A3EFAF28651EA209256792AD492593208AC38280A"
    "38B95ABF228458CEC0D64155F968C6A50A350D7F66EB8011FD119D9E070B78AB"
    "FEE71AD127BF86599D7A8C301443D83F48982DBEC54B3FE74785715422B7790A"
    "6433A1D349D7D829DBA2413FAF654DC5F9862B0ACC5C4A305990E9B65A3FB7CC"
    "2CB65FC7AA253747966CE66417DB14D591D9E2D080AA2530A7A272A3742646B8"
    "1F25182B19392F259B64133989FB276F6E43B3ACBA96AC820ED192453484B3E2"
    "FA4321141E585C5A9AD61015775227FD4B5F0534777753F17B554E4831A319AD"
    "3179D28CA3D808913E5C0D4C75BCD51650472C4364777230F0B62C728C63CBCF"
    "1CEC706DA397A6C3DAF4AA4A20DAEBFC4D7118E4695A5417AF19793024909BA5"
    "9C398D90E3A97824F5902212391C617DBA55E6F06B053EA504517054FA9EA57D"
)
PUBLIC_KEY_EXPONENT = 65537
SUPPORTER_THEME_NAME = SUPPORTER_THEME_NAMES[0] if SUPPORTER_THEME_NAMES else DEFAULT_THEME
SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _verify_rsa_pkcs1_v15_sha256(message: bytes, signature: bytes) -> bool:
    modulus = int(PUBLIC_KEY_MODULUS_HEX, 16)
    exponent = PUBLIC_KEY_EXPONENT
    key_size = (modulus.bit_length() + 7) // 8
    if len(signature) != key_size:
        return False
    sig_int = int.from_bytes(signature, "big")
    if sig_int >= modulus:
        return False
    encoded = pow(sig_int, exponent, modulus).to_bytes(key_size, "big")
    digest_info = SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    min_padding = 8
    if not encoded.startswith(b"\x00\x01"):
        return False
    try:
        separator = encoded.index(b"\x00", 2)
    except ValueError:
        return False
    if separator < 2 + min_padding:
        return False
    if encoded[2:separator] != b"\xff" * (separator - 2):
        return False
    return hmac.compare_digest(encoded[separator + 1 :], digest_info)


class SupporterService(QObject):
    changed = Signal()

    def __init__(self, runtime_root: Path, parent=None):
        super().__init__(parent)
        self._root = Path(runtime_root) / "supporter"
        self._installed_key = self._root / "supporter.kfpskey"
        self._payload: dict | None = None
        self._status = "No local unlock installed."
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self.reload)
        self._watcher.directoryChanged.connect(self.reload)
        self.reload()

    def _set_status(self, status: str):
        self._status = status
        self.changed.emit()

    def _validate_file(self, path: Path) -> tuple[bool, dict | None, str]:
        try:
            envelope = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return False, None, f"Could not read unlock file: {exc}"
        if not isinstance(envelope, dict):
            return False, None, "Unlock file is not a valid signed envelope."
        if envelope.get("type") != "kfps.supporter.unlock":
            return False, None, "Unlock file type is not recognized."
        if int(envelope.get("version", 0)) != 1:
            return False, None, "Unlock file version is not supported."
        payload_b64 = envelope.get("payload")
        signature_b64 = envelope.get("signature")
        if not isinstance(payload_b64, str) or not isinstance(signature_b64, str):
            return False, None, "Unlock file is missing payload or signature."
        try:
            payload_bytes = _b64url_decode(payload_b64)
            signature = _b64url_decode(signature_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:
            return False, None, f"Unlock file data is malformed: {exc}"
        if not isinstance(payload, dict):
            return False, None, "Unlock file payload is invalid."
        if payload.get("schema") != "kfps.supporter.v1":
            return False, None, "Unlock file payload schema is not supported."
        canonical = _canonical_payload(payload)
        if canonical != payload_bytes:
            return False, None, "Unlock file payload was not canonicalized."
        if not _verify_rsa_pkcs1_v15_sha256(canonical, signature):
            return False, None, "Unlock file signature is invalid or the file was edited."
        entitlements = payload.get("entitlements")
        if not isinstance(entitlements, list) or "supporter_theme" not in entitlements:
            return False, None, "Unlock file does not enable this feature."
        return True, payload, "Local unlock verified."

    def reload(self):
        old_unlocked = self._payload is not None
        old_status = self._status
        old_label = self.supporterLabel
        self._payload = None
        if self._installed_key.is_file():
            ok, payload, status = self._validate_file(self._installed_key)
            if ok:
                self._payload = payload
                self._status = status
            else:
                self._status = status
        else:
            self._status = "No local unlock installed."
        self._refresh_watchers()
        if old_unlocked != (self._payload is not None) or old_status != self._status or old_label != self.supporterLabel:
            self.changed.emit()

    def _refresh_watchers(self):
        self._root.mkdir(parents=True, exist_ok=True)
        watched = set(self._watcher.files() + self._watcher.directories())
        wanted = {str(self._root)}
        if self._installed_key.is_file():
            wanted.add(str(self._installed_key))
        for path in watched - wanted:
            self._watcher.removePath(path)
        for path in wanted - watched:
            if Path(path).exists():
                self._watcher.addPath(path)

    @Property(bool, notify=changed)
    def unlocked(self):
        return self._payload is not None

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def supporterLabel(self):
        if not self._payload:
            return "Not unlocked"
        name = str(self._payload.get("supporter_name") or "").strip()
        return name or "Supporter"

    @Property("QStringList", notify=changed)
    def availableThemes(self):
        return available_theme_names(self.unlocked)

    @Property(str, notify=changed)
    def preferredTheme(self):
        return SUPPORTER_THEME_NAME

    @Property("QStringList", notify=changed)
    def entitlements(self):
        if not self._payload:
            return []
        values = self._payload.get("entitlements")
        if not isinstance(values, list):
            return []
        return [str(item) for item in values]

    @Slot(str, result=bool)
    def hasEntitlement(self, name: str):
        if not self.unlocked:
            return False
        target = str(name or "").strip()
        values = set(self.entitlements)
        return bool(target and (target in values or "supporter" in values or "all_features" in values))

    @Slot(result=bool)
    def importKey(self):
        start = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Import KFPS unlock",
            start,
            "KFPS unlock (*.kfpskey);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return False
        source = Path(path)
        ok, payload, status = self._validate_file(source)
        if not ok:
            self._payload = None
            self._set_status(status)
            return False
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._installed_key.with_suffix(".tmp")
        shutil.copyfile(source, tmp)
        os.replace(tmp, self._installed_key)
        self._payload = payload
        self._set_status(status)
        return True

    @Slot()
    def removeKey(self):
        try:
            self._installed_key.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            self._set_status(f"Could not remove unlock file: {exc}")
            return
        self._payload = None
        self._set_status("Local unlock removed.")
        self._refresh_watchers()

    @Slot()
    def refresh(self):
        QTimer.singleShot(0, self.reload)
