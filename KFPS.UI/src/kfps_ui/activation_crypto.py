from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .activation_config import (
    ACTIVATION_KEY_ID,
    ACTIVATION_PUBLIC_KEY_EXPONENT,
    ACTIVATION_PUBLIC_KEY_MODULUS_HEX,
)


SUPPORTER_PUBLIC_KEY_MODULUS_HEX = (
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
SUPPORTER_PUBLIC_KEY_EXPONENT = 65537
SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True)
class RsaPublicKey:
    modulus_hex: str
    exponent: int


@dataclass(frozen=True)
class SupporterKey:
    path: Path
    payload: dict[str, Any]
    payload_bytes: bytes
    signature: bytes
    key_id: str
    signature_sha256: str
    key_proof: str


SUPPORTER_PUBLIC_KEY = RsaPublicKey(SUPPORTER_PUBLIC_KEY_MODULUS_HEX, SUPPORTER_PUBLIC_KEY_EXPONENT)
ACTIVATION_PUBLIC_KEY = RsaPublicKey(ACTIVATION_PUBLIC_KEY_MODULUS_HEX, ACTIVATION_PUBLIC_KEY_EXPONENT)


def b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("empty base64url value")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_rsa_pkcs1_v15_sha256(message: bytes, signature: bytes, public_key: RsaPublicKey) -> bool:
    modulus = int(public_key.modulus_hex, 16)
    key_size = (modulus.bit_length() + 7) // 8
    if len(signature) != key_size:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int >= modulus:
        return False
    encoded = pow(signature_int, public_key.exponent, modulus).to_bytes(key_size, "big")
    digest_info = SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    if not encoded.startswith(b"\x00\x01"):
        return False
    try:
        separator = encoded.index(b"\x00", 2)
    except ValueError:
        return False
    if separator < 10 or encoded[2:separator] != b"\xff" * (separator - 2):
        return False
    return hmac.compare_digest(encoded[separator + 1 :], digest_info)


def derive_activation_key_id(payload_bytes: bytes, signature: bytes) -> str:
    material = (
        b"KFPS-ACTIVATION-KEY-V1\x00"
        + len(payload_bytes).to_bytes(4, "big")
        + payload_bytes
        + signature
    )
    return hashlib.sha256(material).hexdigest()


def read_supporter_key(path: Path) -> tuple[SupporterKey | None, str]:
    path = Path(path)
    try:
        envelope = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, f"Could not read unlock file: {exc}"
    if not isinstance(envelope, dict):
        return None, "Unlock file is not a valid signed envelope."
    if envelope.get("type") != "kfps.supporter.unlock":
        return None, "Unlock file type is not recognized."
    if envelope.get("version") != 1:
        return None, "Unlock file version is not supported."
    payload_b64 = envelope.get("payload")
    signature_b64 = envelope.get("signature")
    if not isinstance(payload_b64, str) or not isinstance(signature_b64, str):
        return None, "Unlock file is missing payload or signature."
    try:
        payload_bytes = b64url_decode(payload_b64)
        signature = b64url_decode(signature_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        return None, f"Unlock file data is malformed: {exc}"
    if not isinstance(payload, dict) or payload.get("schema") != "kfps.supporter.v1":
        return None, "Unlock file payload schema is not supported."
    if canonical_payload(payload) != payload_bytes:
        return None, "Unlock file payload was not canonicalized."
    if not verify_rsa_pkcs1_v15_sha256(payload_bytes, signature, SUPPORTER_PUBLIC_KEY):
        return None, "Unlock file signature is invalid or the file was edited."
    entitlements = payload.get("entitlements")
    if not isinstance(entitlements, list) or "supporter_theme" not in entitlements:
        return None, "Unlock file does not enable this feature."
    return SupporterKey(
        path=path,
        payload=payload,
        payload_bytes=payload_bytes,
        signature=signature,
        key_id=derive_activation_key_id(payload_bytes, signature),
        signature_sha256=hashlib.sha256(signature).hexdigest(),
        key_proof=b64url_encode(signature),
    ), "Local unlock verified."


def _signed_payload(
    envelope: object,
    *,
    expected_type: str,
    expected_schema: str,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(envelope, dict):
        return None, "Signed activation response is not an object."
    if envelope.get("type") != expected_type or envelope.get("version") != 1:
        return None, "Signed activation response type is invalid."
    if envelope.get("kid") != ACTIVATION_KEY_ID:
        return None, "Signed activation response key is not recognized."
    try:
        payload_bytes = b64url_decode(envelope["payload"])
        signature = b64url_decode(envelope["signature"])
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None, "Signed activation response is malformed."
    if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
        return None, "Signed activation response schema is invalid."
    if canonical_payload(payload) != payload_bytes:
        return None, "Signed activation response is not canonical."
    if not verify_rsa_pkcs1_v15_sha256(payload_bytes, signature, ACTIVATION_PUBLIC_KEY):
        return None, "Signed activation response signature is invalid."
    return payload, ""


def verify_activation_receipt(
    envelope: object,
    *,
    key_id: str,
    device_id: str,
) -> tuple[dict[str, Any] | None, str]:
    payload, error = _signed_payload(
        envelope,
        expected_type="kfps.supporter.activation",
        expected_schema="kfps.activation.v1",
    )
    if payload is None:
        return None, error
    if payload.get("key_id") != key_id or payload.get("device_id") != device_id:
        return None, "Activation receipt does not belong to this key and device."
    if not isinstance(payload.get("activated_at"), str):
        return None, "Activation receipt is missing its activation time."
    return payload, ""


def verify_activation_decision(
    envelope: object,
    *,
    key_id: str,
    device_id: str,
    nonce: str,
) -> tuple[dict[str, Any] | None, str]:
    payload, error = _signed_payload(
        envelope,
        expected_type="kfps.supporter.activation-decision",
        expected_schema="kfps.activation.decision.v1",
    )
    if payload is None:
        return None, error
    if payload.get("key_id") != key_id or payload.get("device_id") != device_id or payload.get("nonce") != nonce:
        return None, "Activation decision does not match the current request."
    if payload.get("status") not in {"already_activated", "not_eligible", "deactivated"}:
        return None, "Activation decision status is not recognized."
    return payload, ""


def verify_activation_status(
    envelope: object,
    *,
    key_id: str,
    device_id: str,
    nonce: str,
) -> tuple[dict[str, Any] | None, str]:
    payload, error = _signed_payload(
        envelope,
        expected_type="kfps.supporter.activation-status",
        expected_schema="kfps.activation.status.v1",
    )
    if payload is None:
        return None, error
    if payload.get("key_id") != key_id or payload.get("device_id") != device_id or payload.get("nonce") != nonce:
        return None, "Activation status does not match the current request."
    if payload.get("status") not in {"active", "revoked"}:
        return None, "Activation status is not recognized."
    if not isinstance(payload.get("checked_at"), str):
        return None, "Activation status is missing its check time."
    return payload, ""
