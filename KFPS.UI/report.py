from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src"), str(ROOT)]

if __name__ == "__main__":
    from kfps_ui.support_window import main
    raise SystemExit(main(ROOT))
