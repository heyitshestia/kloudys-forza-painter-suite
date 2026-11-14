from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import tracemalloc
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI.parent), str(UI / "src")]

from tools.cgroup import forza_source_decoder as decoder


def block(data: bytes, declared: int | None = None) -> bytes:
    compressed = zlib.compress(data)
    return struct.pack("<II", len(compressed), len(data) if declared is None else declared) + compressed


class ForzaContainerLimitTests(unittest.TestCase):
    def unwrap(self, data):
        return decoder.unwrap_forza_container_bytes(data, Path("synthetic-C_livery"))

    def test_forged_tiny_length_rejected_before_large_allocation(self):
        raw = block(bytes(32 * 1024 * 1024), 1)
        tracemalloc.start()
        try:
            with self.assertRaises(decoder.DecodeError):
                self.unwrap(raw)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 2 * 1024 * 1024, f"forged length allocated {peak} bytes")

    def test_per_block_declaration_rejected_before_inflater_creation(self):
        raw = block(b"x", 64 * 1024 * 1024 + 1)
        with patch.object(decoder.zlib, "decompressobj", wraps=zlib.decompressobj) as inflater:
            with self.assertRaisesRegex(decoder.DecodeError, "block.*limit"):
                self.unwrap(raw)
            inflater.assert_not_called()

    def test_exact_and_excess_block_and_cumulative_budgets(self):
        with patch.object(decoder, "MAX_FORZA_BLOCK_BYTES", 16), patch.object(
            decoder, "MAX_FORZA_PAYLOAD_BYTES", 24
        ):
            self.assertEqual(b"a" * 16 + b"b" * 8, self.unwrap(block(b"a" * 16) + block(b"b" * 8)))
            with self.assertRaisesRegex(decoder.DecodeError, "block.*limit"):
                self.unwrap(block(b"a" * 17))

    def test_cumulative_declarations_are_checked_before_next_inflater(self):
        with patch.object(decoder, "MAX_FORZA_BLOCK_BYTES", 16), patch.object(
            decoder, "MAX_FORZA_PAYLOAD_BYTES", 24
        ), patch.object(decoder.zlib, "decompressobj", wraps=zlib.decompressobj) as inflater:
            with self.assertRaisesRegex(decoder.DecodeError, "total.*limit"):
                self.unwrap(block(b"a" * 16) + block(b"b" * 9))
            self.assertEqual(1, inflater.call_count)

    def test_forged_second_block_cannot_exceed_cumulative_budget(self):
        with patch.object(decoder, "MAX_FORZA_BLOCK_BYTES", 16), patch.object(
            decoder, "MAX_FORZA_PAYLOAD_BYTES", 24
        ):
            with self.assertRaises(decoder.DecodeError):
                self.unwrap(block(b"a" * 16) + block(b"b" * 9, 8))

    def test_zero_length_block_cannot_disable_output_bound(self):
        self.assertEqual(b"", self.unwrap(block(b"")))
        with self.assertRaises(decoder.DecodeError):
            self.unwrap(block(b"x", 0))

    def test_truncated_corrupt_trailing_and_concatenated_zlib_rejected(self):
        compressed = zlib.compress(b"fixture")
        corrupt = compressed[:-1] + bytes((compressed[-1] ^ 255,))
        for stream in (compressed[:-1], corrupt, compressed + b"trailing", compressed + compressed):
            with self.subTest(stream=stream), self.assertRaises(decoder.DecodeError):
                self.unwrap(struct.pack("<II", len(stream), 7) + stream)
        for raw in (block(b"fixture")[:-1], block(b"fixture") + b"x", block(b"fixture", 8)):
            with self.subTest(raw=raw), self.assertRaises(decoder.DecodeError):
                self.unwrap(raw)

    def test_large_valid_multiblock_and_file_entry_point(self):
        data = bytes(range(256)) * (8 * 1024)
        wrapped = block(data) + block(data) + block(b"")
        self.assertEqual(data + data, self.unwrap(wrapped))
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "C_livery"
            source.write_bytes(wrapped)
            self.assertEqual(data + data, decoder.unwrap_forza_container(source))

    def test_honest_32_mib_block_is_not_rejected_as_a_compression_bomb(self):
        data = bytes(32 * 1024 * 1024)
        self.assertEqual(data, self.unwrap(block(data)))

    def test_incompressible_data_crosses_input_and_output_chunk_boundaries(self):
        import random

        data = random.Random(20261114).randbytes(256 * 1024 + 1)
        self.assertEqual(data, self.unwrap(block(data)))

    def test_community_validation_bounds_nested_expansion_and_interrupted_download(self):
        from kfps_ui.community_gallery_service import CommunityGalleryService
        from test_full_livery_package import build_package, rewrite_package, refresh_manifest_hashes
        from tools.livery.package import FullLiveryPackageError

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, altered = root / "fixture.kfpslivery", root / "nested.kfpslivery"
            build_package(original)
            inner = block(bytes(32 * 1024 * 1024), 1)

            def transform(entries):
                entries["source/fh6/C_livery"] = inner
                manifest = json.loads(entries["manifest.json"])
                manifest["source"]["owned"] = True
                manifest["sharing"]["contains_foreign_vinyl_groups"] = False
                entries["manifest.json"] = json.dumps(manifest).encode("utf-8")
                refresh_manifest_hashes(entries)

            rewrite_package(original, altered, transform)
            raw = altered.read_bytes()
            record = {"download_url": "local-fixture-only", "content_sha256": hashlib.sha256(raw).hexdigest()}
            client = SimpleNamespace(binary=lambda *args, **kwargs: (raw, None))
            tracemalloc.start()
            try:
                with self.assertRaises(FullLiveryPackageError) as rejected:
                    CommunityGalleryService._livery_payload(SimpleNamespace(root=root), record, client)
                self.assertIsInstance(rejected.exception.__cause__, decoder.DecodeError)
                self.assertIn("decompressed length", str(rejected.exception.__cause__))
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 4 * 1024 * 1024, f"nested validation allocated {peak} bytes")
            client.binary = lambda *args, **kwargs: (raw[:-10], None)
            with self.assertRaisesRegex(ValueError, "integrity check"):
                CommunityGalleryService._livery_payload(SimpleNamespace(root=root), record, client)
            self.assertEqual({original, altered}, set(root.iterdir()))


if __name__ == "__main__":
    unittest.main()
