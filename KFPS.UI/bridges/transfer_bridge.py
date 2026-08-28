import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def discover_app_root():
    starts = []
    env_root = os.environ.get("KFPS_APP_ROOT")
    if env_root:
        starts.append(Path(env_root))
    starts.extend([Path.cwd(), Path(__file__).resolve().parents[2]])
    for start in starts:
        for candidate in [start, *start.parents]:
            nested = candidate / "KloudysFH6Painter"
            if looks_like_app_root(nested):
                return nested.resolve()
            if looks_like_app_root(candidate):
                return candidate.resolve()
    return Path.cwd().resolve()


def looks_like_app_root(path):
    return path.is_dir() and (path / "VERSION").is_file() and (path / "fh6_probe.py").is_file()


ROOT = discover_app_root()
sys.path.insert(0, str(ROOT))

import psutil

from game_adapters import get_adapter, iter_adapters
from live_memory_locator import DIAGNOSTIC_SCHEMA, address_text, read_diagnostic

UNIVERSAL_IMPORT_ROOT = ROOT / "runtime" / "universal-import"
EXPORTED_JSON_ROOT = ROOT / "imgs" / "exported"
MEMORY_SNAPSHOT_LIMIT_MB = 2048


def parse_args():
    parser = argparse.ArgumentParser(description="KFPS import/export bridge")
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--game",
        default="fh6",
        choices=sorted(adapter.bridge_key for adapter in iter_adapters()),
    )
    common.add_argument("--layer-count", type=int, required=True)
    common.add_argument("--pid", type=int)

    import_parser = sub.add_parser("import", parents=[common])
    import_parser.add_argument("--json", required=True)
    import_parser.add_argument("--clear-unused", action="store_true")

    export_parser = sub.add_parser("export", parents=[common])
    return parser.parse_args()


def log(message):
    print(message, flush=True)


def create_transfer_run_dir(game, operation, layer_count, *, root=None, moment=None):
    adapter = get_adapter(game)
    operation = str(operation or "").strip().lower()
    if operation not in {"import", "export"}:
        raise ValueError(f"unsupported transfer operation: {operation}")
    layer_count = int(layer_count)
    if layer_count <= 0:
        raise ValueError("transfer layer count must be greater than zero")
    root = Path(root or UNIVERSAL_IMPORT_ROOT)
    timestamp = (moment or datetime.now()).strftime("%Y%m%d-%H%M%S")
    base = f"{adapter.key}-live-{operation}-{layer_count}-{timestamp}"
    root.mkdir(parents=True, exist_ok=True)
    for sequence in range(1, 1000):
        name = base if sequence == 1 else f"{base}-{sequence:02d}"
        candidate = root / name
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not allocate a unique transfer run folder below {root}")


def run_subprocess(cmd, timeout=None):
    env = os.environ.copy()
    env.update({"FORZA_PAINTER_NO_ELEVATE": "1", "FORZA_PAINTER_NO_PAUSE": "1"})
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        [str(item) for item in cmd],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        env=env,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(line)
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        log(f"Timed out after {timeout} seconds.")
        return 124


def find_game_pid(game):
    try:
        adapter = get_adapter(game)
    except ValueError as exc:
        raise RuntimeError(f"unsupported game: {game}") from exc
    names = {name.lower() for name in adapter.process_names}
    matches = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in names:
                matches.append((int(proc.info["pid"]), proc.info.get("name") or "unknown"))
        except (psutil.Error, OSError, KeyError, TypeError):
            continue
    if not matches:
        expected = ", ".join(adapter.process_names)
        raise RuntimeError(f"no supported {game.upper()} process detected ({expected})")
    matches.sort()
    if len(matches) > 1:
        log(f"Multiple {game.upper()} processes detected; using pid={matches[0][0]} ({matches[0][1]}).")
    else:
        log(f"Detected {game.upper()} process pid={matches[0][0]} ({matches[0][1]}).")
    return matches[0][0]


def import_json_shape_count(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    shapes = data.get("shapes")
    if not isinstance(shapes, list):
        raise ValueError("Import JSON must contain a shapes list.")
    return sum(1 for shape in shapes if isinstance(shape, dict) and not shape.get("hidden"))


def locate_universal_template(game, pid, template_count, run_dir, purpose):
    adapter = get_adapter(game)
    operation = "import" if purpose.startswith("import") else "export"
    session_report = run_dir / "locator-session.json"
    log(f"Locating and validating the open {adapter.short_label} vinyl through locator engine v1...")
    locator_cmd = [
        sys.executable,
        "-m",
        "live_memory_locator",
        "--root",
        ROOT,
        "--game",
        game,
        "--pid",
        str(pid),
        "--layer-count",
        str(template_count),
        "--purpose",
        operation,
        "--output",
        session_report,
        "--limit-mb",
        str(MEMORY_SNAPSHOT_LIMIT_MB),
        "--max-matches",
        "500000",
        "--inspect-radius",
        "0x800",
        "--fast-seconds",
        "45",
        "--research-seconds",
        "90",
    ]
    exit_code = run_subprocess(locator_cmd, timeout=180)
    if not session_report.is_file():
        raise RuntimeError(f"locator engine exited with code {exit_code} without writing diagnostics")
    session = read_diagnostic(session_report)
    request = session.get("request") or {}
    if (
        session.get("schema") != DIAGNOSTIC_SCHEMA
        or str(request.get("game") or "").lower() != adapter.bridge_key
        or int(request.get("pid") or 0) != int(pid)
        or int(request.get("layer_count") or 0) != int(template_count)
        or str(request.get("purpose") or "") != operation
    ):
        raise RuntimeError("locator diagnostic does not match the current transfer request")

    outcome = session.get("outcome") or {}
    status = str(outcome.get("status") or "error")
    reason = str(outcome.get("reason") or "The live-memory locator did not return a usable result.")
    if status != "located":
        log(reason)
        raise RuntimeError(reason)
    if outcome.get("authoritative") is not True:
        raise RuntimeError("locator engine did not produce an authoritative result")
    if exit_code != 0:
        raise RuntimeError(f"locator engine reported success but exited with code {exit_code}")

    selected = session.get("selected") or {}
    if operation == "import":
        group_value = selected.get("import_group_address")
        table_value = selected.get("import_table_address")
        verified = selected.get("import_target_verified") is True
    else:
        group_value = selected.get("group_address")
        table_value = selected.get("table_address")
        verified = True
    if not verified or not group_value or not table_value:
        raise RuntimeError("locator result did not contain the verified addresses required for this transfer")

    group = address_text(int(group_value))
    table = address_text(int(table_value))
    log(
        f"{adapter.short_label} group located and validated for {template_count} layer(s) "
        f"with {selected.get('locator') or 'the versioned locator engine'}."
    )
    return group, table, session_report


def copy_export_to_exported_folder(export_json):
    EXPORTED_JSON_ROOT.mkdir(parents=True, exist_ok=True)
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", export_json.stem).strip(" .") or "game-export"
    target_folder = EXPORTED_JSON_ROOT / base
    target_folder.mkdir(parents=True, exist_ok=True)
    target = target_folder / export_json.name
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = target_folder / f"{export_json.stem}-{stamp}{export_json.suffix}"
    shutil.copy2(export_json, target)
    return target


def run_import(args):
    adapter = get_adapter(args.game)
    if not adapter.supports("live_import"):
        raise RuntimeError(f"{adapter.short_label} online import is not supported")
    json_path = Path(args.json).expanduser().resolve()
    if not json_path.is_file():
        raise RuntimeError(f"missing import JSON: {json_path}")
    if args.layer_count <= 0:
        raise RuntimeError("template layer count must be greater than zero")
    shape_count = import_json_shape_count(json_path)
    if shape_count <= 0:
        raise RuntimeError("import JSON has no visible shapes")
    if shape_count > args.layer_count:
        raise RuntimeError(f"import JSON has too many visible shapes: JSON={shape_count}, template={args.layer_count}")

    pid = args.pid or find_game_pid(args.game)
    run_dir = create_transfer_run_dir(args.game, "import", args.layer_count)
    import_backup = run_dir / "import-backup.json"
    import_report = run_dir / "import-report.json"
    trim_backup = run_dir / "trim-backup.json"

    log(f"Universal import run folder: {run_dir}")
    log(f"Target game: {args.game.upper()}")
    log(f"Import JSON visible shapes: {shape_count}")
    group, table, _locator_report = locate_universal_template(args.game, pid, args.layer_count, run_dir, "import-template")
    import_cmd = [
        sys.executable,
        ROOT / "fh6_import_typecode_json.py",
        "--pid",
        str(pid),
        "--table",
        str(table),
        "--json",
        json_path,
        "--game",
        args.game,
        "--template-count",
        str(args.layer_count),
        "--compact-supported-layers",
        "--allow-unknown-low-byte",
        "--backup",
        import_backup,
        "--report",
        import_report,
        "--write",
    ]
    if args.clear_unused:
        import_cmd.append("--clear-unused")

    log(f"Writing JSON shapes into {args.game.upper()}...")
    if run_subprocess(import_cmd, timeout=240) != 0:
        raise RuntimeError("universal import failed while writing layers")
    report = json.loads(import_report.read_text(encoding="utf-8"))
    imported = int(report.get("imported_layer_count") or 0)
    failures = int(report.get("failure_count") or 0)
    unsupported = int(report.get("unsupported_shape_count") or 0)
    if failures or imported <= 0:
        raise RuntimeError(f"universal import wrote with failures: imported={imported}, failures={failures}, unsupported={unsupported}")

    log(f"Imported {imported} shape layers. Trimming {args.game.upper()} group count...")
    trim_cmd = [
        sys.executable,
        ROOT / "fh6_trim_group_count.py",
        "--pid",
        str(pid),
        "--group",
        str(group),
        "--table",
        str(table),
        "--new-count",
        str(imported),
        "--trim-vector-end",
        "--backup",
        trim_backup,
        "--write",
    ]
    if run_subprocess(trim_cmd, timeout=60) != 0:
        raise RuntimeError("import wrote layers but failed while trimming layer count")
    log(f"Universal import complete: {imported} layers. Save and reload the vinyl group to verify.")
    return 0


def run_export(args):
    adapter = get_adapter(args.game)
    if not adapter.supports("live_export"):
        raise RuntimeError(f"{adapter.short_label} online export is not supported")
    if args.layer_count <= 0:
        raise RuntimeError("loaded group layer count must be greater than zero")
    pid = args.pid or find_game_pid(args.game)
    moment = datetime.now()
    timestamp = moment.strftime("%Y%m%d-%H%M%S")
    run_dir = create_transfer_run_dir(
        args.game,
        "export",
        args.layer_count,
        moment=moment,
    )
    export_json = run_dir / f"{adapter.key}-current-group-{args.layer_count}-{timestamp}.json"
    export_report = run_dir / f"{adapter.key}-current-group-{args.layer_count}-{timestamp}.report.json"

    log(f"Universal export run folder: {run_dir}")
    log(f"Target game: {args.game.upper()}")
    group, table, locator_report = locate_universal_template(args.game, pid, args.layer_count, run_dir, "export-template")

    export_cmd = [
        sys.executable,
        ROOT / "fh6_export_typecode_json.py",
        "--pid",
        str(pid),
        "--group",
        str(group),
        "--table",
        str(table),
        "--count",
        str(args.layer_count),
        "--out",
        export_json,
        "--report",
        export_report,
        "--probe-report",
        locator_report,
        "--game",
        args.game,
    ]
    log(f"Reading current {args.game.upper()} group into compatible JSON...")
    if run_subprocess(export_cmd, timeout=240) != 0:
        if export_report.exists():
            try:
                report = json.loads(export_report.read_text(encoding="utf-8"))
                refusal = report.get("refusal_reason")
                reasons = report.get("validation_reasons") or []
                if refusal:
                    log(str(refusal))
                    if reasons:
                        log("Export validation failed. See the saved report for technical details.")
                else:
                    log("Universal export failed while reading layers.")
            except Exception:
                log("Universal export failed while reading layers.")
        else:
            log("Universal export failed while reading layers.")
        raise RuntimeError("universal export failed while reading layers")
    report = json.loads(export_report.read_text(encoding="utf-8"))
    exported = int(report.get("exported_shape_count") or 0)
    failures = int(report.get("failure_count") or 0)
    warnings = report.get("validation_warnings") or report.get("editable_group_check", {}).get("warnings") or []
    import_copy = copy_export_to_exported_folder(export_json)
    log(f"Universal export complete: {exported} layers -> {export_json}")
    log(f"Copied import-ready export to {import_copy}")
    if warnings:
        log("Export validation warning: grouped vinyl did not match every old flat-table assumption; see report.")
    if failures:
        log(f"Export warning: {failures} unreadable layer(s), see report.")
    log(f"KFPS_SELECTED_JSON: {import_copy}")
    return 0


def main():
    args = parse_args()
    try:
        if args.mode == "import":
            return run_import(args)
        if args.mode == "export":
            return run_export(args)
        raise RuntimeError(f"unknown mode: {args.mode}")
    except Exception as exc:
        log(f"Transfer failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
