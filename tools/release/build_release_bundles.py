from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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
    if lowered.name in FORBIDDEN_NAMES or lowered.name.startswith(".dev.vars."):
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
    shutil.copytree(source, destination)


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
        (release_root / "Images").mkdir()

        if kind == "recommended":
            if python_source is None:
                raise RuntimeError("The recommended bundle requires --python-source.")
            copy_python_runtime(python_source, app_root / "python")

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
