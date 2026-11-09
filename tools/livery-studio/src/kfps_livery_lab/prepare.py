"""Prepare one explicitly selected car without reading saves or discovering processes."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat as stat_module
import sys
import tempfile
import zipfile
from contextlib import contextmanager

from .component_coverage import audit_components
from .file_io import atomic_stream, io_path, resolved_path

LAB_ROOT = Path(__file__).resolve().parents[2]
PREPARE_FORMAT = "kfps-livery-lab-prepared-v1"
RECEIPT_FORMAT = "kfps-livery-lab-preparation-receipt-v1"
MAX_PREPARED_BYTES = 8 * 1024 * 1024


def within(path: Path, root: Path) -> Path:
    resolved = resolved_path(path)
    if not resolved.is_relative_to(resolved_path(root)):
        raise ValueError("Path is outside its authorized root.")
    return resolved


def viewer_cache_base(lab_root=None):
    lab = LAB_ROOT if lab_root is None else Path(lab_root)
    if lab.name == "livery-studio" and lab.parent.name == "tools":
        return lab.parents[1] / "runtime" / "lv"
    return lab / "runs" / "viewer-cache"


def workspace_path(workspace: Path, *, lab_root=None) -> Path:
    """One boundary for preparation and its native-material staging."""
    lab = LAB_ROOT if lab_root is None else Path(lab_root)
    root = resolved_path(workspace)
    allowed = [resolved_path(lab / "runs"), resolved_path(viewer_cache_base(lab))]
    if not any(root.is_relative_to(parent) for parent in allowed):
        raise ValueError("Path is outside its authorized root.")
    if root in allowed:
        raise ValueError("Use a named run directory, not the runs root.")
    return root


def workspace_environment(workspace: Path) -> Path:
    root = workspace_path(workspace)
    io_path(root).mkdir(parents=True, exist_ok=True)
    temporary = within(root / "tmp", root)
    cache = within(root / "cache", root)
    io_path(temporary).mkdir(exist_ok=True)
    io_path(cache).mkdir(exist_ok=True)
    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(temporary)
    for key in ("XDG_CACHE_HOME", "MPLCONFIGDIR", "NUMBA_CACHE_DIR", "DOTNET_BUNDLE_EXTRACT_BASE_DIR", "DOTNET_CLI_HOME"):
        os.environ[key] = str(cache)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    tempfile.tempdir = str(temporary)
    return root


def load_baseline(kfps_root: Path) -> Path:
    root = Path(kfps_root).resolve(strict=True)
    required = ("tools/livery/render_contract.py", "tools/livery/portable_mesh_converter.py",
                "json_preview_renderer.py", "tools/livery-inspector/vendor/three/build/three.module.min.js")
    for name in required:
        if not within(root / name, root).is_file():
            raise ValueError(f"KFPS baseline prerequisite missing: {name}")
    for name in ("tools", "tools.livery", "json_preview_renderer", "kfps_shapes"):
        module = sys.modules.get(name)
        filename = getattr(module, "__file__", None)
        if filename and not Path(filename).resolve().is_relative_to(root):
            raise ValueError("A different KFPS root is already loaded; use a fresh process.")
    sys.path.insert(0, str(root))
    return root


@contextmanager
def workspace_lock(workspace: Path):
    root = workspace_environment(workspace)
    path = within(root / "backend.lock", root)
    with io_path(path).open("a+b") as handle:
        if io_path(path).stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("This workspace already has a preparation or server process.") from exc
        try:
            yield root
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, value) -> None:
    body = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with atomic_stream(path) as handle:
        handle.write(body)


def file_hash(path: Path) -> str:
    with io_path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _source_stamp(stat: os.stat_result) -> tuple:
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _check_cancel(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Car preparation was cancelled.")


def _ordinary_path(path: Path) -> Path:
    # Check the spelling before resolving: even an in-root link aliases mutable
    # outputs and must not acquire a verification receipt.
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        native = io_path(part)
        try:
            info = native.lstat()
        except FileNotFoundError:
            continue
        if (stat_module.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
                or (stat_module.S_ISREG(info.st_mode) and info.st_nlink != 1)):
            raise ValueError("Preparation cannot use redirected or multiply linked files.")
    return path


def _check_output_paths(root: Path) -> None:
    for name in ("prepared.json", "preparation-receipt.json", "component-coverage.json"):
        _ordinary_path(root / name)
    count = 0
    for name in ("mesh", "internal", "render", "material-preview"):
        directory = _ordinary_path(root / name)
        if not directory.exists():
            continue
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for child in (*dirs, *files):
                _ordinary_path(Path(parent) / child)
                count += 1
                if count > 512:
                    raise ValueError("Preparation output inventory exceeds its bound.")


def _read_object(path: Path, limit=MAX_PREPARED_BYTES) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate preparation metadata key.")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite preparation metadata: " + value)

    with io_path(_ordinary_path(path)).open("rb") as stream:
        body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Preparation metadata exceeds its bound.")
    result = json.loads(body, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("Preparation metadata must be an object.")
    return result


def _value_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _receipt_code(baseline: Path) -> dict:
    import numpy
    import PIL
    import zlib

    # Check these again before publication, not just on receipt lookup. The
    # blank authoring path uses neither vector rendering nor external shapes.
    lab = ("prepare.py", "component_coverage.py", "converter_process.py", "converter_provenance.py",
           "file_io.py", "render_adapter.py", "material_preview.py", "material_assets.py",
           "wheel_fitment.py", "part_fitment.py", "part_names.py", "catalogue_cache.py")
    native = ("render_contract.py", "portable_mesh_converter.py", "vehicle_assets.py",
              "projection_alignment.py", "derived_cache.py")
    files = {"lab/" + name: file_hash(Path(__file__).with_name(name)) for name in lab}
    files.update({"native/" + name: file_hash(baseline / "tools/livery" / name) for name in native})
    return {"files": files, "runtime": {"python": sys.version, "numpy": numpy.__version__,
                    "pillow": PIL.__version__, "zlib": zlib.ZLIB_RUNTIME_VERSION}}


def _prepared_images(prepared: dict) -> list[str]:
    files = prepared["files"]
    textures = files["native_textures"]
    if (files["mesh"] != "mesh/vehicle.glb" or files["coverage"] != "component-coverage.json"
            or not isinstance(files["masks"], list) or len(files["masks"]) != 3
            or not isinstance(textures, dict) or len(textures) > 32):
        raise ValueError("Invalid prepared file inventory.")
    images = [files["paint"], *files["masks"], *textures.values()]
    for name in images:
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or Path(name).is_absolute() or any(p in ("", ".", "..") for p in name.split("/"))):
            raise ValueError("Invalid prepared image path.")
    expected = {files["mesh"], files["coverage"], *images}
    if len(expected) != len(images) + 2 or set(prepared["file_sha256"]) != expected:
        raise ValueError("Incomplete prepared file fingerprints.")
    return images


def _validate_prepared_files(root: Path, prepared: dict, cancel_event) -> dict:
    from PIL import Image

    images = _prepared_images(prepared)
    stamps = {}
    for name, expected in prepared["file_sha256"].items():
        _check_cancel(cancel_event)
        path = within(_ordinary_path(root / name), root)
        before = _source_stamp(path.stat())
        if file_hash(path) != expected:
            raise ValueError("Prepared artifact fingerprint changed.")
        if name in images:
            with Image.open(io_path(path)) as image:
                image.verify()
        if _source_stamp(path.stat()) != before:
            raise ValueError("Prepared artifact changed during validation.")
        stamps[name] = before
    return stamps


def _receipt_matches(root: Path, prepared: dict, dependencies: dict, validation: dict, cancel_event):
    try:
        receipt = _read_object(root / "preparation-receipt.json", 64 * 1024)
        if (receipt.get("format") != RECEIPT_FORMAT or receipt.get("dependencies") != dependencies
                or receipt.get("prepared_sha256") != file_hash(root / "prepared.json")
                or prepared.get("format") != PREPARE_FORMAT or prepared.get("validation") != validation):
            return None
        stamps = _validate_prepared_files(root, prepared, cancel_event)
        for name in ("internal/blank-sections.zip", "render/index.json"):
            _check_cancel(cancel_event)
            if file_hash(_ordinary_path(root / name)) != receipt["artifacts"][name]:
                return None
            stamps[name] = _source_stamp((root / name).stat())
        return stamps
    except InterruptedError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def _write_receipt(root: Path, dependencies: dict) -> None:
    receipt = {"format": RECEIPT_FORMAT, "dependencies": dependencies,
               "prepared_sha256": file_hash(root / "prepared.json"),
               "artifacts": {name: file_hash(_ordinary_path(root / name)) for name in
                             ("internal/blank-sections.zip", "render/index.json")}}
    atomic_json(root / "preparation-receipt.json", receipt)


def lab_converter(baseline: Path) -> Path:
    build = within(LAB_ROOT / "runs" / "component-converter" / "converter", LAB_ROOT / "runs")
    try:
        from .converter_provenance import verify_build
        return verify_build(LAB_ROOT, baseline, build)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Build the isolated component converter with scripts/build-converter.ps1 before preparing a car.") from exc


def blank_sections(path: Path, section_names) -> None:
    from PIL import Image
    image = io.BytesIO()
    Image.new("RGBA", (2048, 1024), (0, 0, 0, 0)).save(image, format="PNG")
    output = io.BytesIO()
    # Fixed timestamps make the internal atlas input stable across restarts.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        entries = {"lab.json": b'{"format":"kfps-livery-lab-blank-sections-v1","game_package":false}'}
        entries.update({f"projection/rendered/{name}.png": image.getvalue() for name in section_names})
        for name, body in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, body)
    body = output.getvalue()
    if path.is_file() and path.read_bytes() == body:
        return
    temporary = within(path.with_suffix(".zip.tmp"), path.parent)
    temporary.write_bytes(body)
    os.replace(temporary, path)


def prepare_car(kfps_root: Path, game_root: Path, archive: str, workspace: Path, *, cancel_event=None) -> dict:
    _check_cancel(cancel_event)
    _ordinary_path(workspace)
    root = workspace_environment(workspace)
    _check_output_paths(root)
    baseline = load_baseline(kfps_root)
    game = Path(game_root).resolve(strict=True)
    if not archive or Path(archive).name != archive or any(c in archive for c in "\\/:") or not archive.lower().endswith(".zip"):
        raise ValueError("Archive must be one ZIP filename, not a path.")
    source = within(game / "media" / "Cars" / archive, game).resolve(strict=True)
    if not source.is_file():
        raise ValueError("Selected car archive is missing.")

    from tools.livery.vehicle_assets import VehicleAsset, _car_clip_in_archive, read_projection_metadata
    from tools.livery.portable_mesh_converter import validate_local_chassis_glb
    from .converter_process import convert_vehicle_model_to_glb
    from tools.livery.render_contract import SECTION_TO_SLOT, _atlas_to_local_affine
    from .render_adapter import build_authoring_atlases
    from .material_preview import prepare_material_preview
    from .wheel_fitment import read_reference_record, placeholder_assembly
    from .part_fitment import reference_body_compatibility
    from .part_names import load_part_names

    stat = source.stat()
    source_stamp = _source_stamp(stat)
    clip = _car_clip_in_archive(source)
    if clip is None:
        raise ValueError("Selected archive has no car identity.")
    asset = VehicleAsset(clip[0], source.stem, str(source), source.name, stat.st_size, stat.st_mtime_ns, clip[1])
    source_hash = file_hash(source)
    if _source_stamp(source.stat()) != source_stamp:
        raise ValueError("Source car archive changed during identity/hash collection. Retry preparation.")
    converter = lab_converter(baseline)
    signature = {"format": PREPARE_FORMAT, "archive_sha256": source_hash,
                 "converter_sha256": file_hash(converter),
                 "backend_sha256": file_hash(Path(__file__)),
                 "coverage_sha256": file_hash(Path(__file__).with_name("component_coverage.py")),
                 "process_sha256": file_hash(Path(__file__).with_name("converter_process.py")),
                 "render_adapter_sha256": file_hash(Path(__file__).with_name("render_adapter.py")),
                 "material_preview_sha256": file_hash(Path(__file__).with_name("material_preview.py")),
                 "material_assets_sha256": file_hash(Path(__file__).with_name("material_assets.py")),
                 "wheel_fitment_sha256": file_hash(Path(__file__).with_name("wheel_fitment.py")),
                 "part_fitment_sha256": file_hash(Path(__file__).with_name("part_fitment.py")),
                 "baseline": {name: file_hash(baseline / name) for name in (
                     "tools/livery/render_contract.py", "tools/livery/portable_mesh_converter.py",
                     "tools/livery/vehicle_assets.py", "tools/livery/projection_alignment.py")}}
    code = _receipt_code(baseline)
    _check_cancel(cancel_event)
    for name in ("internal", "mesh", "render"):
        within(root / name, root).mkdir(exist_ok=True)
    mesh = within(root / "mesh" / "vehicle.glb", root)
    index = within(root / "prepared.json", root)
    cached = {}
    if index.is_file():
        try:
            cached = _read_object(index)
        except (OSError, ValueError, RecursionError):
            cached = {}
    mesh_cached = (cached.get("signature") == signature and mesh.is_file()
                   and cached.get("mesh_sha256") == file_hash(mesh))
    diagnostics = cached.get("conversion") if mesh_cached else {}
    if not isinstance(diagnostics, dict):
        mesh_cached = False
        diagnostics = {}
    diagnostics = dict(diagnostics)
    if mesh_cached:
        try:
            validation = validate_local_chassis_glb(mesh)
        except (ValueError, OSError, RuntimeError):
            mesh_cached = False
    if not mesh_cached:
        _check_cancel(cancel_event)
        staged = within(root / "mesh" / "vehicle.pending.glb", root)
        try:
            convert_vehicle_model_to_glb(asset, staged, converter_path=converter, diagnostics=diagnostics,
                                         cancel_event=cancel_event)
            validation = validate_local_chassis_glb(staged)
            os.replace(staged, mesh)
        finally:
            staged.unlink(missing_ok=True)

    _check_cancel(cancel_event)
    vehicle = {"car_id": asset.car_id, "model_code": asset.model_code, "archive_name": source.name}
    from tools.livery.portable_mesh_converter import _glb_payloads
    wheel_document, _ = _glb_payloads(mesh)
    part_options = wheel_document['scenes'][wheel_document.get('scene', 0)].get('extras', {}).get('kfps_part_options', [])
    from .garage_build import has_fixed_stock_body
    fixed_body = has_fixed_stock_body(wheel_document)

    def dynamic_inputs():
        _check_cancel(cancel_event)
        issue = None
        try:
            reference = read_reference_record(LAB_ROOT, vehicle, archive_sha256=source_hash)
        except (OSError, ValueError, UnicodeError) as error:
            reference = None
            issue = ("missing-reference" if isinstance(error, FileNotFoundError)
                     else "unreadable-reference" if isinstance(error, OSError)
                     else "invalid-reference")
        materials = prepare_material_preview(mesh, game_root=game, prepared_root=root)
        _check_cancel(cancel_event)
        names = load_part_names(game, vehicle, part_options, cancel_event=cancel_event, fixed_body=fixed_body)
        return reference, issue, materials, names

    # Re-run dynamic material/reference verification rather than maintaining a
    # second archive-dependency resolver (including unsupported/missing assets).
    fitment_reference, reference_issue, native_materials, part_names = dynamic_inputs()
    _check_cancel(cancel_event)
    dependencies = {"signature": _value_hash(signature), "code": code,
                    "source": str(source), "source_stamp": list(source_stamp),
                    "game": str(game), "workspace": str(root), "vehicle": vehicle,
                    "materials": _value_hash(native_materials),
                    "reference": _value_hash([fitment_reference, reference_issue]),
                    "part_names": _value_hash(part_names)}

    def check_inputs():
        _check_cancel(cancel_event)
        reference, issue, materials, names = dynamic_inputs()
        if (_value_hash([reference, issue]) != dependencies["reference"]
                or _value_hash(materials) != dependencies["materials"]
                or _value_hash(names) != dependencies["part_names"]):
            raise ValueError("Material or fitment inputs changed during preparation. Retry preparation.")
        if (_source_stamp(source.stat()) != source_stamp or file_hash(source) != source_hash
                or _source_stamp(source.stat()) != source_stamp or _receipt_code(baseline) != code
                or file_hash(converter) != signature["converter_sha256"]):
            raise ValueError("Source car archive or preparation dependencies changed. Retry preparation.")
        _check_cancel(cancel_event)

    stamps = _receipt_matches(root, cached, dependencies, validation, cancel_event) if mesh_cached else None
    if stamps is not None:
        check_inputs()
        if any(_source_stamp(_ordinary_path(root / name).stat()) != stamp for name, stamp in stamps.items()):
            raise ValueError("Prepared artifacts changed before reuse. Retry preparation.")
        cached["cache"] = {"mesh": True, "render": True}
        atomic_json(index, cached)
        _write_receipt(root, dependencies)
        return cached

    internal = within(root / "internal" / "blank-sections.zip", root)
    blank_sections(internal, SECTION_TO_SLOT)
    _check_cancel(cancel_event)
    contract = build_authoring_atlases(internal, asset, root / "render", mesh_path=mesh, mesh_validation=validation)
    projection = read_projection_metadata(asset)
    by_slot = {row["section"].casefold(): row for row in projection["sections"]}
    sections = []
    for row in contract["sections"]:
        item = dict(row)
        metadata = by_slot.get(row["slot"].casefold())
        if not metadata or not metadata.get("valid"):
            raise ValueError("A rendered section has no valid native projection metadata.")
        if "atlasToLocal" not in item:
            item["atlasToLocal"] = list(_atlas_to_local_affine(
                row["slot"], 2048, 1024, float(metadata.get("xorigin", 0)), float(metadata.get("yorigin", 0))))
        sections.append(item)
    render_metadata = {key: contract[key] for key in ("format", "uv_contract", "assembly", "paint_size", "mask_size", "filters", "sections", "quality_scale", "quality_source")}
    render_metadata["assembly"] = placeholder_assembly(
        render_metadata["assembly"], wheel_document, fitment_reference)
    if reference_issue:
        render_metadata["assembly"]["wheel_fitment"].update(
            reference_issue=reference_issue,
            reason="Optional wheel/body reference could not be validated. No guessed wheels or part relationships are applied.")
    _check_cancel(cancel_event)
    coverage = audit_components(source, mesh)
    if reference_issue:
        coverage["limitations"] = [*coverage.get("limitations", []),
                                  "Optional wheel/body reference is unavailable (" + reference_issue + ")."]
    body_compatibility = reference_body_compatibility(wheel_document, fitment_reference)
    names_compatibility = part_names.get('body_compatibility')
    if body_compatibility is None:
        body_compatibility = names_compatibility
    elif names_compatibility is not None and body_compatibility['parent_map'] != names_compatibility['parent_map']:
        raise ValueError('The body reference catalogues disagree. No fitted configuration was applied.')
    if body_compatibility is not None:
        coverage["body_compatibility"] = body_compatibility
    if coverage["summary"]["uv_integrity_errors"]:
        raise ValueError("Converted UV values failed copy-integrity verification. The car was not opened.")
    coverage_path = within(root / "component-coverage.json", root)
    atomic_json(coverage_path, coverage)
    native_textures = {"profile": native_materials["profile"], "game_equivalent": False,
                       "declarations": {row["resource_path"]: row["sha256"] for row in native_materials["declarations"]
                                        if row["status"] == "verified"},
                       "assets": [{key: value for key, value in row.items() if key != "png_path"}
                                  for row in native_materials["assets"]],
                       "summary": native_materials["summary"], "omissions": native_materials["omissions"]}
    fidelity = {key: coverage[key] for key in ("summary", "game_equivalence_verified", "source_decoder_verified",
                                              "materials", "wheels", "limitations")}
    if body_compatibility is not None:
        fidelity["body_compatibility"] = body_compatibility
    fidelity["part_names"] = part_names
    # Do not describe a projected fallback as a verified native wrap.
    render_metadata["uv_contract"] = {**render_metadata["uv_contract"], "world_projection_fallback": False}
    manifest = {"format": "kfps_livery_lab_preview_v1", "vehicle": vehicle,
                "livery": {"title": "Offline livery layout", "target_car_id": asset.car_id, "logical_placement_count": 0},
                "sharing": {"exportable": False, "preview_only": True},
                "inspection_runtime": {"local_mesh": True,
                                       "direct_uv3": coverage["summary"]["all_livery_surfaces_have_uv3"],
                                       "world_projection_fallback": False, "fidelity": fidelity,
                                       "native_textures": native_textures,
                                       "render_contract": render_metadata}}
    prepared = {"format": PREPARE_FORMAT, "signature": signature, "manifest": manifest,
                "editor_config": {"format": "kfps-livery-layout-v1", "vehicle": vehicle,
                                  "uv_scale": [contract["uv_contract"]["u_scale"], contract["uv_contract"].get("v_scale", 1)],
                                  "paint_size": contract["paint_size"], "sections": sections,
                                  "section_size": [2048, 1024], "game_compatible": False},
                "files": {"mesh": "mesh/vehicle.glb", "coverage": "component-coverage.json", "paint": "render/" + contract["files"]["paint"],
                          "native_textures": {row["cache_key"]: row["png_path"] for row in native_materials["assets"]},
                          "masks": ["render/" + name for name in contract["files"]["masks"]]},
                "mesh_sha256": file_hash(mesh), "validation": validation,
                "cache": {"mesh": mesh_cached, "render": contract["cache_hit"]}, "conversion": diagnostics}
    from PIL import Image
    image_names = [prepared["files"]["paint"], *prepared["files"]["masks"], *prepared["files"]["native_textures"].values()]
    for name in image_names:
        path = within(root / name, root)
        with Image.open(path) as image:
            image.verify()
    prepared["file_sha256"] = {name: file_hash(within(root / name, root)) for name in
                               [prepared["files"]["mesh"], prepared["files"]["coverage"], *image_names]}
    # All stages reopen the archive; do not publish mixed inputs under an old hash.
    check_inputs()
    atomic_json(index, prepared)
    _write_receipt(root, dependencies)
    return prepared
