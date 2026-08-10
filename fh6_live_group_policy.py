"""Fail-closed policy checks for FH6 live vinyl group exports."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Callable, Iterable


_STATE_OFFSET = 0x134
_STATE_SIZE = 4
_CLEAR_STATES = frozenset((0x00, 0x20))
_RESTRICTED_STATE = 0x21
MIN_HEADER_SIZE = _STATE_OFFSET + _STATE_SIZE
DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_GROUPS = 4096


@dataclass(frozen=True)
class LiveGroupPolicyResult:
    allowed: bool
    status: str
    reason: str
    group_count: int
    max_depth: int
    fingerprint: str

    def report(self) -> dict:
        return {
            "passed": bool(self.allowed),
            "status": self.status,
            "group_count": int(self.group_count),
            "max_depth": int(self.max_depth),
            "fingerprint": self.fingerprint,
        }


def classify_group_header(raw: bytes) -> str:
    if len(raw) < MIN_HEADER_SIZE:
        return "unknown"
    state = struct.unpack_from("<I", raw, _STATE_OFFSET)[0]
    # FH6 uses 0x00 for the root/flat object and 0x20 for an owned child group.
    if state in _CLEAR_STATES:
        return "clear"
    if state == _RESTRICTED_STATE:
        return "restricted"
    return "unknown"


def assess_group_tree(
    root_group: int,
    read_header: Callable[[int], bytes],
    read_children: Callable[[int], Iterable[int]],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_groups: int = DEFAULT_MAX_GROUPS,
) -> LiveGroupPolicyResult:
    entries: list[tuple[int, str, tuple[int, ...]]] = []
    seen: set[int] = set()
    active: set[int] = set()
    failure_status = ""
    failure_reason = ""
    deepest = 0

    def fail(status: str, reason: str) -> None:
        nonlocal failure_status, failure_reason
        if not failure_status:
            failure_status = status
            failure_reason = reason

    def walk(group: int, depth: int) -> None:
        nonlocal deepest
        group = int(group)
        deepest = max(deepest, depth)
        if failure_status:
            return
        if depth > max_depth:
            fail("unknown", "The live vinyl hierarchy is deeper than KFPS can verify safely.")
            return
        if group in active:
            fail("unknown", "The live vinyl hierarchy contains a recursive group reference.")
            return
        if group in seen:
            fail("unknown", "The live vinyl hierarchy reuses a group in more than one location.")
            return
        if len(seen) >= max_groups:
            fail("unknown", "The live vinyl hierarchy contains too many groups to verify safely.")
            return

        seen.add(group)
        active.add(group)
        try:
            header = read_header(group)
            status = classify_group_header(header)
            if status == "restricted":
                fail(
                    "restricted",
                    "Export refused: this vinyl contains content that is not owned by the current profile.",
                )
                children: tuple[int, ...] = ()
            elif status != "clear":
                fail("unknown", "KFPS could not verify that every live vinyl group is exportable.")
                children = ()
            else:
                try:
                    children = tuple(int(child) for child in read_children(group))
                except Exception:
                    fail("unknown", "KFPS could not verify the complete live vinyl hierarchy.")
                    children = ()
            entries.append((group, status, children))
            for child in children:
                walk(child, depth + 1)
        except Exception:
            fail("unknown", "KFPS could not read the complete live vinyl hierarchy.")
        finally:
            active.discard(group)

    walk(int(root_group), 0)
    fingerprint_payload = [
        {"group": group, "status": status, "children": list(children)}
        for group, status, children in entries
    ]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()
    if failure_status:
        return LiveGroupPolicyResult(
            allowed=False,
            status=failure_status,
            reason=failure_reason,
            group_count=len(seen),
            max_depth=deepest,
            fingerprint=fingerprint,
        )
    return LiveGroupPolicyResult(
        allowed=True,
        status="clear",
        reason="",
        group_count=len(seen),
        max_depth=deepest,
        fingerprint=fingerprint,
    )
