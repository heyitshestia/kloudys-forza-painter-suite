from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SHA256_DIGESTINFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in value).strip(" .")
    return cleaned or "supporter"


class DerReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_tlv(self) -> tuple[int, bytes]:
        if self.pos >= len(self.data):
            raise ValueError("unexpected end of DER")
        tag = self.data[self.pos]
        self.pos += 1
        if self.pos >= len(self.data):
            raise ValueError("missing DER length")
        first = self.data[self.pos]
        self.pos += 1
        if first & 0x80:
            count = first & 0x7F
            if count == 0 or count > 4:
                raise ValueError("unsupported DER length")
            if self.pos + count > len(self.data):
                raise ValueError("truncated DER length")
            length = int.from_bytes(self.data[self.pos : self.pos + count], "big")
            self.pos += count
        else:
            length = first
        if self.pos + length > len(self.data):
            raise ValueError("truncated DER value")
        value = self.data[self.pos : self.pos + length]
        self.pos += length
        return tag, value


def _read_pem(path: Path) -> tuple[str, bytes]:
    text = path.read_text(encoding="ascii")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    begin = next((line for line in lines if line.startswith("-----BEGIN ")), "")
    end = next((line for line in lines if line.startswith("-----END ")), "")
    if not begin or not end:
        raise ValueError("private key is not PEM encoded")
    label = begin.removeprefix("-----BEGIN ").removesuffix("-----")
    body = "".join(line for line in lines if not line.startswith("-----"))
    return label, base64.b64decode(body)


def _parse_integer(reader: DerReader) -> int:
    tag, value = reader.read_tlv()
    if tag != 0x02:
        raise ValueError("expected ASN.1 integer")
    return int.from_bytes(value, "big", signed=False)


def _parse_rsa_private_key(der: bytes) -> tuple[int, int]:
    tag, seq = DerReader(der).read_tlv()
    if tag != 0x30:
        raise ValueError("RSA private key is not a sequence")
    reader = DerReader(seq)
    _version = _parse_integer(reader)
    modulus = _parse_integer(reader)
    _public_exponent = _parse_integer(reader)
    private_exponent = _parse_integer(reader)
    return modulus, private_exponent


def load_private_numbers(path: Path) -> tuple[int, int]:
    label, der = _read_pem(path)
    if label == "RSA PRIVATE KEY":
        return _parse_rsa_private_key(der)
    if label != "PRIVATE KEY":
        raise ValueError(f"unsupported private key type: {label}")

    tag, seq = DerReader(der).read_tlv()
    if tag != 0x30:
        raise ValueError("PKCS#8 private key is not a sequence")
    reader = DerReader(seq)
    _version = _parse_integer(reader)
    _algorithm_tag, _algorithm = reader.read_tlv()
    private_tag, private_value = reader.read_tlv()
    if private_tag != 0x04:
        raise ValueError("PKCS#8 private key is missing private key bytes")
    return _parse_rsa_private_key(private_value)


def sign(private_key: Path, message: bytes) -> bytes:
    modulus, private_exponent = load_private_numbers(private_key)
    key_size = (modulus.bit_length() + 7) // 8
    digest_info = SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    padding_len = key_size - len(digest_info) - 3
    if padding_len < 8:
        raise ValueError("private key is too small")
    encoded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    signature_int = pow(int.from_bytes(encoded, "big"), private_exponent, modulus)
    return signature_int.to_bytes(key_size, "big")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a signed KFPS supporter unlock file.")
    parser.add_argument("--private-key", required=True, type=Path, help="Path to the private RSA PEM. Never commit this file.")
    parser.add_argument("--supporter", required=True, help="Name shown in KFPS after import.")
    parser.add_argument("--email-hash", default="", help="Optional SHA-256 hash of supporter email or Ko-fi identifier.")
    parser.add_argument("--output", required=True, type=Path, help="Output .kfpskey path.")
    args = parser.parse_args()

    payload = {
        "schema": "kfps.supporter.v1",
        "supporter_name": args.supporter.strip(),
        "supporter_hash": args.email_hash.strip(),
        "entitlements": ["supporter_theme"],
        "themes": ["Ko-fi Cherry"],
        "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    payload_bytes = canonical(payload)
    signature = sign(args.private_key, payload_bytes)
    envelope = {
        "type": "kfps.supporter.unlock",
        "version": 1,
        "payload": b64url(payload_bytes),
        "signature": b64url(signature),
    }
    output = args.output
    if output.suffix.lower() != ".kfpskey":
        output = output / f"{safe_filename(args.supporter)}.kfpskey"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
