"""Synthetic format cases, run in a child to isolate SQLite's heap limits."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/garage-reader"), str(ROOT / "tools/garage-reader/vendor")]
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from profile_support import Keys
import profile_reader as reader

KEYS = Keys(bytes(range(32)), bytes(range(16)), b"s" * 32, b"i" * 32)


def fixture(sql=""):
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE Career_Garage (Id INTEGER PRIMARY KEY, CarId INTEGER, FrontBumper INTEGER, RearWing INTEGER, CarBody INTEGER, RearBumper INTEGER, Hood INTEGER, SideSkirts INTEGER)")
        db.execute("CREATE TABLE Career_PurchasedParts (GarageId INT, UngroupedPartEnum INT, PartId INT, PricePaid INT)")
        db.execute("INSERT INTO Career_Garage VALUES (1,4313,4313001,4313002,4313000,4313000,4313000,4313000)")
        if sql:
            db.executescript(sql)
        db.commit()
        data = db.serialize()
    db.close()
    return b"".join(struct.pack("<II", tag, len(part)) + part
                    for tag, part in zip(reader.SECTION_TAGS, (b"a", b"b", b"c", data)))


def packed(payload):
    data = zlib.compress(payload)
    return struct.pack("<II", len(data), len(payload)) + data


def tag(data):
    mac = CMAC(algorithms.AES(KEYS.mac))
    mac.update(data)
    return mac.finalize()


def envelope(raw, padding=None):
    iv = b"v" * 16
    count = (-len(raw)) % 512
    raw += bytes(count)
    header = iv + struct.pack("<I", count if padding is None else padding)
    result = bytearray(header + tag(struct.pack("<I", len(raw)) + header))
    for offset in range(0, len(raw), 512):
        chunk = raw[offset:offset + 512]
        for part in (chunk, tag(chunk)):
            operation = Cipher(algorithms.AES(KEYS.data), modes.CBC(iv)).encryptor()
            result.extend(operation.update(part) + operation.finalize())
            iv = HKDF(algorithm=hashes.SHA256(), length=16, salt=KEYS.salt, info=KEYS.info).derive(iv)
    return bytes(result)


class FormatCases(unittest.TestCase):
    def test_roundtrip_and_repeat_are_read_only(self):
        payload = fixture()
        source = envelope(packed(payload))
        before = hashlib.sha256(source).digest()
        first = reader.decode(source, KEYS)
        self.assertEqual(payload, first.payload)
        self.assertEqual(4313001, first.garage[0]["FrontBumper"])
        self.assertEqual(first.garage, reader.decode(source, KEYS).garage)
        self.assertEqual(before, hashlib.sha256(source).digest())

    def test_corruption_truncation_and_added_chunks(self):
        source = envelope(packed(fixture()))
        for offset in (0, 16, 20, 35, 36, 200, 547, 548, 563):
            changed = bytearray(source)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(reader.DecodeError):
                reader.decode(bytes(changed), KEYS)
        for size in (0, 1, 35, 36, 37, 100, 563):
            with self.subTest(size=size), self.assertRaises(reader.DecodeError):
                reader.decode(source[:size], KEYS)
        with self.assertRaises(reader.DecodeError):
            reader.decode(source + source[36:564], KEYS)
        with self.assertRaises(reader.DecodeError):
            reader.decode(envelope(packed(fixture()), padding=512), KEYS)

    def test_wrong_support_fields(self):
        for name in ("data", "mac", "salt", "info"):
            fields = {key: getattr(KEYS, key) for key in ("data", "mac", "salt", "info")}
            fields[name] = bytes([fields[name][0] ^ 1]) + fields[name][1:]
            with self.subTest(field=name), self.assertRaises(reader.DecodeError):
                reader.decode(envelope(packed(fixture())), Keys(**fields))

    def test_section_boundaries(self):
        payload = fixture()
        variants = [payload + b"extra", b"x" + payload[1:], payload[:4] + b"\xff" * 4 + payload[8:],
                    payload.replace(b"SQLite format 3", b"BADite format 3")]
        for value in variants:
            with self.subTest(length=len(value)), self.assertRaises(reader.DecodeError):
                reader.parse_sections(value)

    def test_compression_boundaries(self):
        payload = fixture()
        data = zlib.compress(payload)
        for size, value in ((len(payload), data + b"junk"), (len(payload), data + zlib.compress(b"x")),
                            (len(payload) - 1, data), (len(payload) + 1, data),
                            (len(payload), data[:-1]), (32, zlib.compress(b"z" * 1000000)),
                            (0xffffffff, b"z"), (2, b"z")):
            with self.subTest(size=size), self.assertRaises(reader.DecodeError):
                reader.expand(struct.pack("<II", len(value), size) + value)

    def test_database_schema_and_types(self):
        for sql in ("UPDATE Career_Garage SET FrontBumper='bad'", "UPDATE Career_Garage SET CarId=NULL",
                    "UPDATE Career_Garage SET Hood=NULL", "DROP TABLE Career_PurchasedParts",
                    "ALTER TABLE Career_Garage RENAME TO old; CREATE TABLE Career_Garage AS SELECT * FROM old",
                    "ALTER TABLE Career_Garage ADD COLUMN LiveryFileName TEXT; UPDATE Career_Garage SET LiveryFileName=42"):
            # SQLite TEXT affinity converts 42, so exercise a genuine BLOB instead.
            sql = sql.replace("LiveryFileName=42", "LiveryFileName=x'0102'")
            with self.subTest(sql=sql), self.assertRaises(reader.DecodeError):
                reader.inspect_database(reader.parse_sections(fixture(sql))[-1])

    def test_database_extent_and_output_limits(self):
        db = reader.parse_sections(fixture())[-1]
        bad = bytearray(db)
        bad[100] = 255
        for data in (db + bytes(int.from_bytes(db[16:18], "big")), bytes(bad), db[:16], db[:99], db[:101]):
            with self.subTest(size=len(data)), self.assertRaises(reader.DecodeError):
                reader.inspect_database(data)
        with patch.object(reader, "MAX_EXPORT", 10), self.assertRaises(reader.DecodeError):
            reader.inspect_database(db)

    def test_nullable_optional_values_and_private_columns(self):
        db = reader.parse_sections(fixture("ALTER TABLE Career_Garage ADD COLUMN TireBrand INT; ALTER TABLE Career_Garage ADD COLUMN AccountName TEXT DEFAULT 'private';"))[-1]
        _, rows = reader.inspect_database(db)
        self.assertIsNone(rows[0]["TireBrand"])
        self.assertNotIn("AccountName", rows[0])
        self.assertNotIn("private", json.dumps(rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
