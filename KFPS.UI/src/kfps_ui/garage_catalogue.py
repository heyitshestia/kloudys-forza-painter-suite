"""On-demand FH6 catalogue and installed stock thumbnails, for a worker thread.

The existing vehicle index supplies identity; RC<n>.zip supplies only exact-ID
Thumbnail_<ID>_Big.swatchbin assets. Saved-livery artwork is never a fallback.
No network, game writes, GPU work, timers or persistent decoded-image cache.
Missing images have an empty URL. Cancellation raises InterruptedError.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import sys
import tempfile
import time
import zipfile
import zlib

APP_ROOT = Path(__file__).resolve().parents[3]
MAX_CARS = 4096
MAX_ARCHIVES = 64
MAX_DIRECTORY_ENTRIES = 8192
MAX_ZIP_ENTRIES = 8192
MAX_ZIP_BYTES = 128 * 1024 * 1024
MAX_CENTRAL_BYTES = 2 * 1024 * 1024
MAX_TEXTURE_BYTES = 2 * 1024 * 1024
MAX_TEXTURE_PIXELS = 1024 * 1024
MAX_THUMBNAIL_BYTES = 128 * 1024
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 45
THUMBNAIL_SIZE = (320, 180)
PIPELINE = "garage-stock-320x180-v1"
_ARCHIVE = re.compile(r"RC([0-9]{1,3})\.zip\Z", re.IGNORECASE)
_MEMBER = re.compile(r"Thumbnail_([1-9][0-9]{0,9})_Big\.swatchbin\Z", re.IGNORECASE)
_CACHE_FILE = re.compile(r"[0-9a-f]{64}\.png\Z")


class _Invalid(ValueError):
    pass


class _TimeLimit(RuntimeError):
    pass


class _Budget:
    def __init__(self, cancel):
        self.cancel = cancel
        self.deadline = time.monotonic() + MAX_SECONDS
        self.cancelled = False
        self.rows = []

    def is_set(self):
        if self.cancelled:
            return True
        if self.cancel is not None:
            stopped = self.cancel() if callable(self.cancel) else self.cancel.is_set()
            if stopped:
                self.cancelled = True
                return True
        if time.monotonic() > self.deadline:
            raise _TimeLimit("Catalogue time limit reached")
        return False

    def wait(self, seconds):
        self.check()
        if self.cancel is not None and hasattr(self.cancel, "wait"):
            self.cancel.wait(min(seconds, .025))
        else:
            time.sleep(min(seconds, .025))
        self.check()

    def check(self):
        if self.is_set():
            raise InterruptedError("Garage catalogue loading cancelled.")


def _studio_imports():
    # Existing local parsers are shared with Studio, not copied from a reference.
    path = str(APP_ROOT / "tools/livery-studio/src")
    if path not in sys.path:
        sys.path.insert(0, path)
    from kfps_livery_lab import material_assets, catalogue_cache, part_names
    from kfps_livery_lab.storage_paths import SafeRoot, StorageError
    return material_assets, catalogue_cache, part_names, SafeRoot, StorageError


def _stamp(path):
    info = Path(path).stat()
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def catalogue_signature(game_folder, cancel=None):
    """Cheap, bounded source check on a worker; no archive reads or idle polling."""
    budget = _Budget(cancel)
    game = Path(game_folder).expanduser().resolve()
    if (game / 'Content/media').is_dir():
        game = game / 'Content'
    records = []
    for relative, pattern in (('media/cars', None), ('media/stripped', _ARCHIVE)):
        budget.check()
        directory = game / relative
        try:
            with os.scandir(directory) as entries:
                for count, entry in enumerate(entries, 1):
                    budget.check()
                    if count > MAX_DIRECTORY_ENTRIES:
                        raise _Invalid('Catalogue directory entry limit')
                    if (pattern.fullmatch(entry.name) if pattern else entry.name.lower().endswith('.zip')):
                        if entry.is_file(follow_symlinks=False):
                            records.append((relative + '/' + entry.name, _stamp(entry.path)))
        except FileNotFoundError:
            records.append((relative, None))
    for relative in ('media/stripped/gamedbRC.slt', 'media/stripped/stringtables/EN.zip'):
        budget.check()
        try:
            stamp = _stamp(game / relative)
        except FileNotFoundError:
            stamp = None
        records.append((relative, stamp))
    budget.check()
    return hashlib.sha256(json.dumps([str(game), sorted(records)]).encode()).hexdigest()


def _cars(game, index_path, cache_root, budget):
    if str(APP_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_ROOT))
    from tools.livery.vehicle_assets import load_or_build_vehicle_asset_index, VehicleAssetError
    _, cache, _, SafeRoot, _ = _studio_imports()
    path = Path(index_path).absolute() if index_path else Path(cache_root).absolute() / "vehicle-index.json"
    resolved = path.resolve()
    if (resolved.is_relative_to(game) or
            (resolved.is_relative_to(APP_ROOT) and not resolved.is_relative_to(APP_ROOT / "runtime"))):
        # Still permit a read-only in-memory index when persistence is forbidden.
        path = None
    budget.check()
    try:
        if path is None:
            vehicles = load_or_build_vehicle_asset_index(game, cancel_event=budget)
        else:
            store = SafeRoot(path.parent)
            store.check(path, missing=True, directory=False)
            store.mkdir(store.root)
            with cache._pin_windows_directories(store):
                vehicles = load_or_build_vehicle_asset_index(game, path, cancel_event=budget)
    except VehicleAssetError as exc:
        raise _Invalid("Installed vehicle index unavailable") from exc
    if not 0 < len(vehicles) <= MAX_CARS:
        raise _Invalid("Vehicle count limit")
    rows = []
    for ident, asset in vehicles.items():
        budget.check()
        model = asset.model_code
        rows.append({"carId": ident, "title": model.replace("_", " "),
                     "modelCode": model, "thumbnailUrl": ""})
    return sorted(rows, key=lambda row: row["carId"])


@contextmanager
def _archive(path, budget):
    """Bound central-directory allocation before ZipFile parses any entries."""
    budget.check()
    before = _stamp(path)
    if not 22 <= before[0] <= MAX_ZIP_BYTES:
        raise _Invalid("Archive size limit")
    with Path(path).open("rb") as stream:
        stream.seek(max(0, before[0] - 65557))
        tail = stream.read(65557)
        position = tail.rfind(b"PK\x05\x06")
        if position < 0 or len(tail) - position < 22:
            raise _Invalid("Archive directory missing")
        _, disk, central_disk, disk_count, count, size, offset, comment = struct.unpack_from(
            "<4s4H2IH", tail, position)
        if (disk or central_disk or disk_count != count or count > MAX_ZIP_ENTRIES
                or size > MAX_CENTRAL_BYTES or offset + size > before[0] - 22
                or len(tail) - position != 22 + comment or count == 65535):
            raise _Invalid("Archive directory limit")
        stream.seek(0)
        with zipfile.ZipFile(stream) as bundle:
            if len(bundle.infolist()) != count:
                raise _Invalid("Archive directory mismatch")
            yield bundle
    budget.check()
    if _stamp(path) != before:
        raise _Invalid("Archive changed")


def _member_bytes(bundle, info, maximum, budget):
    if (info.flag_bits & 1 or not 0 < info.file_size <= maximum
            or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
        raise _Invalid("Archive member limit")
    budget.check()
    with bundle.open(info) as stream:
        data = stream.read(maximum + 1)
    if len(data) != info.file_size:
        raise _Invalid("Archive member size")
    budget.check()
    return data


def _sources(game, ids, budget):
    paths, result = [], {}
    with os.scandir(game / "media/Stripped") as entries:
        for count, entry in enumerate(entries, 1):
            budget.check()
            if count > MAX_DIRECTORY_ENTRIES:
                raise _Invalid("Directory entry limit")
            if _ARCHIVE.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                paths.append(Path(entry.path))
                if len(paths) > MAX_ARCHIVES:
                    raise _Invalid("Archive count limit")
    for path in sorted(paths):
        budget.check()
        try:
            stamp = _stamp(path)
            found = []
            with _archive(path, budget) as bundle:
                for info in bundle.infolist():
                    budget.check()
                    match = _MEMBER.fullmatch(info.filename)
                    if match and int(match[1]) in ids:
                        found.append((int(match[1]), info))
            for ident, info in found:
                source = (path, stamp, info)
                result[ident] = None if ident in result else source
        except InterruptedError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, NotImplementedError):
            continue
    return result


def _decode_thumbnail(data, *, cache_key=""):
    """Adapt verified premultiplied PC TXCH data, then use the existing decoder."""
    material, _, _, _, _ = _studio_imports()
    from PIL import Image, ImageOps
    from PIL.PngImagePlugin import PngInfo
    if not 20 <= len(data) <= MAX_TEXTURE_BYTES or data[:4] != b"burG":
        raise _Invalid("Texture size or format")
    version = tuple(data[4:6])
    if version not in ((0, 0), (1, 0), (1, 1)):
        raise _Invalid("Texture version")
    start = 20 if version == (1, 1) else 16
    count = struct.unpack_from("<I" if start == 20 else "<H", data, 16 if start == 20 else 6)[0]
    if not 1 <= count <= 64 or start + count * 24 > len(data):
        raise _Invalid("Texture blob limit")
    headers = []
    for index in range(count):
        tag, _, _, count_meta, meta, _, _, _ = struct.unpack_from("<IBBHIIII", data, start + index * 24)
        if tag != 0x54584342:
            continue
        if not 1 <= count_meta <= 64 or meta + count_meta * 8 > len(data):
            raise _Invalid("Texture metadata limit")
        for entry in range(meta, meta + count_meta * 8, 8):
            tag, flags, relative = struct.unpack_from("<IHH", data, entry)
            if tag == 0x54584348:
                header = entry + relative
                if flags >> 4 < 64 or header + (flags >> 4) > len(data):
                    raise _Invalid("Texture header limit")
                headers.append(header)
    if len(headers) != 1:
        raise _Invalid("Texture header count")
    header = headers[0]
    width, height = struct.unpack_from("<II", data, header + 24)
    if not 0 < width * height <= MAX_TEXTURE_PIXELS:
        raise _Invalid("Thumbnail pixel limit")
    premultiplied = bool(data[header + 39] & 2)
    adapted = bytearray(data)
    adapted[header + 39] &= ~2
    image, _ = material.decode_swatchbin(bytes(adapted))
    try:
        if premultiplied:
            with Image.frombytes("RGBa", image.size, image.tobytes()) as associated:
                straight = associated.convert("RGBA")
            image.close()
            image = straight
        with ImageOps.pad(image, THUMBNAIL_SIZE, method=Image.Resampling.LANCZOS,
                          color=(0, 0, 0, 0)) as small:
            output = io.BytesIO()
            provenance = PngInfo()
            provenance.add_text("kfps-stock-key", cache_key)
            small.save(output, format="PNG", pnginfo=provenance)
            return output.getvalue()
    finally:
        image.close()


def _titles(game, rows, budget):
    """Refresh installed metadata on catalogue changes; reuse its durable cache."""
    _, cache, names, SafeRoot, StorageError = _studio_imports()
    result = {}
    try:
        existing = cache.load_installed_catalogue(game, cancel_event=budget)
        if not existing.get('database'):
            return result
        strings = {}
        with _archive(game / "media/stripped/stringtables/EN.zip", budget) as bundle:
            for table in ("Data_Car", "List_CarMake"):
                matches = [entry for entry in bundle.infolist() if entry.filename == table + ".str"]
                if len(matches) != 1:
                    return result
                strings.update(names._parse_strings(
                    _member_bytes(bundle, matches[0], names.MAX_STRING_BYTES, budget), table))
        with closing(sqlite3.connect(":memory:")) as db:
            db.deserialize(existing['database'])
            db.execute("PRAGMA query_only=ON")
            ticks = 0
            def progress():
                nonlocal ticks
                ticks += 1
                return int(budget.is_set() or ticks > 10000)
            db.set_progress_handler(progress, 1000)
            models = {row["carId"]: row["modelCode"].lower() for row in rows}
            for ident, model, year, title, make in db.execute(
                    "SELECT Id,MediaName,Year,DisplayName,MakeName FROM Data_Car LIMIT 4097"):
                budget.check()
                if type(ident) is not int or not isinstance(model, str) or models.get(ident) != model.lower():
                    continue
                title, make = names._localized(title, strings), names._localized(make, strings)
                if title and make and type(year) is int and 1880 <= year <= 2200:
                    label = f"{year} {make} {title}"
                    if len(label) <= 240 and not any(ord(char) < 32 for char in label):
                        result[ident] = {'title': label, 'manufacturer': make,
                                         'modelName': title, 'year': year}
    except InterruptedError:
        raise
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, StorageError, struct.error):
        budget.check()
    return result


def _publish(store, path, data, budget):
    store.check(path, missing=True, directory=False)
    descriptor, temporary = tempfile.mkstemp(prefix=".thumb-", suffix=".tmp", dir=store.root)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        budget.check()
        store.check(path, missing=True, directory=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _cached_png(store, path):
    from PIL import Image
    data = store.read(path, MAX_THUMBNAIL_BYTES)
    with Image.open(io.BytesIO(data)) as image:
        if (image.format != "PNG" or image.size != THUMBNAIL_SIZE
                or image.info.get("kfps-stock-key") != path.stem):
            raise _Invalid("Cached thumbnail format")
        image.verify()
    return len(data)


def _cache_files(store, wanted, budget):
    used = 0
    with os.scandir(store.root) as entries:
        for count, entry in enumerate(entries, 1):
            budget.check()
            if count > MAX_DIRECTORY_ENTRIES:
                raise _Invalid("Cache directory limit")
            name, path = entry.name, Path(entry.path)
            managed = bool(_CACHE_FILE.fullmatch(name))
            temporary = name.startswith(".thumb-") and name.endswith(".tmp")
            if not managed and not temporary:
                continue
            info = store.check(path, directory=False)
            if temporary or name not in wanted or used + info.st_size > MAX_CACHE_BYTES:
                path.unlink()
            else:
                used += info.st_size
    return used


def load_catalogue(game_folder, index_path, cache_root, cancel=None):
    """Return {cars: [{carId,title,modelCode,thumbnailUrl}], status: str}.

    Call on demand from a background worker. ``cancel`` may be an Event or a
    no-argument predicate. The shared vehicle-index loader automatically builds
    missing/stale indexes and validates the selected installation. ``index_path``
    may be None to use ``cache_root/vehicle-index.json``.
    ``cache_root/stock-thumbnails-v1`` is exclusively owned by this module;
    only recognized cache files there are pruned, under a cancellable lock.
    """
    budget = _Budget(cancel)
    try:
        return _load_catalogue(game_folder, index_path, cache_root, budget)
    except InterruptedError:
        raise
    except _TimeLimit:
        return {"cars": budget.rows, "status": "Catalogue time limit reached; retry to resume cached work."}
    except (ImportError, OSError, ValueError, TypeError):
        budget.check()
        return {"cars": budget.rows, "status": "Stock catalogue assets or cache unavailable."}


def _load_catalogue(game_folder, index_path, cache_root, budget):
    budget.check()
    game = Path(game_folder).expanduser().resolve()
    if (game / "Content/media").is_dir():
        game = game / "Content"
    try:
        rows = _cars(game, index_path, cache_root, budget)
    except InterruptedError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        budget.check()
        return {"cars": [], "status": "Vehicle catalogue unavailable; check the linked FH6 game folder."}
    budget.rows = rows
    try:
        titles = _titles(game, rows, budget)
        for row in rows:
            row.update(titles.get(row["carId"], {}))
        sources = _sources(game, {row["carId"] for row in rows}, budget)
    except InterruptedError:
        raise
    except (OSError, ValueError):
        sources = {}
    budget.check()
    _, cache, _, SafeRoot, StorageError = _studio_imports()
    try:
        destination = Path(cache_root).absolute() / "stock-thumbnails-v1"
        if destination.resolve().is_relative_to(game):
            raise _Invalid("Game writes prohibited")
        if (destination.resolve().is_relative_to(APP_ROOT)
                and not destination.resolve().is_relative_to(APP_ROOT / "runtime")):
            raise _Invalid("Project assets must stay in runtime")
        store = SafeRoot(destination)
        store.mkdir(store.root)
        with cache._pin_windows_directories(store), cache._lock(store, budget):
            jobs = {}
            for row in rows:
                source = sources.get(row["carId"])
                if source is None:
                    continue
                path, stamp, info = source
                key = hashlib.sha256(json.dumps([PIPELINE, str(path.resolve()), stamp,
                    row["carId"], row["modelCode"], info.filename, info.CRC, info.file_size]).encode()).hexdigest()
                jobs[row["carId"]] = (source, store.root / (key + ".png"))
            used = _cache_files(store, {path.name for _, path in jobs.values()}, budget)
            by_archive = {}
            for row in rows:
                budget.check()
                job = jobs.get(row["carId"])
                if job is None:
                    continue
                (source, stamp, info), target = job
                by_archive.setdefault(source, []).append((row, stamp, info, target))
            for source, work in by_archive.items():
                try:
                    if _stamp(source) != work[0][1]:
                        continue
                    with _archive(source, budget) as bundle:
                        for row, stamp, info, target in work:
                            budget.check()
                            try:
                                try:
                                    _cached_png(store, target)
                                except (OSError, ValueError, StorageError):
                                    old = store.check(target, missing=True, directory=False)
                                    if old is not None:
                                        target.unlink()
                                        used -= old.st_size
                                    data = _member_bytes(bundle, info, MAX_TEXTURE_BYTES, budget)
                                    png = _decode_thumbnail(data, cache_key=target.stem)
                                    budget.check()
                                    if len(png) > MAX_THUMBNAIL_BYTES or used + len(png) > MAX_CACHE_BYTES:
                                        continue
                                    if _stamp(source) != stamp:
                                        raise _Invalid("Archive changed")
                                    _publish(store, target, png, budget)
                                    used += _cached_png(store, target)
                                row["thumbnailUrl"] = target.as_uri()
                            except InterruptedError:
                                raise
                            except (OSError, ValueError, StorageError, zipfile.BadZipFile,
                                    NotImplementedError, struct.error, zlib.error):
                                continue
                    if _stamp(source) != work[0][1]:
                        raise _Invalid("Archive changed")
                except _TimeLimit:
                    for row, _, _, _ in work:
                        row["thumbnailUrl"] = ""
                    raise
                except InterruptedError:
                    raise
                except (OSError, ValueError, zipfile.BadZipFile):
                    for row, _, _, _ in work:
                        row["thumbnailUrl"] = ""
    except InterruptedError:
        raise
    except (OSError, ValueError, StorageError):
        pass
    budget.check()
    count = sum(bool(row["thumbnailUrl"]) for row in rows)
    return {"cars": rows, "status": f"{len(rows)} catalogue cars; {count} stock thumbnails available."}
