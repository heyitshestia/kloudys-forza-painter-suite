"""Release-owned runtime/content identity. Startup only; never on an edit path."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import uuid

CONTRACT = "KFPS.Editor/baseline.json"
SCHEMA = "kfps-editor-baseline/1"
MAX_CONTRACT_BYTES = 16 * 1024 * 1024


class BaselineError(RuntimeError):
    pass


def development_root(root: Path) -> bool:
    root = Path(root).resolve()
    if (root / ".git").exists():
        return True
    # Stages are private qualification artifacts, not a public runtime fallback.
    for parent in root.parents:
        if parent.name == "test-runs" and parent.parent.name == "runtime":
            return (parent.parent.parent / ".git").exists() and (root / "editor-stage.json").is_file()
    return False


def isolated_environment(environment=None):
    result = dict(os.environ if environment is None else environment)
    for key in list(result):
        upper = key.upper()
        if upper.startswith(("PYTHON", "QT_", "QTWEBENGINE", "QML", "PYSIDE", "SHIBOKEN")):
            result.pop(key)
    result["PYTHONNOUSERSITE"] = "1"
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    return result


def managed_python(root: Path) -> Path:
    root = Path(root).resolve()
    for name in ("pythonw.exe", "python.exe"):
        candidate = root / "python" / name
        if candidate.is_file() and candidate.resolve().parent == root / "python":
            return candidate
    raise BaselineError("The editor's bundled runtime is missing.")


def engine_identity():
    import platform
    import struct
    import PySide6
    from PySide6.QtCore import qVersion
    from PySide6.QtWebEngineCore import qWebEngineChromiumVersion, qWebEngineVersion
    return {"python": platform.python_version(), "bits": struct.calcsize("P") * 8,
            "pyside": PySide6.__version__, "qt": qVersion(),
            "webengine": qWebEngineVersion(), "chromium": qWebEngineChromiumVersion()}


def verify_import_origins(python_root):
    import importlib
    python_root = Path(python_root).resolve()
    for name in ("PySide6", "PySide6.QtWebEngineCore", "shiboken6", "numpy", "PIL", "psutil", "win32api", "win32file"):
        module = importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(python_root):
            raise BaselineError(f"Editor dependency loaded outside its bundled runtime: {name}")


def file_hash(path: Path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return digest


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or len(relative) > 512:
        raise BaselineError("Invalid baseline path.")
    parts = PurePosixPath(relative)
    if (parts.is_absolute() or parts.as_posix() != relative or
            any(p in (".", "..") for p in parts.parts) or
            any(c in relative for c in ("\\", ":", "\x00"))):
        raise BaselineError("Invalid baseline path.")
    path = root
    for part in parts.parts:
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BaselineError(f"Linked installation file: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise BaselineError(f"Missing installation file: {relative}")
    return path


def executable_paths(root: Path, tree: str):
    base = root / tree
    if not base.is_dir() or base.is_symlink() or getattr(base, "is_junction", lambda: False)():
        raise BaselineError(f"Missing or linked installation folder: {tree}")
    for directory, folders, names in os.walk(base, followlinks=False):
        for name in list(folders):
            path = Path(directory) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise BaselineError("Linked folder in editor baseline.")
            if name == "__pycache__":
                folders.remove(name)
        for name in names:
            if not name.endswith(".pyc"):
                yield (Path(directory) / name).relative_to(root).as_posix()


def verify(root: Path, *, executable=None, identity=None, isolated=None):
    root = Path(root).resolve()
    started = time.monotonic()
    path = root / CONTRACT
    if not path.exists():
        if development_root(root):
            return {"status": "development", **(identity or engine_identity())}
        raise BaselineError("The editor installation is incomplete. Its baseline record is missing.")
    try:
        path = safe_file(root, CONTRACT)
        if path.stat().st_size > MAX_CONTRACT_BYTES:
            raise BaselineError("The editor baseline record is oversized.")
        payload = path.read_bytes()
        contract = json.loads(payload)
        if contract.get("schema") != SCHEMA:
            raise BaselineError("The editor baseline record is unsupported.")
        if Path(executable or sys.executable).resolve().parent != root / "python":
            raise BaselineError("The editor must use this installation's bundled runtime.")
        if not (sys.flags.isolated if isolated is None else isolated):
            raise BaselineError("The editor runtime must start in isolated mode.")
        records = contract["files"]
        if not isinstance(records, list) or not 1 <= len(records) <= 100000:
            raise BaselineError("Invalid editor baseline inventory.")
        expected = set()
        total = 0
        for item in records:
            relative, digest, size = item["path"], item["sha256"], item["size"]
            if not isinstance(relative, str) or relative.casefold() in expected:
                raise BaselineError("Duplicate editor baseline file.")
            expected.add(relative.casefold())
            if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest) or type(size) is not int or size < 0:
                raise BaselineError("Invalid editor baseline fingerprint.")
            current = safe_file(root, relative)
            if current.stat().st_size != size or file_hash(current) != digest:
                raise BaselineError(f"Editor installation file does not match: {relative}")
            total += size
        required = {"python/python.exe", "KFPS.Editor/editor.py", "KFPS.Editor/manifest.json",
                    "KFPS.Editor/web/index.html", "KFPS.Editor/web/vendor/fabric.min.js"}
        if not {p.casefold() for p in required} <= expected:
            raise BaselineError("The editor baseline inventory is incomplete.")
        # Only program trees are exact. User projects/settings are never scanned.
        for tree in ("python", "KFPS.Editor/web", "KFPS.Editor/src"):
            for relative in executable_paths(root, tree):
                if relative.casefold() not in expected:
                    raise BaselineError(f"Unexpected editor/runtime file: {relative}")
        if identity is None:
            verify_import_origins(root / "python")
        actual = identity or engine_identity()
        if actual != contract["engine"]:
            raise BaselineError("The running browser engine does not match this editor release.")
        return {"status": "verified", "baseline": hashlib.sha256(payload).hexdigest(),
                "files": len(records), "bytes": total,
                "verification_ms": round((time.monotonic() - started) * 1000, 1), **actual}
    except BaselineError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BaselineError("The editor installation is missing or has unreadable baseline files.") from exc


def launch_command(root: Path, entry: Path, arguments, fallback=None):
    root = Path(root).resolve()
    if development_root(root) and not (root / CONTRACT).exists():
        return [str(fallback or sys.executable), str(entry), *arguments], dict(os.environ)
    # -B prevents writes but still reads stale .pyc files. A unique, non-created
    # cache prefix also prevents loading old source caches after an update.
    cache = root / "runtime/fabric-editor" / (".bytecode-" + uuid.uuid4().hex)
    return [str(managed_python(root)), "-I", "-B", "-X", f"pycache_prefix={cache}", str(entry), *arguments], isolated_environment()
