"""Run the shared real-window startup suite for the Xbox theme, silently."""
import os
from pathlib import Path
import runpy

os.environ["KFPS_STARTUP_TEST_THEME"] = "xbox"
os.environ.setdefault("KFPS_STARTUP_TEST_RUN_ROOT", str(Path(__file__).resolve().parents[2] / "runtime/test-runs/xbox-startup"))
runpy.run_path(str(Path(__file__).with_name("test_ps2_startup.py")), run_name="__main__")
