"""Start with KFPS's isolated embedded Python as well as ordinary Python."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("kfps_livery_lab.server", run_name="__main__")
