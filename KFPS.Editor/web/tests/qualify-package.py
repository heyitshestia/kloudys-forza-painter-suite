"""Verify an existing editor-only stage, its imports and the real EXE entry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("stage", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
stage, output = args.stage.resolve(), args.output.resolve()
root = Path(__file__).resolve().parents[3]
for path in (stage, output):
    if not path.is_relative_to(root / "runtime/test-runs"):
        raise ValueError("Qualification must stay in the isolated test root")
output.mkdir(parents=True, exist_ok=False)
inventory = json.loads((stage / "editor-stage.json").read_text(encoding="utf-8"))
for item in inventory["files"]:
    target = stage / item["path"]
    assert target.resolve().is_relative_to(stage)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"], item["path"]
assert not (stage / "KFPS.UI").exists()
assert not (stage / "runtime").exists()
probe = r'''
import importlib, importlib.abc, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / "KFPS.Editor/src")]
class ForbiddenImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'kfps_ui', 'cv2'}:
            raise ImportError('Independent editor attempted to load '+fullname)
sys.meta_path.insert(0, ForbiddenImports())
manifest = json.loads((root / 'KFPS.Editor/manifest.json').read_text())
for name in manifest['runtime_modules']:
    importlib.import_module(name)
from kfps_editor import cli, host, server, projects, recovery, diagnostics, localization, ipc, update_guard
from tools import source_download_guard, kfps_display_language
assert cli.APP_ROOT == root
modules = {}
for name, module in list(sys.modules.items()):
    file = getattr(module, '__file__', None)
    if file and (name.startswith(('kfps_editor', 'kfps_shapes', 'tools.')) or name in {'geometry_json','json_preview_renderer'}):
        target = Path(file).resolve()
        assert target.is_relative_to(root), (name, str(target))
        modules[name] = str(target.relative_to(root))
assert not any(name.startswith(('kfps_ui','cv2')) for name in sys.modules)
print(json.dumps({'modules':modules, 'runtimeModules':manifest['runtime_modules'], 'noMainUiOrGenerator':True}))
'''
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", KFPS_PYTHON=sys.executable)
imported = subprocess.run([sys.executable, "-I", "-B", "-c", probe, str(stage)],
    cwd=output, env=env, capture_output=True, text=True, timeout=60, creationflags=flags)
(output / "imports.stdout.log").write_text(imported.stdout, encoding="utf-8")
(output / "imports.stderr.log").write_text(imported.stderr, encoding="utf-8")
assert imported.returncode == 0, imported.stderr
result = json.loads(imported.stdout)
launcher = stage / "KFPS Editor.exe"
assert launcher.is_file()
launched = subprocess.run([str(launcher), "--help"], cwd=output, env=env,
    capture_output=True, text=True, timeout=60, creationflags=flags)
assert launched.returncode == 0, launched.stderr
result.update(filesVerified=len(inventory["files"]), launcherHelpExit=launched.returncode,
              launcherSha256=hashlib.sha256(launcher.read_bytes()).hexdigest())
(output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
