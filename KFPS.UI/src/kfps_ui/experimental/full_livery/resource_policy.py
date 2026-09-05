from __future__ import annotations

from dataclasses import dataclass

MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class LiveryMemoryBudget:
    worker_bytes: int
    viewer_bytes: int
    reserve_bytes: int

    @classmethod
    def for_memory(cls, total: int, available: int) -> "LiveryMemoryBudget":
        total = max(GIB, int(total))
        available = max(0, int(available))
        return cls(
            worker_bytes=int(max(768 * MIB, min(6 * GIB, total * .20, available * .45))),
            viewer_bytes=int(max(384 * MIB, min(2 * GIB, total * .12, available * .35))),
            reserve_bytes=int(max(256 * MIB, min(GIB, total * .05))),
        )

    def viewer_failure(self, resident: int, gpu_growth: int, available: int) -> str:
        usage = max(0, resident) + max(0, gpu_growth)
        if usage > self.viewer_bytes:
            return "viewer memory budget exceeded"
        if available < self.reserve_bytes and usage > 256 * MIB:
            return "system memory reserve exhausted"
        return ""

    def worker_limit(self, operation: str) -> int:
        # Only preview preparation adopts the new adaptive budget. Existing
        # package import/export jobs retain their previous limit.
        return self.worker_bytes if operation in {"prepare-mesh", "preview-source"} else 6 * GIB
