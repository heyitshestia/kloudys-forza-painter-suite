"""Legacy editor launcher retained for existing shortcuts and KFPS versions."""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_root), str(_root / "KFPS.Editor/src")]
from kfps_editor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
