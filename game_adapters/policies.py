from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import GameAdapter


@dataclass(frozen=True)
class OfflineSourceAssessment:
    allowed: bool
    status: str
    reason: str = ""
    details: object | None = None


def assess_offline_source(adapter: GameAdapter, source_path: Path) -> OfflineSourceAssessment:
    """Run a game's additional fail-closed file ownership preflight."""

    if adapter.ownership.offline_source_preflight == "fm8_layer_group_files":
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files

        result = assess_fm8_layer_group_files(source_path)
        return OfflineSourceAssessment(
            allowed=bool(result.allowed),
            status=str(result.status),
            reason=str(result.reason),
            details=result,
        )
    return OfflineSourceAssessment(True, "decoder")
