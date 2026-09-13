"""Actual Windows lock and mocked legacy process-scan qualification. No update."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
out = Path(sys.argv[1]).resolve()
if not out.is_relative_to(ROOT / "runtime/test-runs"):
    raise ValueError("Isolated test output required")
out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor.update_guard import acquire_update_guard, updater_state_root
os.environ["LOCALAPPDATA"] = str(out / "system-data")
outer = out / "install"
app_root = outer / "KloudysFH6Painter"
app_root.mkdir(parents=True)
assert updater_state_root(outer) == updater_state_root(app_root)
state = updater_state_root(app_root)
code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kfps_editor.update_guard import acquire_update_guard
try:
    guard = acquire_update_guard(Path(sys.argv[2]))
except RuntimeError as error:
    print(str(error)); sys.exit(2)
else:
    guard.Close(); sys.exit(0)
"""
def child_guard():
    return subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / "KFPS.Editor/src"), str(state)],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
guard = acquire_update_guard(state)
try:
    blocked = child_guard()
    assert blocked.returncode == 2 and "updating" in blocked.stdout, blocked
finally:
    guard.Close()
assert child_guard().returncode == 0
victim = out / "untouched.txt"
victim.write_text("untouched", encoding="utf-8")
linked = out / "linked-lock"
linked.mkdir()
os.link(victim, linked / "updater.lock")
try:
    accidental = acquire_update_guard(linked)
except RuntimeError:
    pass
else:
    accidental.Close()
    raise AssertionError("Hard-linked lock accepted")
assert victim.read_text(encoding="utf-8") == "untouched"
scan = ROOT / "tools/update/Stop-KfpsProcesses.ps1"
wrapper = r'''
$ErrorActionPreference = 'Stop'
function Get-CimInstance { Get-Content -Raw -LiteralPath $env:KFPS_PROCESS_FIXTURE | ConvertFrom-Json }
function Stop-Process { throw 'A process stop was attempted during the editor guard check' }
& $env:KFPS_PROCESS_SCAN -Root $env:KFPS_TEST_ROOT -Parent $env:KFPS_TEST_PARENT -ReportPath $env:KFPS_TEST_REPORT
exit $LASTEXITCODE
'''
cases = []
for name, executable, command in (
    ("canonical", sys.executable, f'"{sys.executable}" "{app_root / "KFPS.Editor/editor.py"}"'),
    ("legacy", sys.executable, f'"{sys.executable}" "{app_root / "KFPS.UI/editor.py"}"'),
    ("server", sys.executable, f'"{sys.executable}" "{app_root / "tools/fabric-editor/start_fabric_editor.py"}"'),
    ("outer-launcher", str(outer / "KFPS Editor.exe"), f'"{outer / "KFPS Editor.exe"}"'),
):
    fixture, report = out / f"{name}.json", out / f"{name}.txt"
    fixture.write_text(json.dumps([{"Name": Path(executable).name, "ExecutablePath": executable,
        "CommandLine": command, "ProcessId": 123456789}]), encoding="utf-8")
    env = dict(os.environ, KFPS_PROCESS_FIXTURE=str(fixture), KFPS_PROCESS_SCAN=str(scan),
        KFPS_TEST_ROOT=str(app_root), KFPS_TEST_PARENT=str(outer), KFPS_TEST_REPORT=str(report))
    result = subprocess.run(["powershell", "-NoProfile", "-Command", wrapper], env=env,
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 2, (name, result.returncode, result.stdout, result.stderr)
    assert "No processes were stopped" in report.read_text(), name
    cases.append({"entry": name, "blockedWithoutStopping": True})
result = {"sameInstallIdentity": True, "crossProcessLock": True, "releasedLock": True,
          "hardLinkRejected": True, "legacyProcessScan": cases}
(out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
