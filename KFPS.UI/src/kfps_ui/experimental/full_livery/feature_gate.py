from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .qualification import QualificationStatus, evaluate_qualification


STAGES = ("disabled", "preview", "candidate", "stable")


@dataclass(frozen=True)
class FullLiveryFeatureGate:
    stage: str
    source: str
    qualification: QualificationStatus | None = None

    @classmethod
    def resolve(
        cls,
        demo: bool = False,
        *,
        qualification_file: str | Path | None = None,
        app_version: str = "",
    ) -> "FullLiveryFeatureGate":
        requested = os.environ.get("KFPS_FULL_LIVERY_STAGE", "").strip().casefold()
        if requested in STAGES:
            if requested == "stable":
                status = evaluate_qualification(
                    qualification_file or "",
                    app_version=app_version,
                )
                if not status.qualified:
                    return cls("candidate", "qualification-blocked", status)
                return cls("stable", "qualification", status)
            return cls(requested, "environment")
        # Candidate preserves the existing DIRTY workflow while keeping the feature
        # explicitly outside the stable product contract.
        return cls("candidate" if not demo else "preview", "built-in")

    @property
    def enabled(self) -> bool:
        return self.stage != "disabled"

    @property
    def can_preview(self) -> bool:
        return self.stage in {"preview", "candidate", "stable"}

    @property
    def can_export(self) -> bool:
        return self.stage in {"preview", "candidate", "stable"}

    @property
    def can_install(self) -> bool:
        return self.stage in {"candidate", "stable"}

    @property
    def is_stable(self) -> bool:
        return self.stage == "stable"

    def describe(self) -> str:
        if self.source == "qualification-blocked" and self.qualification is not None:
            return "Candidate build: stable status was refused. " + self.qualification.detail
        return {
            "disabled": "Full Liveries are disabled for this build.",
            "preview": "Preview build: scanning, rendering, and package export are available; save installation is gated.",
            "candidate": "Candidate build: the complete workflow is available for testing, but is not marked stable.",
            "stable": "Stable build: the full-livery validation matrix has passed.",
        }[self.stage]
