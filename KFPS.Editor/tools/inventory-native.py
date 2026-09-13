"""Machine-readable native/shared function ownership and import inventory."""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor.manifest import load_manifest

manifest = load_manifest()
records, sources = [], []
for entry in manifest["native"] + manifest["shared"]:
    if not entry["path"].endswith(".py"):
        continue
    source = ROOT / entry["path"]
    payload = source.read_bytes()
    tree = ast.parse(payload, filename=entry["path"])
    imports = []
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []

        def visit_ClassDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node):
            self.scope.append(node.name)
            records.append({"file": entry["path"], "name": ".".join(self.scope),
                "line": node.lineno, "end": node.end_lineno, "owner": entry["owner"],
                "role": entry["role"], "basis": "explicit native/shared source manifest"})
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Import(self, node):
            imports.append({"line": node.lineno, "statement": ast.unparse(node)})

        visit_ImportFrom = visit_Import
    Visitor().visit(tree)
    sources.append({"file": entry["path"], "sha256": hashlib.sha256(payload).hexdigest(),
                    "owner": entry["owner"], "imports": imports})
print(json.dumps({"records": records, "sources": sources}))
