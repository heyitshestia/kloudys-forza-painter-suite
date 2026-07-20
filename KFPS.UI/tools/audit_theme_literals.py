from __future__ import annotations

import re
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
QML = UI / "qml"

HEX = re.compile(r'#[0-9a-fA-F]{6,8}')
ALLOW_EXACT = {
    # The facade may contain transparent utility values and palette wiring.
    Path("Kfps/Theme/Theme.qml"),
    # This full-window source-download lock deliberately remains independent
    # from selectable app themes so its warning treatment cannot be softened.
    Path("SourceDownloadBlocker.qml"),
}


def is_palette_file(rel: Path) -> bool:
    return rel.parent == Path("Kfps/Theme") and rel.name.startswith("Palette") and rel.suffix == ".qml"

# Alpha-only transparent/black/white utility values are still allowed outside palettes.
UTILITY = {
    "#00ffffff", "#00000000", "#05000000", "#0d000000", "#35000000",
    "#ffffff", "#ffffffff", "#000000", "#ff000000",
}


def main() -> int:
    findings: list[str] = []
    for path in sorted(QML.rglob("*.qml")):
        rel = path.relative_to(QML)
        if rel in ALLOW_EXACT or is_palette_file(rel):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for value in HEX.findall(line):
                if value.lower() in {item.lower() for item in UTILITY}:
                    continue
                findings.append(f"{rel}:{line_no}: {value} :: {line.strip()}")
    if findings:
        print("Hard-coded non-palette color literals remain:\n")
        print("\n".join(findings))
        print("\nMove these into Theme.qml/Palette*.qml if they should change with themes.")
        return 1
    print("No non-palette QML color literals found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
