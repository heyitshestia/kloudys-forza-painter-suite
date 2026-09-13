"""Compatibility entry point. Both catalogs are maintained by locales/manage.py."""
from pathlib import Path
import runpy
import sys


sys.argv[1:] = ["check" if "--check" in sys.argv else "build"]
runpy.run_path(str(Path(__file__).resolve().parents[1] / "locales/manage.py"), run_name="__main__")
