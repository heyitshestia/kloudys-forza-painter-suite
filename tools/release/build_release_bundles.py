from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile


APP_FOLDER = "KloudysFH6Painter"
FORBIDDEN_PARTS = {
    ".git",
    ".wrangler",
    "__pycache__",
    "node_modules",
    "runtime",
    "webui-data",
}
FORBIDDEN_SUFFIXES = (".kfpskey", ".pyc")
FORBIDDEN_NAMES = {
    ".dev.vars",
    "relay-state.dat",
    "rtti-enrollment.json",
}
PRESERVED_IMAGE_DIRS = {
    PurePosixPath("imgs/generated"),
    PurePosixPath("imgs/exported"),
    PurePosixPath("imgs/editor"),
    PurePosixPath("imgs/library"),
    PurePosixPath("imgs/luma-bands"),
    PurePosixPath("imgs/handmade"),
}


def _run_git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def resolve_commit(repo: Path, revision: str) -> str:
    return str(_run_git(repo, "rev-parse", f"{revision}^{{commit}}")).strip()


def commit_timestamp(repo: Path, commit: str) -> int:
    return int(str(_run_git(repo, "show", "-s", "--format=%ct", commit)).strip())


def read_version(repo: Path, commit: str) -> str:
    version = str(_run_git(repo, "show", f"{commit}:VERSION")).strip()
    if not version or any(character not in "0123456789." for character in version):
        raise RuntimeError(f"VERSION at {commit} is invalid: {version!r}")
    return version


def require_clean_tracked_tree(repo: Path) -> None:
    status = str(_run_git(repo, "status", "--porcelain", "--untracked-files=no")).strip()
    if status:
        raise RuntimeError("Tracked files are modified. Commit or restore them before building a release.")


def _safe_tar_members(bundle: tarfile.TarFile, destination: Path):
    destination = destination.resolve()
    for member in bundle.getmembers():
        target = (destination / member.name).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise RuntimeError(f"Git archive contains an unsafe path: {member.name}") from exc
        if member.issym() or member.islnk():
            raise RuntimeError(f"Release archives may not contain links: {member.name}")
        yield member


def export_commit(repo: Path, commit: str, destination: Path) -> None:
    archive = _run_git(repo, "archive", "--format=tar", commit, text=False)
    tar_path = destination.parent / "tracked.tar"
    tar_path.write_bytes(archive)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:") as bundle:
        bundle.extractall(destination, members=_safe_tar_members(bundle, destination), filter="data")


def _is_forbidden(relative: PurePosixPath) -> bool:
    lowered = PurePosixPath(*(part.lower() for part in relative.parts))
    if any(part in FORBIDDEN_PARTS for part in lowered.parts):
        return True
    if lowered.name in FORBIDDEN_NAMES or (
        lowered.name.startswith(".dev.vars.") and lowered.name != ".dev.vars.example"
    ):
        return True
    if lowered.name.endswith(FORBIDDEN_SUFFIXES):
        return True
    return any(lowered == root or root in lowered.parents for root in PRESERVED_IMAGE_DIRS)


def enforce_release_policy(app_root: Path) -> None:
    violations = []
    for path in app_root.rglob("*"):
        relative = PurePosixPath(path.relative_to(app_root).as_posix())
        if _is_forbidden(relative):
            violations.append(relative.as_posix())
    if violations:
        preview = "\n".join(f"  {item}" for item in violations[:25])
        raise RuntimeError(f"Release source contains forbidden runtime/personal paths:\n{preview}")


def copy_python_runtime(source: Path, destination: Path) -> None:
    source = source.resolve()
    if not (source / "python.exe").is_file():
        raise RuntimeError(f"Bundled runtime is missing python.exe: {source}")
    for path in source.rglob("*"):
        if path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path)):
            raise RuntimeError(f"Bundled runtime may not contain links or junctions: {path}")
        relative = PurePosixPath(path.relative_to(source).as_posix())
        lowered = PurePosixPath(*(part.lower() for part in relative.parts))
        if (
            lowered.name.endswith(".kfpskey")
            or lowered.name in FORBIDDEN_NAMES
            or lowered.name.startswith(".dev.vars.")
        ):
            raise RuntimeError(f"Bundled runtime contains personal or secret state: {relative}")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _normalized_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def _python_runtime_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    return environment


def locked_python_distributions(requirements_lock: Path) -> dict[str, str]:
    locked = {}
    for raw in requirements_lock.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        requirement = line.split(";", 1)[0].strip()
        name, version = requirement.split("==", 1)
        locked[_normalized_distribution(name)] = version.strip()
    if not locked:
        raise RuntimeError(f"No exact Python requirements were found in {requirements_lock}.")
    return locked


def installed_python_distributions(source: Path) -> dict[str, str]:
    python = source.resolve() / "python.exe"
    result = subprocess.run(
        [str(python), "-m", "pip", "--isolated", "list", "--format=json"],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_python_runtime_environment(),
    )
    values = json.loads(result.stdout)
    return {
        _normalized_distribution(str(item["name"])): str(item["version"])
        for item in values if isinstance(item, dict) and item.get("name") and item.get("version")
    }


def _is_optional_record_path(relative: PurePosixPath) -> bool:
    return relative.suffix.lower() == ".pyc" or "__pycache__" in relative.parts


def _record_hash(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise RuntimeError(f"Unsupported Python RECORD hash algorithm: {algorithm}") from exc
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode("ascii")


def validate_python_distribution_records(source: Path) -> None:
    source = source.resolve()
    site_packages = source / "Lib" / "site-packages"
    if not site_packages.is_dir():
        raise RuntimeError(f"Bundled runtime is missing site-packages: {site_packages}")

    issues = []
    distributions = sorted(site_packages.glob("*.dist-info"), key=lambda path: path.name.lower())
    if not distributions:
        raise RuntimeError(f"Bundled runtime contains no Python distribution metadata: {site_packages}")

    for dist_info in distributions:
        record_path = dist_info / "RECORD"
        if not record_path.is_file():
            issues.append(f"{dist_info.name}: missing RECORD")
            continue
        with record_path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            records = csv.reader(stream)
            for row in records:
                if not row:
                    continue
                relative_text, hash_field, size_field = (row + ["", ""])[:3]
                relative = PurePosixPath(relative_text)
                if _is_optional_record_path(relative):
                    continue
                if not relative_text or relative.is_absolute():
                    issues.append(f"{dist_info.name}: unsafe path {relative_text!r}")
                    continue
                target = (site_packages / Path(*relative.parts)).resolve()
                try:
                    target.relative_to(source)
                except ValueError:
                    issues.append(f"{dist_info.name}: unsafe path {relative_text}")
                    continue
                if not target.is_file():
                    issues.append(f"{dist_info.name}: missing {relative_text}")
                    continue
                if size_field:
                    try:
                        expected_size = int(size_field)
                    except ValueError:
                        issues.append(f"{dist_info.name}: invalid size for {relative_text}")
                    else:
                        if target.stat().st_size != expected_size:
                            issues.append(f"{dist_info.name}: size mismatch for {relative_text}")
                if hash_field:
                    if "=" not in hash_field:
                        issues.append(f"{dist_info.name}: invalid hash for {relative_text}")
                        continue
                    algorithm, expected_hash = hash_field.split("=", 1)
                    if _record_hash(target, algorithm) != expected_hash:
                        issues.append(f"{dist_info.name}: hash mismatch for {relative_text}")

    if issues:
        preview = "\n".join(f"  {issue}" for issue in issues[:30])
        remainder = len(issues) - 30
        suffix = f"\n  ... and {remainder} more" if remainder > 0 else ""
        raise RuntimeError(f"Bundled Python contains incomplete or modified package files:\n{preview}{suffix}")


def validate_python_runtime_apis(source: Path) -> None:
    source = source.resolve()
    python = source / "python.exe"
    probe = r"""
import pathlib

import cv2
import numpy
from PIL import Image
import psutil
from PySide6 import (
    QtCore,
    QtGui,
    QtNetwork,
    QtQml,
    QtQuick,
    QtQuickControls2,
    QtTest,
    QtWebEngineQuick,
    QtWidgets,
)
import shiboken6
import win32api

assert pathlib.Path(cv2.__file__).is_file()
assert cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)).shape == (3, 3)
pixels = numpy.zeros((2, 2, 3), dtype=numpy.uint8)
encoded_ok, encoded = cv2.imencode(".png", pixels)
assert encoded_ok and cv2.imdecode(encoded, cv2.IMREAD_COLOR).shape == pixels.shape
assert Image.fromarray(pixels).size == (2, 2)
assert psutil.Process().pid > 0
assert shiboken6.__version__
assert win32api.GetVersionEx()[0] >= 10
app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
image = QtGui.QImage(2, 2, QtGui.QImage.Format_RGBA8888)
image.fill(QtGui.QColor("red"))
assert not image.isNull() and QtCore.qVersion()
print("KFPS bundled Python API probe passed.")
"""
    environment = _python_runtime_environment()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [str(python), "-c", probe], capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=environment,
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(f"Bundled Python API validation failed:\n{detail}")


def validate_python_runtime(source: Path, requirements_lock: Path) -> None:
    source = source.resolve()
    python = source / "python.exe"
    if not python.is_file():
        raise RuntimeError(f"Bundled runtime is missing python.exe: {source}")
    subprocess.run(
        [str(python), "-m", "pip", "--isolated", "check"], check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_python_runtime_environment(),
    )
    locked = locked_python_distributions(requirements_lock)
    installed = installed_python_distributions(source)
    wrong = {
        name: {"expected": version, "installed": installed.get(name, "missing")}
        for name, version in locked.items() if installed.get(name) != version
    }
    allowed = set(locked) | {"pip", "setuptools", "wheel"}
    extras = sorted(set(installed) - allowed)
    if wrong or extras:
        raise RuntimeError(
            "Bundled Python does not match requirements.lock.txt: "
            + json.dumps({"wrong_or_missing": wrong, "unexpected": extras}, sort_keys=True)
        )
    validate_python_distribution_records(source)
    validate_python_runtime_apis(source)


def synchronize_python_runtime(source: Path, requirements_lock: Path) -> None:
    source = source.resolve()
    python = source / "python.exe"
    locked = locked_python_distributions(requirements_lock)
    installed = installed_python_distributions(source)
    extras = sorted(set(installed) - set(locked) - {"pip", "setuptools", "wheel"})
    environment = _python_runtime_environment()
    if extras:
        subprocess.run(
            [str(python), "-m", "pip", "--isolated", "uninstall", "-y", *extras],
            check=True, env=environment,
        )
    subprocess.run([
        str(python), "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
        "--no-warn-script-location", "--upgrade", "--force-reinstall", "--no-deps",
        "-r", str(requirements_lock.resolve()),
    ], check=True, env=environment)
    validate_python_runtime(source, requirements_lock)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path, *, version: str, commit: str, kind: str, timestamp: int) -> Path:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "RELEASE-MANIFEST.json":
            continue
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "schema": "kfps.release-manifest.v1",
        "version": version,
        "commit": commit,
        "kind": kind,
        "source_timestamp_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "files": files,
    }
    target = root / "RELEASE-MANIFEST.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def verify_manifest(root: Path) -> None:
    manifest_path = root / "RELEASE-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {record["path"]: record for record in manifest["files"]}
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if set(expected) != set(actual):
        raise RuntimeError("Release manifest inventory does not match staged files.")
    for relative, path in actual.items():
        record = expected[relative]
        if path.stat().st_size != record["size"] or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Release manifest verification failed: {relative}")


def write_deterministic_zip(source_root: Path, target: Path, timestamp: int) -> None:
    date_time = datetime.fromtimestamp(timestamp, timezone.utc).timetuple()[:6]
    if date_time[0] < 1980:
        date_time = (1980, 1, 1, 0, 0, 0)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(source_root.rglob("*")):
            relative = path.relative_to(source_root.parent).as_posix()
            if path.is_dir():
                info = zipfile.ZipInfo(relative.rstrip("/") + "/", date_time=date_time)
                info.external_attr = (0o40755 << 16) | 0x10
                bundle.writestr(info, b"")
                continue
            info = zipfile.ZipInfo(relative, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_one(
    repo: Path,
    output_dir: Path,
    *,
    commit: str,
    version: str,
    timestamp: int,
    kind: str,
    python_source: Path | None,
) -> Path:
    if kind not in {"recommended", "advanced"}:
        raise ValueError(f"Unsupported release kind: {kind}")
    asset_name = (
        f"KFPS-{version}-bundled.zip"
        if kind == "recommended"
        else f"KFPS-{version}-ADVANCED-NO-PYTHON-NO-DEPENDENCIES.zip"
    )
    with tempfile.TemporaryDirectory(prefix="kfps-release-") as temporary:
        temporary_root = Path(temporary)
        exported = temporary_root / "exported"
        export_commit(repo, commit, exported)
        enforce_release_policy(exported)

        release_root = temporary_root / f"KFPS-{version}"
        app_root = release_root / APP_FOLDER
        shutil.copytree(exported, app_root)
        (app_root / "BUILD_COMMIT").write_text(commit + "\n", encoding="ascii")
        shutil.copy2(app_root / "KFPS.exe", release_root / "KFPS.exe")
        updater = app_root / "KFPS-Updater.exe"
        if not updater.is_file():
            raise RuntimeError("Release source is missing KFPS-Updater.exe.")
        shutil.copy2(updater, release_root / "KFPS-Updater.exe")
        (release_root / "Images").mkdir()

        if kind == "recommended":
            if python_source is None:
                raise RuntimeError("The recommended bundle requires --python-source.")
            sanitized_runtime = temporary_root / "python-runtime"
            copy_python_runtime(python_source, sanitized_runtime)
            synchronize_python_runtime(sanitized_runtime, app_root / "requirements.lock.txt")
            copy_python_runtime(sanitized_runtime, app_root / "python")
            validate_python_runtime(app_root / "python", app_root / "requirements.lock.txt")

        write_manifest(release_root, version=version, commit=commit, kind=kind, timestamp=timestamp)
        verify_manifest(release_root)
        target = output_dir / asset_name
        write_deterministic_zip(release_root, target, timestamp)
        (output_dir / f"{asset_name}.sha256").write_text(
            f"{sha256_file(target)}  {asset_name}\n", encoding="ascii"
        )
        return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic KFPS GitHub release bundles.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--kind", choices=("recommended", "advanced", "all"), default="all")
    parser.add_argument("--python-source", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    if not args.allow_dirty:
        require_clean_tracked_tree(repo)
    commit = resolve_commit(repo, args.commit)
    version = read_version(repo, commit)
    timestamp = commit_timestamp(repo, commit)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    kinds = ("recommended", "advanced") if args.kind == "all" else (args.kind,)
    for kind in kinds:
        target = build_one(
            repo,
            output_dir,
            commit=commit,
            version=version,
            timestamp=timestamp,
            kind=kind,
            python_source=args.python_source,
        )
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
