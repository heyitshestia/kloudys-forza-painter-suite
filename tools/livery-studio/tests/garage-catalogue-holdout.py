"""Read-only catalogue coverage on existing car geometry, not fitted-build proof."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools/livery-studio/src")]
from kfps_livery_lab.part_names import load_part_names
from kfps_livery_lab.garage_build import BODY_PARTS
from kfps_livery_lab.prepare import atomic_json, file_hash
from tools.livery.portable_mesh_converter import _glb_payloads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("Evidence must stay in the local runtime directory")
    fixtures = [(ROOT / "tools/livery-studio/runs/grouped-sections-20261021/cars" / f"c{i}/prepared")
                for i in range(1, 5)]
    records = []
    for directory in fixtures:
        prepared = json.loads((directory / "prepared.json").read_bytes())
        vehicle = {key: prepared["editor_config"]["vehicle"][key] for key in ("car_id", "model_code")}
        mesh = directory / prepared["files"]["mesh"]
        before = file_hash(mesh)
        document, _ = _glb_payloads(mesh)
        options = document["scenes"][document.get("scene", 0)]["extras"]["kfps_part_options"]
        start = time.perf_counter()
        names = load_part_names(args.game_root, vehicle, options)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        assert names["same_build_verified"] is True and names["provenance"]["current"] is True
        declared = {(row["part_type"], row["id"]) for row in options}
        assert declared.issubset({(row["part_type"], row["id"]) for row in names["names"]})
        assert before == file_hash(mesh), "Source geometry changed"
        records.append({"vehicle": vehicle, "declaredOptions": len(declared),
            "resolvedNames": sum(row["status"] == "resolved" for row in names["names"]),
            "unresolved": [row for row in names["names"] if row["status"] != "resolved"],
            "undeclaredGroups": [part for part in BODY_PARTS if not any(p == part for p, _ in declared)],
            "nonvisualOptions": len(names["non_visual_options"]), "elapsedMs": elapsed,
            "sourceUnchanged": True, "warnings": names["warnings"]})
    result = {"qualification": "installed catalogue labels on existing geometry only; no owned-build or in-game claim",
              "cars": records}
    atomic_json(output, result)
    assert json.loads(output.read_bytes()) == result
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
