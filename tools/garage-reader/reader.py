"""On-demand Garage worker. No network, persistent output or save writes."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main(*, catalogue=False):
    if sys.argv[1:] not in (["--stdin"], ["--check"]):
        return 2
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    try:
        from distribution import verify
        verify(root)
        sys.path.insert(0, str(root / "vendor"))
        from profile_support import load_support
        from profile_reader import MAX_INPUT, MAX_EXPORT, decode
        support = load_support(root / "support" / "profile-support.dll", "gamedb" if catalogue else "profiledata")
        if catalogue:
            from catalogue_reader import MAX_INPUT, MAX_OUTPUT as MAX_EXPORT, read_catalogue
    except Exception:
        return 3
    if sys.argv[1:] == ["--check"]:
        sys.stdout.write('{"ready":true}\n')
        return 0
    try:
        data = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not data or len(data) > MAX_INPUT:
            return 2
        if catalogue:
            output = read_catalogue(data, support)
        else:
            result = decode(data, support)
            output = json.dumps(result.garage, ensure_ascii=True, allow_nan=False,
                                separators=(",", ":")).encode("ascii")
        if len(output) > MAX_EXPORT:
            return 2
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
