#!/usr/bin/env python3
"""Audit KFPS JSON shape identity against canonical resource mapping."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .cgroup_codec import read_flat_cgroup
    from .shape_identity import canonical_shape_identity, explicit_shape_word
except ImportError:  # pragma: no cover - direct script execution fallback
    from cgroup_codec import read_flat_cgroup
    from shape_identity import canonical_shape_identity, explicit_shape_word


def audit_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list):
        raise ValueError("JSON must contain a shapes list")
    rows = []
    conflicts = []
    word_counts: Counter[int] = Counter()
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            continue
        try:
            identity = canonical_shape_identity(shape)
        except Exception as exc:
            conflicts.append({"index": index, "layer": index + 1, "error": str(exc)})
            continue
        explicit = explicit_shape_word(shape)
        display_word = shape_name_word(shape.get("shape_name"))
        row = {
            "index": index,
            "layer": index + 1,
            "word": identity.word,
            "type": identity.type_code,
            "source": identity.source,
            "explicit_word": explicit,
            "resource_family": shape.get("resource_family"),
            "resource_index": shape.get("resource_index"),
            "shape_name": shape.get("shape_name"),
            "shape_name_word": display_word,
            "conflict": identity.conflict,
        }
        if display_word is not None and display_word != identity.word:
            row["display_conflict"] = f"shape_name says word {display_word}, canonical word is {identity.word}"
        rows.append(row)
        word_counts[identity.word] += 1
        if identity.conflict or row.get("display_conflict"):
            conflicts.append(row)
    return {
        "format": "kfps_shape_identity_audit_v1",
        "source_json": str(path),
        "shape_count": len(rows),
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:200],
        "word_counts_top_32": [{"word": word, "count": count} for word, count in word_counts.most_common(32)],
        "rows_first_64": rows[:64],
    }


def shape_name_word(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\bword\s+(\d+)\b", value, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1)) & 0xFFFF
    except ValueError:
        return None


def compare_cgroup(report: dict[str, Any], cgroup_path: Path) -> None:
    parsed = read_flat_cgroup(cgroup_path)
    json_words = [row["word"] for row in report.get("rows_first_64", [])]
    cgroup_words = [layer["shape_id"] for layer in parsed["layers"][: len(json_words)]]
    mismatches = []
    for index, (json_word, cgroup_word) in enumerate(zip(json_words, cgroup_words)):
        if int(json_word) != int(cgroup_word):
            mismatches.append({"layer": index + 1, "json_word": json_word, "cgroup_word": cgroup_word})
    report["cgroup_compare"] = {
        "cgroup": str(cgroup_path),
        "cgroup_count": parsed["count"],
        "compared_prefix_count": len(cgroup_words),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", type=Path)
    parser.add_argument("--cgroup", type=Path, help="Optional C_group file/folder to compare")
    parser.add_argument("--output", type=Path, help="Write audit report JSON")
    args = parser.parse_args()

    report = audit_json(args.json)
    if args.cgroup:
        compare_cgroup(report, args.cgroup)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
