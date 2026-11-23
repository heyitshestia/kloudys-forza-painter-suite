"""Open a fixed chapter of the installed offline manual in the user's browser."""
import os
from pathlib import Path
import webbrowser


def open_manual(app_root: Path, chapter: str) -> None:
    if chapter not in ("garage", "studio"):
        raise ValueError("Unknown manual chapter.")
    folder = Path(app_root).resolve() / "docs" / "garage-studio-guide"
    entry = folder / (chapter + ".html")
    # Windows file associations take a filename, not a filename with a URL fragment.
    # Each tiny entry page links into the same authoritative manual.
    if not all(path.is_file() and path.resolve() == path
               for path in (entry, folder / "index.html")):
        raise FileNotFoundError("The illustrated manual is missing from this installation.")
    if os.name == "nt":
        os.startfile(str(entry), "open")
    elif not webbrowser.open(entry.as_uri(), new=2):
        raise OSError("The default browser could not open the manual.")
