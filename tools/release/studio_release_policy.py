"""Closed Studio distribution inventory; never package a working install wholesale."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat

STUDIO = PurePosixPath("tools/livery-studio")
LAUNCHER = "KFPSLiverySudio.exe"
CONVERTER = PurePosixPath("runs/component-converter/converter")
CONVERTER_FILES = {CONVERTER / "build-manifest.json", CONVERTER / "publish/Kfps.LiveryLab.Converter.exe"}
BUILD_FILES = {PurePosixPath("scripts") / name for name in
               ("build-converter.ps1", "resolve-baseline.ps1", "build-studio-launcher.ps1")}
LICENSE_FILES = {PurePosixPath("licenses") / name for name in
                 ("LICENSE.dotnet.txt", "THIRD-PARTY-NOTICES.dotnet.txt", "LICENSE.System.Memory.txt",
                  "THIRD-PARTY-NOTICES.System.Memory.txt", "LICENSE.Syroot.BinaryData.txt", "PROVENANCE.json")}
REQUIRED = {
    "src/launch_studio.py", "src/run_livery.py", "src/kfps_livery_lab/launcher.py",
    "src/kfps_livery_lab/install_config.py", "src/kfps_livery_lab/package_paths.py",
    "src/kfps_livery_lab/host_bridge.py", "src/kfps_livery_lab/server.py",
    "src/kfps_livery_lab/native_host.py", "src/kfps_livery_lab/studio_window.py",
    "src/kfps_livery_lab/readonly_preview.py", "src/kfps_livery_lab/readonly_server.py",
    "src/kfps_livery_lab/readonly_prepare.py", "src/kfps_livery_lab/readonly_cache.py",
    "src/kfps_livery_lab/project_storage.py", "src/kfps_livery_lab/managed_recovery.py",
    "src/kfps_livery_lab/recovery.py", "src/kfps_livery_lab/source_editor.py",
    "src/kfps_livery_lab/diagnostics.py", "src/kfps_livery_lab/storage_paths.py",
    "src/kfps_livery_lab/converter_provenance.py", "src/chassis-converter/baseline-prerequisites.json",
    "src/chassis-converter/LICENSE.ForzaTechStudio", "src/launcher/KFPSLiverySudio.cs",
    "src/web/index.html", "src/web/livery-editor.mjs", "src/web/project-storage-ui.mjs",
    "src/web/readonly.html", "src/web/readonly.mjs", "src/web/readonly.css", "src/web/LICENSE.lucide",
    "src/web/locales/en.mjs", "src/web/locales/ko.mjs", "src/web/locales/ja.mjs", "src/web/locales/messages.json",
} | {str(path) for path in CONVERTER_FILES | BUILD_FILES | LICENSE_FILES}
BASELINE_REQUIRED = (
    "json_preview_renderer.py", "geometry_json.py", "KFPS.Editor/manifest.json",
    "KFPS.Editor/src/kfps_editor/baseline.py", "KFPS.Editor/src/kfps_editor/graphics.py",
    "KFPS.Editor/src/kfps_editor/graphics_probe.py", "KFPS.Editor/src/kfps_editor/server.py",
    "KFPS.Editor/web/release-announcement.js", "KFPS.Editor/web/release-announcement.css",
    "KFPS.Editor/web/activity-client.js", "KFPS.UI/content/release-announcement.json",
    "tools/kfps_release_announcement.py", "tools/kfps_display_language.py",
    "tools/kfps_activity.py", "tools/kfps_activity_host.py",
    "tools/livery/vehicle_assets.py", "tools/livery/render_contract.py", "tools/livery/portable_mesh_converter.py",
    "tools/livery-inspector/vendor/three/build/three.module.min.js", "tools/livery-inspector/THIRD_PARTY.md",
    "tools/livery-inspector/vendor/three/build/three.core.min.js", "tools/livery-inspector/vendor/three/LICENSE",
    "tools/livery-inspector/vendor/three/examples/jsm/loaders/GLTFLoader.js",
    "tools/livery-inspector/vendor/three/examples/jsm/controls/OrbitControls.js",
    "tools/livery-inspector/vendor/three/examples/jsm/utils/BufferGeometryUtils.js",
    "tools/livery-inspector/vendor/three/examples/jsm/utils/SkeletonUtils.js",
)
PERSONAL_PATH = re.compile(rb"(?:[A-Za-z]:[/\\]+(?:Users[/\\]+[^/\\\s'\"]+|KFPS-UI-Redesign|ECC)[/\\])", re.I)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_file(root, relative):
    relative = PurePosixPath(relative)
    if relative.is_absolute() or ".." in relative.parts or any(":" in part or "\\" in part for part in relative.parts):
        raise ValueError("Unsafe distribution path.")
    root = Path(root).absolute()
    path = root.joinpath(*relative.parts)
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked distribution input: " + str(relative))
    if not path.is_file():
        raise ValueError("Missing distribution input: " + str(relative))
    return path


def studio_path_allowed(relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or any(":" in p or "\\" in p for p in path.parts):
        return False
    if path in CONVERTER_FILES | BUILD_FILES | LICENSE_FILES:
        return True
    if path in {PurePosixPath("src/launch_studio.py"), PurePosixPath("src/run_livery.py"),
                PurePosixPath("src/launcher/KFPSLiverySudio.cs")}:
        return True
    if path.parent == PurePosixPath("src/kfps_livery_lab"):
        return path.suffix == ".py" and not path.name.startswith(".")
    if path.parent == PurePosixPath("src/chassis-converter"):
        return path.suffix in {".cs", ".csproj"} or path.name in {
            "baseline-prerequisites.json", "LICENSE.ForzaTechStudio", "PROVENANCE.md", "NuGet.Config", "material_textures.py"}
    if path.parent == PurePosixPath("src/web"):
        return path.suffix in {".js", ".mjs", ".css", ".html"} or path.name == "LICENSE.lucide"
    if path.parent == PurePosixPath("src/web/locales"):
        return path.name in {"en.mjs", "ko.mjs", "ja.mjs", "messages.json"}
    return False


def _provenance(lab):
    path = safe_file(lab, "src/kfps_livery_lab/converter_provenance.py")
    spec = importlib.util.spec_from_file_location("_release_converter_provenance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(lab, baseline, *, strict=False):
    lab, baseline = Path(lab).absolute(), Path(baseline).absolute()
    records = []
    # Never enumerate working caches, recovery stores, settings or test evidence.
    candidates = []
    for folder in ("src/kfps_livery_lab", "src/chassis-converter", "src/web", "src/web/locales"):
        directory = lab / folder
        if directory.is_dir():
            candidates.extend(PurePosixPath(p.relative_to(lab).as_posix()) for p in directory.iterdir() if p.is_file())
    candidates.extend(PurePosixPath(p) for p in REQUIRED)
    for relative in sorted(set(candidates)):
        if not studio_path_allowed(relative):
            if relative.suffix == ".pyc":
                continue
            raise ValueError("Unreviewed Studio source input: " + str(relative))
        path = safe_file(lab, relative)
        if path.suffix.lower() != ".exe" and PERSONAL_PATH.search(path.read_bytes()):
            raise ValueError("Personal/workspace path in public Studio source: " + str(relative))
        records.append({"path": (STUDIO / relative).as_posix(), "source": relative.as_posix(),
                        "bytes": path.stat().st_size, "sha256": digest(path)})
    provenance = _provenance(lab)
    build = lab.joinpath(*CONVERTER.parts)
    receipt = provenance.read_json(safe_file(build, "build-manifest.json"))
    if receipt.get("format") != "kfps-converter-build-v2":
        raise ValueError("Public Studio requires relocatable v2 converter provenance.")
    provenance.verify_build(lab, baseline, build)
    dependencies = []
    names = set(BASELINE_REQUIRED)
    names.update(row["path"] for row in receipt["sources"] if row["root"] == "baseline")
    for name in sorted(names):
        path = safe_file(baseline, name)
        dependencies.append({"path": name, "bytes": path.stat().st_size, "sha256": digest(path)})
    if strict:
        expected = {row["source"] for row in records}
        for path in lab.rglob("*"):
            relative = path.relative_to(lab).as_posix()
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Linked Studio distribution entry: " + relative)
            if path.is_file() and relative not in expected:
                raise ValueError("Non-shipping Studio file: " + relative)
    return {"version": 1, "component": "livery-studio", "format": "public-portable-source-v1",
            "launcher": LAUNCHER, "files": records, "baseline_prerequisites": dependencies,
            "converter_sha256": digest(lab / CONVERTER / "publish/Kfps.LiveryLab.Converter.exe"),
            "excluded": ["settings", "recovery", "tests", "fixtures", "integration", "docs",
                         "runs except the two exact converter files", "game assets", "artwork", "credentials"],
            "policy": "Native game-save export remains Preview; no in-game or per-car fidelity certification."}


def validate_packaged_studio(app_root):
    root = Path(app_root)
    lab = root.joinpath(*STUDIO.parts)
    launcher = root / LAUNCHER
    if not lab.exists() and not launcher.exists():
        return None  # Historical builds without Studio remain buildable.
    safe_file(root, LAUNCHER)
    return inventory(lab, root, strict=True)


def copy_outer_launchers(app_root, release_root):
    root, outer = Path(app_root), Path(release_root)
    import shutil
    names = ["KFPS.exe", "KFPS-Updater.exe"]
    for optional in ("KFPS Editor.exe", LAUNCHER):
        if (root / optional).is_file():
            names.append(optional)
    for name in names:
        shutil.copy2(safe_file(root, name), outer / name)
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio-source", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    value = inventory(args.studio_source, args.baseline, strict=args.strict)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(f"Reviewed {len(value['files'])} Studio inputs and {len(value['baseline_prerequisites'])} baseline prerequisites.")


if __name__ == "__main__":
    main()
