"""Require a complete Garage worker in application artifacts that use it."""
from pathlib import Path
import runpy


def validate_packaged_garage(app_root):
    root = Path(app_root)
    if not (root / "KFPS.UI/src/kfps_ui/garage_reader.py").is_file():
        return
    support = root / "tools/garage-reader"
    try:
        # Do not generate bytecode inside the closed, hash-verified distribution.
        module = runpy.run_path(str(support / "distribution.py"))
        return module["verify"](support)
    except (OSError, ValueError, ImportError, AttributeError) as error:
        raise RuntimeError("Garage support is incomplete; refusing to package this application.") from error
