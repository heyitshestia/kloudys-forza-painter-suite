"""Fixed-layout installation discovery, without settings writes or disk scans."""
from pathlib import Path


def default_baseline(lab):
    lab = Path(lab).absolute()
    if lab.name == "livery-studio" and lab.parent.name == "tools":
        root = lab.parent.parent
    elif lab.name == "livery":
        root = lab.parent / "repo"
    else:
        raise ValueError("Set the Studio KFPS root explicitly for this custom folder layout.")
    for path in (lab, root):
        for item in (path, *path.parents):
            if item.is_symlink() or item.is_junction():
                raise ValueError("Studio installation discovery cannot follow redirected paths.")
    if not all((root / relative).is_file() for relative in
               ("KFPS.Editor/manifest.json", "json_preview_renderer.py")):
        raise ValueError("The default Studio KFPS installation is incomplete.")
    return root.resolve()
