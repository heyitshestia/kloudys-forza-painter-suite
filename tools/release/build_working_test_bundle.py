from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from build_release_bundles import (
    APP_FOLDER,
    copy_python_runtime,
    enforce_release_policy,
    sha256_file,
    synchronize_python_runtime,
    validate_python_runtime,
    verify_manifest,
    write_deterministic_zip,
    write_manifest,
)


PORTABLE_NODE_VERSION = "22.23.2"
PORTABLE_NODE_ARCHIVE = f"node-v{PORTABLE_NODE_VERSION}-win-x64.zip"
PORTABLE_NODE_URL = f"https://nodejs.org/dist/v{PORTABLE_NODE_VERSION}/{PORTABLE_NODE_ARCHIVE}"
PORTABLE_NODE_SHA256 = "1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97"


def git(repo: Path, *arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], check=True, capture_output=True,
        text=not binary,
    )
    return result.stdout


def worktree_files(repo: Path) -> list[PurePosixPath]:
    raw = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", binary=True)
    files = []
    for value in bytes(raw).split(b"\0"):
        if not value:
            continue
        relative = PurePosixPath(value.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Unsafe worktree path: {relative}")
        source = repo / Path(*relative.parts)
        if source.is_file():
            if source.is_symlink():
                raise RuntimeError(f"Test bundles may not contain links: {relative}")
            files.append(relative)
    return sorted(set(files))


def copy_worktree(repo: Path, destination: Path) -> list[PurePosixPath]:
    files = worktree_files(repo)
    for relative in files:
        source = repo / Path(*relative.parts)
        target = destination / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return files


def inventory_hash(root: Path, files: list[PurePosixPath]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        path = root / Path(*relative.parts)
        digest.update(relative.as_posix().encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def extract_python(bundle: Path, destination: Path) -> Path:
    with zipfile.ZipFile(bundle) as archive:
        matches = [
            name for name in archive.namelist()
            if f"/{APP_FOLDER}/python/" in "/" + name.replace("\\", "/") and not name.endswith("/")
        ]
        if not matches:
            raise RuntimeError(f"No bundled KFPS Python runtime was found in {bundle}.")
        markers = {name.split(f"/{APP_FOLDER}/python/", 1)[0] for name in matches}
        if len(markers) != 1:
            raise RuntimeError("Python source bundle contains more than one KFPS application root.")
        destination.mkdir(parents=True)
        prefix = next(iter(markers)) + f"/{APP_FOLDER}/python/"
        for name in matches:
            relative = PurePosixPath(name[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"Unsafe Python archive path: {name}")
            target = destination / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return destination


def acquire_portable_node(bundle: Path | None, destination: Path) -> Path:
    archive = bundle.resolve() if bundle else destination / PORTABLE_NODE_ARCHIVE
    if bundle is None:
        request = urllib.request.Request(PORTABLE_NODE_URL, headers={"User-Agent": "KFPS-Test-Bundle-Builder/1"})
        with urllib.request.urlopen(request, timeout=120) as source, archive.open("wb") as output:
            shutil.copyfileobj(source, output)
    digest = sha256_file(archive)
    if digest != PORTABLE_NODE_SHA256:
        raise RuntimeError(
            f"Portable Node archive checksum mismatch: expected {PORTABLE_NODE_SHA256}, received {digest}."
        )

    extracted = destination / "node-extracted"
    extracted.mkdir()
    with zipfile.ZipFile(archive) as package:
        bad = package.testzip()
        if bad:
            raise RuntimeError(f"Portable Node archive is corrupt at {bad}.")
        files = [name for name in package.namelist() if not name.endswith("/")]
        roots = {PurePosixPath(name).parts[0] for name in files}
        expected_root = f"node-v{PORTABLE_NODE_VERSION}-win-x64"
        if roots != {expected_root}:
            raise RuntimeError(f"Portable Node archive has unexpected roots: {sorted(roots)}")
        for name in files:
            relative = PurePosixPath(name).relative_to(expected_root)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"Unsafe portable Node archive path: {name}")
            target = extracted / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(name) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    if not (extracted / "node.exe").is_file() or not (extracted / "npm.cmd").is_file():
        raise RuntimeError("Portable Node archive does not contain node.exe and npm.cmd.")
    version = subprocess.run(
        [str(extracted / "node.exe"), "--version"], check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()
    if version != f"v{PORTABLE_NODE_VERSION}":
        raise RuntimeError(f"Portable Node version mismatch: {version}")
    return extracted


def install_worker_dependencies(worker_root: Path, node_root: Path) -> None:
    environment = os.environ.copy()
    environment.update({
        "CI": "true",
        "NO_COLOR": "1",
        "PATH": str(node_root) + os.pathsep + environment.get("PATH", ""),
        "npm_config_audit": "false",
        "npm_config_fund": "false",
    })
    subprocess.run(
        [str(node_root / "npm.cmd"), "ci", "--no-audit", "--no-fund"],
        cwd=worker_root, env=environment, check=True,
    )
    wrangler = worker_root / "node_modules" / ".bin" / "wrangler.cmd"
    if not wrangler.is_file():
        raise RuntimeError("The packaged Worker dependencies do not contain Wrangler.")
    subprocess.run(
        [str(node_root / "npm.cmd"), "run", "typecheck"],
        cwd=worker_root, env=environment, check=True,
    )
    subprocess.run(
        [str(node_root / "npm.cmd"), "test"],
        cwd=worker_root, env=environment, check=True,
    )
    for path in (node_root, worker_root / "node_modules"):
        for item in path.rglob("*"):
            if item.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(item)):
                raise RuntimeError(f"Portable test dependencies may not contain links or junctions: {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a non-release KFPS bundle from the current working tree.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--python-source", type=Path)
    source.add_argument("--python-bundle", type=Path)
    parser.add_argument("--refresh-python-runtime", action="store_true")
    parser.add_argument(
        "--node-bundle", type=Path,
        help=f"Optional cached official {PORTABLE_NODE_ARCHIVE}; otherwise it is downloaded and verified.",
    )
    parser.add_argument("--label", default="Community-Staging-Test")
    args = parser.parse_args()

    repo = args.repo.resolve()
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    commit = str(git(repo, "rev-parse", "HEAD")).strip()
    timestamp = int(datetime.now(timezone.utc).timestamp())
    date = datetime.now().strftime("%Y-%m-%d")
    safe_label = "-".join(part for part in args.label.replace("_", "-").split("-") if part)
    folder_name = f"KFPS-{version}-{safe_label}-{date}"
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kfps-working-test-bundle-") as temporary:
        temporary_root = Path(temporary)
        source_root = temporary_root / "source"
        source_root.mkdir()
        files = copy_worktree(repo, source_root)
        enforce_release_policy(source_root)
        state_hash = inventory_hash(source_root, files)

        release_root = temporary_root / folder_name
        app_root = release_root / APP_FOLDER
        shutil.copytree(source_root, app_root)
        (app_root / "BUILD_COMMIT").write_text(commit + "\n", encoding="ascii")
        shutil.copy2(app_root / "KFPS.exe", release_root / "KFPS.exe")
        (release_root / "Images").mkdir()

        if args.python_source:
            python_source = args.python_source.resolve()
        else:
            python_source = extract_python(args.python_bundle.resolve(), temporary_root / "python-source")
        if args.refresh_python_runtime:
            synchronize_python_runtime(python_source, app_root / "requirements.lock.txt")
        validate_python_runtime(python_source, app_root / "requirements.lock.txt")
        copy_python_runtime(python_source, app_root / "python")

        node_source = acquire_portable_node(args.node_bundle, temporary_root)
        worker_root = app_root / "tools" / "community_worker"
        node_target = worker_root / ".node"
        shutil.copytree(node_source, node_target)
        install_worker_dependencies(worker_root, node_target)

        outer_launcher = release_root / "Run_Community_Validation.bat"
        outer_launcher.write_text(
            "@echo off\r\n"
            "call \"%~dp0KloudysFH6Painter\\Run_Community_Validation.bat\"\r\n"
            "exit /b %ERRORLEVEL%\r\n",
            encoding="ascii",
        )
        (release_root / "TESTING-README.txt").write_text(
            "KFPS Community staging test build\n\n"
            "1. Extract the complete ZIP.\n"
            "2. Open KFPS.exe for normal application testing.\n"
            "3. Open Run_Community_Validation.bat. It performs three disposable local runs.\n"
            "4. Send the ZIP created under KloudysFH6Painter\\Community-Test-Reports.\n\n"
            "Python, Node.js, and all validation dependencies are included. No development tools are required.\n"
            "Normal KFPS operation does not use or require the bundled Node.js validation runtime.\n"
            "The validation never deploys or changes the production Community Worker.\n"
            "This is a non-release working-tree build and must not be redistributed as a stable release.\n",
            encoding="utf-8",
        )
        (release_root / "TEST-BUILD.json").write_text(json.dumps({
            "schema": "kfps.working-test-build.v1",
            "version": version,
            "base_commit": commit,
            "working_tree_sha256": state_hash,
            "label": safe_label,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "official_release": False,
            "portable_node_version": PORTABLE_NODE_VERSION,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        write_manifest(
            release_root, version=version, commit=commit,
            kind="community-staging-test", timestamp=timestamp,
        )
        verify_manifest(release_root)
        target = output_dir / f"{folder_name}-bundled.zip"
        write_deterministic_zip(release_root, target, timestamp)
        sidecar = output_dir / f"{target.name}.sha256"
        sidecar.write_text(f"{sha256_file(target)}  {target.name}\n", encoding="ascii")
        print(target)
        print(sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
