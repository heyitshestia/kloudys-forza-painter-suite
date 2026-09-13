"""Legacy server entry point; preserve per-instance module-global overrides."""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_root), str(_root / "KFPS.Editor/src")]
__file__ = str(_root / "KFPS.Editor/src/kfps_editor/server.py")
exec(compile(Path(__file__).read_bytes(), __file__, "exec"), globals())
