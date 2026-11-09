"""Bounded, authenticated, read-only FH6 profile decoding.

Independent implementation of the observed CryptoContainer and profile framing.
No game execution, live-memory access, network access or save-writing support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import sqlite3
import struct
import time
import zlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from profile_support import Keys


MAX_INPUT = 128 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_EXPORT = 16 * 1024 * 1024
TEXT_COLUMNS = {"LiveryFileName", "LiveryFilename", "TuneFileName"}
REQUIRED_PARTS = {"CarBody", "RearWing", "FrontBumper", "RearBumper", "Hood", "SideSkirts"}
SECTION_TAGS = (0x4A8BF2B6, 0xB60261FC, 0x986CA5CB, 0xA9F1F729)
SQLITE_MAGIC = b"SQLite format 3\x00"
PART_COLUMNS = {
    "Id", "CarId", "CarID", "Engine", "Drivetrain", "CarBody", "Motor",
    "Brakes", "SpringDamper", "AntiSwayFront", "AntiSwayRear", "TireCompound",
    "RearWing", "RimSizeFront", "RimSizeRear", "Camshaft", "Valves",
    "Displacement", "Pistons", "FuelSystem", "Ignition", "Exhaust", "Intake",
    "Flywheel", "RestrictorPlate", "OilCooling", "Intercooler", "Clutch",
    "Transmission", "Driveline", "Differential", "FrontBumper", "RearBumper",
    "Hood", "SideSkirts", "TireWidthFront", "TireWidthRear", "WeightReduction",
    "ChassisStiffness", "Aspiration", "Rims", "RimStyle", "LiveryId", "LiveryID",
    "LiveryFileName", "LiveryFilename", "TuneFileName", "PistonsCompression",
    "Manifold", "SingleTurbo", "TwinTurbo", "QuadTurbo", "SuperchargerCSC",
    "SuperchargerDSC", "TrackSpacingFront", "TrackSpacingRear", "FrontAspectRatio",
    "RearAspectRatio", "MotorParts", "TireBrand", "WheelStyle", "WheelStyleRear",
}


class DecodeError(ValueError):
    """Invalid, unsupported or unauthenticated input; no output is valid."""


@dataclass(frozen=True)
class Decoded:
    payload: bytes = field(repr=False)
    database: bytes = field(repr=False)
    summary: dict
    garage: list[dict] = field(repr=False)


def _tag(key: bytes, message: bytes) -> bytes:
    context = CMAC(algorithms.AES(key))
    context.update(message)
    return context.finalize()


def _next_iv(iv: bytes, keys: Keys) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=16, salt=keys.salt, info=keys.info).derive(iv)


def _decrypt(ciphertext: bytes, iv: bytes, key: bytes) -> bytes:
    context = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return context.update(ciphertext) + context.finalize()


def unwrap(source: bytes, keys: Keys) -> tuple[bytes, int]:
    if not 564 <= len(source) <= MAX_INPUT or (len(source) - 36) % 528:
        raise DecodeError("Unsupported encrypted profile length or chunk framing")
    chunks = (len(source) - 36) // 528
    padded_length = chunks * 512
    padding = struct.unpack_from("<I", source, 16)[0]
    if padding >= 512:
        raise DecodeError("Invalid profile padding count")
    expected_header = _tag(keys.mac, struct.pack("<I", padded_length) + source[:20])
    if not hmac.compare_digest(expected_header, source[20:36]):
        raise DecodeError("Profile header authentication failed (wrong format/key or damaged input)")
    iv = source[:16]
    plaintext = bytearray()
    for index, start in enumerate(range(36, len(source), 528)):
        block = _decrypt(source[start:start + 512], iv, keys.data)
        iv = _next_iv(iv, keys)
        observed_tag = _decrypt(source[start + 512:start + 528], iv, keys.data)
        if not hmac.compare_digest(_tag(keys.mac, block), observed_tag):
            raise DecodeError(f"Profile chunk {index} authentication failed")
        plaintext.extend(block)
        iv = _next_iv(iv, keys)
    if padding and any(plaintext[-padding:]):
        raise DecodeError("Nonzero profile padding is unsupported")
    return bytes(plaintext[:padded_length - padding]), chunks


def expand(raw: bytes) -> bytes:
    if len(raw) < 8:
        raise DecodeError("Missing compression header")
    compressed, expanded = struct.unpack_from("<II", raw)
    if compressed == 0 or compressed != len(raw) - 8:
        raise DecodeError("Compressed size does not match authenticated plaintext")
    if not 32 <= expanded <= MAX_EXPANDED:
        raise DecodeError("Expanded profile size is outside the supported limit")
    codec = zlib.decompressobj()
    try:
        payload = codec.decompress(raw[8:], expanded + 1)
    except zlib.error as error:
        raise DecodeError("Invalid zlib stream") from error
    if len(payload) != expanded or not codec.eof or codec.unused_data or codec.unconsumed_tail:
        raise DecodeError("Truncated, oversized or trailing compressed data")
    return payload


def parse_sections(payload: bytes) -> tuple[bytes, ...]:
    if len(payload) > MAX_EXPANDED:
        raise DecodeError("Expanded profile exceeds the size limit")
    offset = 0
    parts = []
    for expected in SECTION_TAGS:
        if len(payload) - offset < 8:
            raise DecodeError("Truncated section header")
        tag, length = struct.unpack_from("<II", payload, offset)
        if tag != expected or length > len(payload) - offset - 8:
            raise DecodeError("Invalid section marker or length")
        offset += 8
        parts.append(payload[offset:offset + length])
        offset += length
    if offset != len(payload):
        raise DecodeError("Unexpected trailing profile section data")
    if not parts[-1].startswith(SQLITE_MAGIC):
        raise DecodeError("Database section has no SQLite signature")
    return tuple(parts)


def secure_connection(connection: sqlite3.Connection) -> None:
    """The isolated reader owns SQLite's process-wide heap cap."""
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    connection.execute("PRAGMA hard_heap_limit=134217728")
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA cache_size=-8192")
    for category, limit in (
        (sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024),
        (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100000),
        (sqlite3.SQLITE_LIMIT_COLUMN, 256),
        (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50),
        (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 10),
        (sqlite3.SQLITE_LIMIT_VDBE_OP, 100000),
        (sqlite3.SQLITE_LIMIT_FUNCTION_ARG, 16),
        (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
        (sqlite3.SQLITE_LIMIT_TRIGGER_DEPTH, 0),
        (sqlite3.SQLITE_LIMIT_WORKER_THREADS, 0),
    ):
        connection.setlimit(category, limit)
    deadline = time.monotonic() + 10
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)


def inspect_database(database: bytes) -> tuple[dict, list[dict]]:
    if not 100 <= len(database) <= MAX_EXPANDED or not database.startswith(SQLITE_MAGIC):
        raise DecodeError("Invalid SQLite header")
    encoded_page_size = int.from_bytes(database[16:18], "big")
    page_size = 65536 if encoded_page_size == 1 else encoded_page_size
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1) or len(database) % page_size:
        raise DecodeError("Invalid SQLite page geometry")
    pages = int.from_bytes(database[28:32], "big")
    if pages and database[24:28] == database[92:96] and pages * page_size != len(database):
        raise DecodeError("Database section differs from its authoritative page extent")
    connection = sqlite3.connect(":memory:")
    try:
        secure_connection(connection)
        connection.deserialize(database)
        if connection.execute("PRAGMA page_count").fetchone()[0] * page_size != len(database):
            raise DecodeError("Database has unconsumed pages")
        integrity = connection.execute("PRAGMA integrity_check(1)").fetchall()
        if integrity != [("ok",)]:
            raise DecodeError("SQLite integrity_check failed")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if not {"Career_Garage", "Career_PurchasedParts"} <= tables:
            raise DecodeError("Database is not a supported FH6 garage profile")
        garage_schema = connection.execute('PRAGMA table_info("Career_Garage")').fetchall()
        columns = [row[1] for row in garage_schema]
        if not {"Id", "CarId", *REQUIRED_PARTS} <= set(columns):
            raise DecodeError("Garage identity or essential part columns are missing")
        identities = [row for row in garage_schema if row[1] == "Id"]
        if identities[0][5] != 1 or identities[0][2].upper() != "INTEGER":
            raise DecodeError("Unsupported garage primary-key contract")
        purchased_schema = connection.execute('PRAGMA table_info("Career_PurchasedParts")').fetchall()
        purchased_columns = {row[1] for row in purchased_schema}
        if not {"GarageId", "UngroupedPartEnum", "PartId", "PricePaid"} <= purchased_columns:
            raise DecodeError("Unsupported purchased-parts schema")
        selected = [name for name in columns if name in PART_COLUMNS]
        count = connection.execute('SELECT count(*) FROM "Career_Garage"').fetchone()[0]
        if count > 100000:
            raise DecodeError("Garage row count exceeds the supported limit")
        query = 'SELECT ' + ', '.join('"' + name + '"' for name in selected) + ' FROM "Career_Garage" ORDER BY "Id"'
        rows, seen, export_size = [], set(), 0
        for values in connection.execute(query):
            row = dict(zip(selected, values))
            for name, value in row.items():
                if value is None and name not in {"Id", "CarId", *REQUIRED_PARTS}:
                    continue
                if name in TEXT_COLUMNS:
                    if not isinstance(value, str) or len(value) > 4096:
                        raise DecodeError("Invalid saved filename field")
                elif type(value) is not int:
                    raise DecodeError("Garage identity/part value is not an integer")
            if row["Id"] in seen:
                raise DecodeError("Duplicate garage instance ID")
            seen.add(row["Id"])
            export_size += len(json.dumps(row, ensure_ascii=True, indent=2)) + 4
            if export_size > MAX_EXPORT:
                raise DecodeError("Garage export exceeds the size budget")
            rows.append(row)
        summary = {
            "integrity_check": "ok", "garage_count": count,
            "purchased_parts_count": connection.execute('SELECT count(*) FROM "Career_PurchasedParts"').fetchone()[0],
            "table_count": len(tables), "garage_columns": columns,
            "exported_columns": selected, "sqlite_bytes": len(database),
            "sqlite_sha256": hashlib.sha256(database).hexdigest(),
        }
        return summary, rows
    except (sqlite3.Error, MemoryError) as error:
        raise DecodeError("SQLite validation/read failed") from error
    finally:
        connection.close()


def decode(source: bytes, keys: Keys) -> Decoded:
    raw, chunks = unwrap(source, keys)
    payload = expand(raw)
    sections = parse_sections(payload)
    summary, garage = inspect_database(sections[-1])
    summary.update({"source_sha256": hashlib.sha256(source).hexdigest(),
                    "source_bytes": len(source), "authenticated_chunks": chunks,
                    "header_authenticated": True, "all_chunks_authenticated": True,
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "section_sizes": [len(section) for section in sections]})
    return Decoded(payload, sections[-1], summary, garage)
