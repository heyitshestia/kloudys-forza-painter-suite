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

from game_profiles import PROFILES

UNIVERSAL_IMPORT_ROOT = ROOT / "runtime" / "universal-import"
EXPORTED_JSON_ROOT = ROOT / "imgs" / "exported"
MEMORY_SNAPSHOT_LIMIT_MB = 2048


def parse_args():
    parser = argparse.ArgumentParser(description="KFPS import/export bridge")
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--game", default="fh6", choices=sorted(PROFILES.keys()))
    common.add_argument("--layer-count", type=int, required=True)
    common.add_argument("--pid", type=int)

    import_parser = sub.add_parser("import", parents=[common])
    import_parser.add_argument("--json", required=True)
    import_parser.add_argument("--clear-unused", action="store_true")

    export_parser = sub.add_parser("export", parents=[common])
    return parser.parse_args()


def log(message):
    print(message, flush=True)


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
    if game not in PROFILES:
        raise RuntimeError(f"unsupported game: {game}")
    names = {name.lower() for name in PROFILES[game].process_names}
    matches = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in names:
                matches.append((int(proc.info["pid"]), proc.info.get("name") or "unknown"))
        except (psutil.Error, OSError, KeyError, TypeError):
            continue
    if not matches:
        expected = ", ".join(PROFILES[game].process_names)
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


def session_matches_import_template(session, game, template_count):
    profile = PROFILES[game]
    required_word = int(getattr(profile, "import_template_shape_word", -1))
    minimum_ratio = float(getattr(profile, "import_template_min_ratio", 0.0))
    if required_word < 0 or minimum_ratio <= 0:
        return True, ""
    counts = session.get("shape_word_counts") or {}
    matching = int(counts.get(str(required_word)) or counts.get(required_word) or 0)
    required = int(int(template_count) * minimum_ratio)
    if matching < required:
        return False, f"template shape check {matching}/{template_count} plain circles"
    return True, f"template shape check {matching}/{template_count} plain circles"


def locate_universal_template(game, pid, template_count, run_dir, purpose):
    session_report = run_dir / f"fast-{purpose}-session.json"
    probe_report = run_dir / f"fallback-{purpose}-probe.json"
    group = None
    table = None
    use_research_scanner = False
    if not use_research_scanner:
        log(f"Fast-locating loaded {game.upper()} group with {template_count} layers...")
        fast_cmd = [
            sys.executable,
            ROOT / "fh6_probe.py",
            "--game",
            game,
            "--pid",
            str(pid),
            "--layer-count",
            str(template_count),
            "--auto-locate",
            "--write-session",
            session_report,
            "--dump-slot-radius",
            "16",
            "--limit-mb",
            str(MEMORY_SNAPSHOT_LIMIT_MB),
            "--max-matches",
            "500000",
            "--inspect-radius",
            "0x800",
            "--max-seconds",
            "45",
        ]
        code = run_subprocess(fast_cmd, timeout=90)
        if code == 0 and session_report.exists():
            session = json.loads(session_report.read_text(encoding="utf-8"))
            if str(session.get("layer_count", "")) == str(template_count):
                table_value = session.get("table_address")
                count_value = session.get("count_address")
                group_value = session.get("group_address")
                template_ok, template_detail = session_matches_import_template(
                    session,
                    game,
                    template_count,
                ) if purpose.startswith("import") else (True, "")
                if not template_ok:
                    log(f"Rejected located {game.upper()} import group: {template_detail}.")
                if template_ok and table_value and (group_value or count_value):
                    table = f"0x{int(table_value):x}" if isinstance(table_value, int) else str(table_value)
                    if group_value:
                        group = f"0x{int(group_value):x}" if isinstance(group_value, int) else str(group_value)
                    else:
                        raw_count = int(count_value) if isinstance(count_value, int) else int(str(count_value), 0)
                        group = f"0x{raw_count - 0x5A:x}"
                    detail = f", {template_detail}" if template_detail else ""
                    log(f"{game.upper()} group fast-located and validated for {template_count} layer(s){detail}.")
        if group and table:
            return group, table
        log("Fast locate did not produce a usable group/table. Falling back to research scanner.")
    else:
        log("Universal import/export uses the research scanner so grouped vinyl child tables can be found safely.")
    probe_cmd = [
        sys.executable,
        ROOT / "fh6_group1000_probe.py",
        "--pid",
        str(pid),
        "--count",
        str(template_count),
        "--max-seconds",
        "90",
        "--report-layers",
        "40",
        "--out-dir",
        run_dir,
    ]
    code = run_subprocess(probe_cmd, timeout=140)
    if code != 0:
        raise RuntimeError("template probe did not complete")
    probe_files = sorted(run_dir.glob(f"fh6-group{template_count}-probe-*.json"), key=lambda path: path.stat().st_mtime)
    if not probe_files:
        raise RuntimeError("template probe report was not created")
    probe_files[-1].replace(probe_report)
    probe = json.loads(probe_report.read_text(encoding="utf-8"))
    candidates = probe.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"no matching loaded {game.upper()} group was found")

    min_sample_ok = min(8, template_count)
    requires_fresh_circle_template = purpose.startswith("import")
    min_circle_count = int(template_count * 0.90) if requires_fresh_circle_template else 0

    def candidate_sample_ok(candidate):
        return int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)

    def candidate_sort_key(candidate):
        valid_ptrs = int(candidate.get("valid_ptrs") or 0)
        invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, template_count - valid_ptrs))
        sample_ok = candidate_sample_ok(candidate)
        exact_table = int(valid_ptrs == template_count and invalid_ptrs == 0)
        exact_decoded = int(exact_table and sample_ok >= template_count)
        vector_bonus = int(candidate.get("vector_ok") is True)
        source_bonus = 1 if candidate.get("source") == "vector_header" else 0
        return (
            exact_decoded,
            exact_table,
            valid_ptrs,
            sample_ok,
            -invalid_ptrs,
            vector_bonus,
            source_bonus,
            int(candidate.get("score") or 0),
        )

    candidates = sorted(candidates, key=candidate_sort_key, reverse=True)

    def shape_count(candidate, shape_byte):
        counts = candidate.get("shape_id_counts_all") or {}
        return int(counts.get(str(shape_byte)) or counts.get(shape_byte) or 0)

    def candidate_rejection(candidate, valid_ptrs, sample_ok):
        vector_ok = candidate.get("vector_ok")
        vector_count = candidate.get("vector_count")
        capacity_count = candidate.get("capacity_count")
        if requires_fresh_circle_template and vector_ok is False:
            return "vector metadata invalid"
        if requires_fresh_circle_template and vector_count is not None and int(vector_count) != int(template_count):
            return f"vector_count={vector_count}"
        if capacity_count is not None and int(capacity_count) < int(template_count):
            return f"capacity_count={capacity_count}"
        if valid_ptrs < template_count:
            return f"valid_ptrs={valid_ptrs}"
        invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, template_count - valid_ptrs))
        if invalid_ptrs:
            return f"invalid_ptrs={invalid_ptrs}"
        if sample_ok < min_sample_ok:
            return f"sample_ok={sample_ok}"
        if requires_fresh_circle_template:
            circle_count = shape_count(candidate, 102)
            if circle_count < min_circle_count:
                return f"circle_template_check={circle_count}/{template_count}"
        return ""

    rejected = []
    selected = None
    strong_candidates = []
    for index, candidate in enumerate(candidates, start=1):
        group = candidate.get("group")
        table = candidate.get("table")
        valid_ptrs = int(candidate.get("valid_ptrs") or 0)
        sample_ok = candidate_sample_ok(candidate)
        rejection = candidate_rejection(candidate, valid_ptrs, sample_ok)
        if group and table and not rejection:
            strong_candidates.append((index, candidate))
            selected = (index, group, table, valid_ptrs, sample_ok, shape_count(candidate, 102))
            break
        rejected.append(f"#{index}: {rejection or 'missing group/table'}")
    if purpose.startswith("export"):
        strong_candidates = []
        for index, candidate in enumerate(candidates, start=1):
            group = candidate.get("group")
            table = candidate.get("table")
            valid_ptrs = int(candidate.get("valid_ptrs") or 0)
            sample_ok = candidate_sample_ok(candidate)
            rejection = candidate_rejection(candidate, valid_ptrs, sample_ok)
            if group and table and not rejection:
                strong_candidates.append((index, candidate))
        if strong_candidates and selected is None:
            index, candidate = strong_candidates[0]
            selected = (
                index,
                candidate.get("group"),
                candidate.get("table"),
                int(candidate.get("valid_ptrs") or 0),
                candidate_sample_ok(candidate),
                shape_count(candidate, 102),
            )

    if not selected:
        detail = "; ".join(rejected[:5]) if rejected else "no candidates"
        if requires_fresh_circle_template:
            raise RuntimeError(
                f"no safe fresh {game.upper()} import template was found. Load the saved/reopened 3000-layer plain white "
                f"circle template, stay in the Vinyl Group Editor, and import only once per fresh template ({detail})"
            )
        raise RuntimeError(f"located group did not validate strongly enough ({detail})")

    index, group, table, valid_ptrs, sample_ok, circle_count = selected
    if index > 1:
        log(f"Skipped {index - 1} weaker fallback candidate(s).")
    circle_suffix = f", circle_template={circle_count}/{template_count}" if requires_fresh_circle_template else ""
    log(f"{game.upper()} group fallback-located and validated: layers={template_count}, validated={valid_ptrs}, sample_ok={sample_ok}{circle_suffix}")
    return group, table


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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = UNIVERSAL_IMPORT_ROOT / f"{json_path.stem}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    import_backup = run_dir / "import-backup.json"
    import_report = run_dir / "import-report.json"
    trim_backup = run_dir / "trim-backup.json"

    log(f"Universal import run folder: {run_dir}")
    log(f"Target game: {args.game.upper()}")
    log(f"Import JSON visible shapes: {shape_count}")
    group, table = locate_universal_template(args.game, pid, args.layer_count, run_dir, "import-template")
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
    if args.layer_count <= 0:
        raise RuntimeError("loaded group layer count must be greater than zero")
    pid = args.pid or find_game_pid(args.game)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = UNIVERSAL_IMPORT_ROOT / f"export-current-group-{args.layer_count}-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    export_json = run_dir / f"{args.game}-current-group-{args.layer_count}-{timestamp}.json"
    export_report = run_dir / f"{args.game}-current-group-{args.layer_count}-{timestamp}.report.json"

    log(f"Universal export run folder: {run_dir}")
    log(f"Target game: {args.game.upper()}")
    group, table = locate_universal_template(args.game, pid, args.layer_count, run_dir, "export-template")
    locator_report = run_dir / "fast-export-template-session.json"
    if not locator_report.exists():
        locator_report = run_dir / "fallback-export-template-probe.json"

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
