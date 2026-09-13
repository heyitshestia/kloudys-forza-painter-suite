"""Create deterministic, non-personal image inputs for editor storage tests."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    if not output.is_relative_to(root / "runtime" / "test-runs"):
        raise ValueError("Capacity fixtures must stay inside test runs")
    output.mkdir(parents=True, exist_ok=False)
    generator = np.random.default_rng(7731)
    pixels = generator.integers(0, 256, size=(4000, 6000, 3), dtype=np.uint8)
    records = []
    for name, data in (("reference-noise-24mp.png", pixels), ("reference-small.png", pixels[:512, :512])):
        path = output / name
        with Image.fromarray(data) as image:
            image.save(path, compress_level=1)
        with Image.open(path) as reopened:
            if not np.array_equal(np.asarray(reopened), data):
                raise AssertionError("Fixture pixels changed during encoding")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append({"name": name, "width": data.shape[1], "height": data.shape[0],
                        "bytes": path.stat().st_size, "sha256": digest})
    (output / "manifest.json").write_text(json.dumps({"seed": 7731, "files": records}, indent=2), encoding="utf-8")
    print(json.dumps(records))


if __name__ == "__main__":
    main()
