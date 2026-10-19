"""Bounded converter input/output identity; portable roots, not fabricated Git state."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

REFERENCE = "33de8f5589519c6e9320617eb3c148fb602ab5ff"
PIN_PATH = "src/chassis-converter/baseline-prerequisites.json"
PIN_SHA256 = "192fe644c685c90bf7a1e49eb4a15fc125fe02a85ad37cfb78f0be8851290a97"
VENDOR = "tools/livery/chassis-converter/vendor/ForzaTechStudio"
FORMAT = "kfps-converter-build-v2"
MAX_METADATA = 1024 * 1024
MAX_SOURCE = 8 * 1024 * 1024
MAX_ARTIFACT = 256 * 1024 * 1024


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate provenance JSON key.")
        result[key] = value
    return result


def read_json(path):
    with Path(path).open("rb") as stream:
        body = stream.read(MAX_METADATA + 1)
    if len(body) > MAX_METADATA:
        raise ValueError("Converter metadata is too large.")
    value = json.loads(body.decode("utf-8-sig"), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("Converter metadata must be an object.")
    return value


def safe_file(root, relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute() or any(p in ("", ".", "..") for p in relative.split("/"))):
        raise ValueError("Invalid converter provenance path.")
    root = Path(root).absolute()
    path = root.joinpath(*relative.split("/"))
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Converter provenance cannot follow redirected paths.")
        if item == root:
            break
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Converter provenance file is missing or outside its root.")
    return path


def fingerprint(path, limit=MAX_SOURCE):
    path = Path(path)
    before = path.stat()
    if before.st_size > limit:
        raise ValueError("Converter input/output exceeds its size limit.")
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(min(1024 * 1024, limit + 1 - count)):
            count += len(chunk)
            if count > limit:
                raise ValueError("Converter input/output grew past its size limit.")
            digest.update(chunk)
    after = path.stat()
    stamp = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if count != before.st_size or stamp(before) != stamp(after):
        raise ValueError("Converter input/output changed while hashing.")
    return {"bytes": count, "sha256": digest.hexdigest()}


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                                timeout=15, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _files(root, relative, *, recursive=False):
    directory = Path(root) / relative
    if not directory.is_dir() or directory.is_symlink() or directory.is_junction():
        raise ValueError("Converter input directory is missing or redirected.")
    result = []
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    for path in iterator:
        if path.is_symlink() or path.is_junction():
            raise ValueError("Converter input directory contains a redirected path.")
        if path.is_file():
            result.append(path.relative_to(root).as_posix())
            if len(result) > 256:
                raise ValueError("Too many converter input files.")
    return sorted(result)


def verify_prerequisites(lab, baseline):
    pin_file = safe_file(lab, PIN_PATH)
    if fingerprint(pin_file)["sha256"] != PIN_SHA256:
        raise ValueError("The reviewed converter prerequisite inventory changed.")
    pins = read_json(pin_file)
    if pins.get("format") != "kfps-converter-prerequisites-v1" or pins.get("reference_commit") != REFERENCE:
        raise ValueError("Unknown converter prerequisite provenance.")
    records = pins.get("files")
    if not isinstance(records, list) or not 1 <= len(records) <= 128:
        raise ValueError("Invalid converter prerequisite inventory.")
    expected = {}
    for row in records:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256", "compiled"}:
            raise ValueError("Invalid converter prerequisite entry.")
        path = row["path"]
        if not isinstance(path, str) or not path.startswith(VENDOR + "/") or path in expected:
            raise ValueError("Duplicate or unexpected converter prerequisite.")
        actual = fingerprint(safe_file(baseline, path))
        if type(row["bytes"]) is not int or actual != {"bytes": row["bytes"], "sha256": row["sha256"]}:
            raise ValueError("A pinned baseline converter prerequisite changed: " + path)
        expected[path] = row
    compiled = {p for p in _files(baseline, VENDOR, recursive=True)
                if p.casefold().endswith(".cs") and p.casefold() != (VENDOR + "/ModelImporter.cs").casefold()
                and not {"obj", "bin"}.intersection(part.casefold() for part in PurePosixPath(p).parts)}
    if compiled != {p for p, row in expected.items() if row["compiled"] is True}:
        raise ValueError("Baseline converter compile inputs differ from the reviewed inventory.")
    return sorted(expected)


def source_records(lab, baseline, *, tests=False):
    baseline_paths = verify_prerequisites(lab, baseline)
    lab_paths = _files(lab, "src/chassis-converter") + [
        "scripts/build-converter.ps1", "scripts/resolve-baseline.ps1",
        "src/kfps_livery_lab/converter_provenance.py"]
    if tests:
        lab_paths.append("tests/ConverterTests.cs")
    rows = []
    for label, root, paths in (("lab", lab, lab_paths), ("baseline", baseline, baseline_paths)):
        for path in sorted(paths):
            rows.append({"root": label, "path": path, **fingerprint(safe_file(root, path))})
    return rows


def inspect_inputs(lab, baseline, mode, *, tests=False):
    if mode not in ("development", "pinned"):
        raise ValueError("Choose development or pinned prerequisite mode.")
    observed = _git(baseline, "rev-parse", "HEAD")
    if observed is not None and not re.fullmatch(r"[0-9a-f]{40}", observed):
        raise ValueError("Invalid observed Git identity.")
    if mode == "development":
        if observed != REFERENCE:
            raise ValueError("Development converter builds require the exact qualified baseline HEAD.")
        if _git(baseline, "status", "--porcelain", "--", "tools/livery/chassis-converter") != "":
            raise ValueError("Development baseline converter has local changes or cannot be inspected.")
    return {"format": FORMAT, "mode": mode, "kind": "tests" if tests else "converter",
            "provenance": {"reference_commit": REFERENCE, "observed_git_head": observed,
                           "prerequisite_inventory_sha256": PIN_SHA256},
            "sources": source_records(lab, baseline, tests=tests)}


def _build_root(lab, build):
    build = Path(build).absolute()
    runs = (Path(lab) / "runs").absolute()
    if build == runs or not build.resolve().is_relative_to(runs.resolve()):
        raise ValueError("Converter build must stay in a named Studio runs directory.")
    for item in (build, *build.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Converter build path is redirected.")
        if item == runs:
            break
    return build


def artifact_records(build, *, tests=False):
    paths = _files(build, "publish")
    expected = "publish/Kfps.LiveryLab.Converter" + (".Tests" if tests else "") + ".exe"
    if expected not in paths or len(paths) > 32 or any(p.is_dir() for p in (Path(build) / "publish").iterdir()):
        raise ValueError("Converter publish output is incomplete or has unexpected directories.")
    return [{"root": "build", "path": p, **fingerprint(safe_file(build, p), MAX_ARTIFACT)} for p in paths]


def finish_build(lab, baseline, build, snapshot):
    build = _build_root(lab, build)
    if snapshot.get("format") != FORMAT or snapshot.get("kind") not in ("converter", "tests"):
        raise ValueError("Invalid converter pre-build snapshot.")
    current = inspect_inputs(lab, baseline, snapshot.get("mode"), tests=snapshot["kind"] == "tests")
    if current != snapshot:
        raise ValueError("Converter inputs or provenance changed during compilation; rebuild required.")
    return {**snapshot, "artifacts": artifact_records(build, tests=snapshot["kind"] == "tests"),
            "assurance": "Exact source/build byte integrity, not a game-render parity claim."}


def _verify_legacy(lab, baseline, build, manifest):
    # Compatibility is bounded to the original complete input layout, never an arbitrary subset.
    own = set(_files(lab, "src/chassis-converter")) - {PIN_PATH}
    expected = {safe_file(lab, p).resolve() for p in own | {"scripts/build-converter.ps1"}}
    vendor = {p for p in _files(baseline, VENDOR, recursive=True)
              if p.casefold().endswith(".cs") and p.casefold() != (VENDOR + "/ModelImporter.cs").casefold()
              and not {"obj", "bin"}.intersection(part.casefold() for part in PurePosixPath(p).parts)}
    expected.update(safe_file(baseline, p).resolve() for p in vendor)
    records = manifest.get("sources")
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError("Incomplete legacy converter source inventory.")
    seen = set()
    for row in records:
        path = Path(row["path"]).resolve(strict=True)
        if path not in expected or path in seen or fingerprint(path)["sha256"] != row["sha256"]:
            raise ValueError("Legacy converter source identity changed.")
        seen.add(path)
    current = artifact_records(build)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(current):
        raise ValueError("Incomplete legacy converter artifact inventory.")
    expected_outputs = {str((build / row["path"]).resolve()): row for row in current}
    seen = set()
    for row in artifacts:
        path = str(Path(row["path"]).resolve(strict=True))
        if path not in expected_outputs or path in seen or row.get("sha256") != expected_outputs[path]["sha256"]:
            raise ValueError("Legacy converter output identity changed.")
        seen.add(path)


def verify_build(lab, baseline, build):
    build = _build_root(lab, build)
    manifest = read_json(safe_file(build, "build-manifest.json"))
    if manifest.get("format") == "kfps-isolated-converter-build-v1":
        _verify_legacy(lab, baseline, build, manifest)
    else:
        if (manifest.get("format") != FORMAT or manifest.get("kind") != "converter"
                or manifest.get("mode") not in ("development", "pinned")):
            raise ValueError("Unsupported converter build provenance.")
        provenance = manifest.get("provenance")
        if (not isinstance(provenance, dict) or provenance.get("reference_commit") != REFERENCE
                or provenance.get("prerequisite_inventory_sha256") != PIN_SHA256
                or (provenance.get("observed_git_head") is not None
                    and not re.fullmatch(r"[0-9a-f]{40}", str(provenance["observed_git_head"])))):
            raise ValueError("Invalid converter baseline provenance.")
        if manifest.get("sources") != source_records(lab, baseline):
            raise ValueError("Converter sources changed after this build.")
        if manifest.get("artifacts") != artifact_records(build):
            raise ValueError("Converter output changed after this build.")
    return safe_file(build, "publish/Kfps.LiveryLab.Converter.exe")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "finish", "verify"))
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--mode", choices=("development", "pinned"), default="development")
    parser.add_argument("--build", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    if args.action == "inspect":
        result = inspect_inputs(args.lab, args.baseline, args.mode, tests=args.tests)
    elif args.action == "finish":
        build = _build_root(args.lab, args.build)
        snapshot = Path(args.snapshot).absolute()
        if snapshot.parent != build or snapshot.name != "source-inputs.json":
            raise ValueError("Converter snapshot must be its named build-local input record.")
        result = finish_build(args.lab, args.baseline, build, read_json(safe_file(build, snapshot.name)))
    else:
        result = {"verified": True, "executable": str(verify_build(args.lab, args.baseline, args.build))}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
