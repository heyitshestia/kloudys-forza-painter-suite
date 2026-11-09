"""Bounded installed catalogue transport. No game paths or persistent output."""
from array import array
import hmac
import struct
import sys
import zlib

from profile_reader import _tag, _next_iv, _decrypt

MAX_INPUT = 64 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
BLOCK = 128 * 1024


def read_catalogue(source, keys):
    stride = BLOCK + 16
    if not 36 + stride <= len(source) <= MAX_INPUT or (len(source) - 36) % stride:
        raise ValueError('Unsupported catalogue framing')
    chunks = (len(source) - 36) // stride
    padded = chunks * BLOCK
    padding = struct.unpack_from('<I', source, 16)[0]
    if padded > MAX_OUTPUT or padding >= BLOCK:
        raise ValueError('Unsupported catalogue size')
    if not hmac.compare_digest(_tag(keys.mac, struct.pack('<I', padded) + source[:20]), source[20:36]):
        raise ValueError('Catalogue header validation failed')
    iv, result = source[:16], bytearray()
    for start in range(36, len(source), stride):
        block = _decrypt(source[start:start + BLOCK], iv, keys.data)
        iv = _next_iv(iv, keys)
        observed = _decrypt(source[start + BLOCK:start + stride], iv, keys.data)
        if not hmac.compare_digest(_tag(keys.mac, block), observed):
            raise ValueError('Catalogue block validation failed')
        result.extend(block)
        iv = _next_iv(iv, keys)
    if padding and any(result[-padding:]):
        raise ValueError('Invalid catalogue padding')
    # GameDB VFS applies a position-derived CRC32 word mask after transport.
    # Independent implementation using the standard-library CRC primitive.
    words = array('I')
    words.frombytes(result)
    if words.itemsize != 4:
        raise ValueError('Unsupported word size')
    if sys.byteorder != 'little':
        words.byteswap()
    for index in range(len(words)):
        seed = (index + 0xE910D5B8 * (index + 1)) & 0xffffffff
        words[index] ^= zlib.crc32(seed.to_bytes(4, 'little').lower())
    if sys.byteorder != 'little':
        words.byteswap()
    result = words.tobytes()
    if not result.startswith(b'SQLite format 3\0') or len(result) < 100:
        raise ValueError('Catalogue is not a supported database')
    page_size = int.from_bytes(result[16:18], 'big')
    if page_size == 1:
        page_size = 65536
    pages = int.from_bytes(result[28:32], 'big')
    if (page_size < 512 or page_size > 65536 or page_size & (page_size - 1)
            or not pages or result[24:28] != result[92:96]
            or len(result) % page_size or pages * page_size > len(result)
            or result[18] not in (1, 2) or result[19] not in (1, 2)
            or result[21:24] != bytes((64, 32, 32)) or any(result[72:92])):
        raise ValueError('Unsupported catalogue database extent')
    return result[:pages * page_size]


