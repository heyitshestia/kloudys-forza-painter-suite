"""Short, extension-safe names for self-contained generator runs."""

import hashlib
import os
import re
from pathlib import Path


MAX_PATH_UNITS = 259
MAX_STEM = 40
MIN_STEM = 12
# Includes a subfolder, checkpoint/preview suffix and atomic-write temporary name.
ARTIFACT_OVERHEAD = 64
RUN_VERSION_RESERVE = 6


def path_units(path):
    return len(str(Path(path).absolute()).encode("utf-16-le")) // 2


def _short_stem(label, identity, limit, always_hash=False):
    if limit < MIN_STEM:
        raise ValueError(
            "The generation output folder is too deeply nested even for short filenames. "
            "No generation files were written. Use a shorter KFPS folder path."
        )
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_") or "image"
    reserved = re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", safe, re.IGNORECASE)
    if not always_hash and safe == label and not reserved and len(safe) <= limit:
        return safe
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:MIN_STEM]
    prefix = safe[:max(0, limit - len(digest) - 1)].rstrip("_-")
    return f"{prefix}-{digest}" if prefix else digest


def generation_run_stem(image_path, generated_root):
    image_path = Path(image_path)
    limit = min(MAX_STEM, MAX_PATH_UNITS - path_units(generated_root) - 1
                - RUN_VERSION_RESERVE - ARTIFACT_OVERHEAD - MIN_STEM)
    identity = os.path.normcase(str(image_path.resolve()))
    return _short_stem(image_path.stem, identity, limit, always_hash=True)


def generation_artifact_stem(image_path, output_dir=None):
    limit = MAX_STEM
    if output_dir is not None:
        limit = min(limit, MAX_PATH_UNITS - path_units(output_dir) - ARTIFACT_OVERHEAD)
    image_path = Path(image_path)
    return _short_stem(image_path.stem, image_path.name, limit)


def legacy_artifact_stem(image_path):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", Path(image_path).stem).strip("_") or "image"


def recovery_checkpoint_stem(image_path, output_dir):
    current = generation_artifact_stem(image_path, output_dir)
    folder = Path(output_dir) / "checkpoints"
    if folder.is_dir():
        names = {path.name for path in folder.iterdir() if path.is_file()}
        for stem in (current, legacy_artifact_stem(image_path)):
            pattern = re.compile(re.escape(stem) + r"(?:\.\d+)?\.json$")
            if any(pattern.fullmatch(name) for name in names):
                return stem
    return current
