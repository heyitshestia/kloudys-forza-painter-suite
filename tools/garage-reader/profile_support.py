"""Pinned Garage support data. Inspected statically, never executed."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes


PIN = "32bce7a6f056bb630d50187c65a0ab745ded8d1cd98225c828c43f924910b711"


@dataclass(frozen=True, repr=False)
class Keys:
    data: bytes
    mac: bytes
    salt: bytes
    info: bytes

    def __post_init__(self):
        if tuple(map(len, (self.data, self.mac, self.salt, self.info))) != (32, 16, 32, 32):
            raise ValueError("Invalid key-material lengths")


def load_support(path: Path, category="profiledata") -> Keys:
    if category not in ("profiledata", "gamedb"):
        raise ValueError("Unsupported Garage data category")
    with path.open("rb") as stream:
        blob = stream.read(2919937)
    if len(blob) != 2919936:
        raise ValueError("Unsupported Garage support data size")
    if hashlib.sha256(blob).hexdigest() != PIN:
        raise ValueError("Garage support data failed verification")
    pe = dnfile.dnPE(data=blob)
    try:
        rows = pe.net.mdtables.FieldRva.rows
        if len(rows) != 1 or pe.net.mdtables.ClassLayout.rows[0].ClassSize != 1498:
            raise ValueError("Garage support layout changed")
        encoded = pe.get_data(rows[0].Rva, 1498)
        table = bytes(value ^ (index & 255) ^ 0xAA for index, value in enumerate(encoded))

        def string_at(rid: int) -> str:
            method = pe.net.mdtables.MethodDef.rows[rid - 1]
            body = CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.Rva, 256)))
            constants = []
            for instruction in body.instructions:
                op = instruction.opcode.name
                if op in ("ldc.i4", "ldc.i4.s"):
                    constants.append(instruction.operand)
                elif op.startswith("ldc.i4.") and op[-1].isdigit():
                    constants.append(int(op[-1]))
            if len(constants) != 4 or constants[0] != constants[1]:
                raise ValueError("Unrecognized static string accessor")
            _, _, offset, length = constants
            if offset < 0 or length < 0 or offset + length > len(table):
                raise ValueError("Invalid static string range")
            return table[offset:offset + length].decode("utf-8", errors="strict")

        # These accessor positions belong to the exact hash-pinned data above.
        salt, info = (bytes.fromhex(string_at(rid)) for rid in (0x23, 0x24))
        matches = []
        for rid in range(0x25, 0x41, 4):
            if string_at(rid).casefold() == category or string_at(rid + 1).casefold() == category:
                matches.append(Keys(bytes.fromhex(string_at(rid + 2)),
                                    bytes.fromhex(string_at(rid + 3)), salt, info))
        if len(matches) != 1:
            raise ValueError("Expected exactly one Garage support category")
        return matches[0]
    finally:
        pe.close()
