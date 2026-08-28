from __future__ import annotations

import base64
import json
import math
import os
import struct
import urllib.error
import urllib.request
import uuid
import zlib


API = os.environ.get("KFPS_COMMUNITY_API_URL", "http://127.0.0.1:8790/v1").rstrip("/")
TEST_AUTH_TOKEN = os.environ.get("KFPS_COMMUNITY_TEST_AUTH_TOKEN", "").strip()
CLIENT_VERSION = os.environ.get("KFPS_APP_VERSION", "3.0.81").strip()
INSTALLATION_ID = "kfps-community-artificial-seed-20260718"
USERNAME = "KFPS_Test_Gallery"


def request(path: str, method: str = "GET", payload=None, token: str = ""):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "User-Agent": "KFPS-Community-Staging-Seed/1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    if TEST_AUTH_TOKEN:
        headers["X-Community-Test-Token"] = TEST_AUTH_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read(256 * 1024).decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {
                "error": "non_json_http_error",
                "status": error.code,
                "content_type": error.headers.get("Content-Type", ""),
                "body_excerpt": raw[:1000],
            }
        return error.code, body


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def preview_png(index: int, size: int = 256) -> bytes:
    palette = [
        (239, 68, 129), (45, 180, 168), (239, 190, 64), (87, 125, 220),
        (210, 88, 203), (234, 112, 60), (99, 194, 96), (215, 76, 76),
    ]
    accent = palette[index % len(palette)]
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            dx = x - size / 2
            dy = y - size / 2
            radius = math.hypot(dx, dy)
            stripe = ((x + y + index * 13) // 18) % 2
            if radius < size * (0.20 + (index % 4) * 0.025):
                color = (248, 238, 244, 255)
            elif radius < size * 0.39:
                color = (*accent, 255)
            elif stripe:
                color = (35, 28, 35, 255)
            else:
                color = (18, 13, 18, 255)
            row.extend(color)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(raw, 9))
        + png_chunk(b"IEND", b"")
    )


def design(index: int):
    shapes = [{"type": 1, "data": [0, 0, 1000, 1000], "color": [0, 0, 0, 0]}]
    for layer in range(8 + index * 3):
        angle = layer * (360 / (8 + index * 3))
        shapes.append({
            "type": 2 if layer % 2 else 16,
            "data": [
                round(math.cos(math.radians(angle)) * (80 + index * 4), 3),
                round(math.sin(math.radians(angle)) * (80 + index * 4), 3),
                22 + index,
                8 + (layer % 5),
                angle,
            ],
            "color": [(index * 37 + layer * 11) % 256, (80 + layer * 17) % 256, (170 + index * 13) % 256, 255],
            "score": layer / 1000,
        })
    return {"format": "kfps.primitive.v1", "shapes": shapes}


def main() -> int:
    status, catalog = request("/artworks?limit=60&sort=name")
    if status != 200:
        raise SystemExit(f"Catalog lookup failed: {catalog}")
    existing_titles = {str(item.get("title") or "") for item in catalog.get("items", [])}

    tokens = []
    for batch in range(2):
        installation_id = (INSTALLATION_ID + "-" + uuid.UUID(int=0).hex) if batch == 0 else (
            INSTALLATION_ID + f"-{batch}-" + uuid.UUID(int=0).hex
        )
        status, auth = request("/auth/test", "POST", {
            "installation_id": installation_id,
            "display_name": f"Artificial catalog seed {batch + 1}",
        })
        if status != 200:
            raise SystemExit(f"Authentication failed for seed batch {batch + 1}: {auth}")
        token = auth["token"]
        if auth.get("username_required"):
            username = USERNAME if batch == 0 else USERNAME + "_Two"
            status, chosen = request(
                "/profile/username", "POST", {"username": username, "confirm_username": username}, token
            )
            if status != 200:
                raise SystemExit(f"Username setup failed for seed batch {batch + 1}: {chosen}")
        tokens.append(token)

    categories = ["Characters", "Motorsport", "Logos", "Gaming", "Abstract", "Patterns", "Humor", "Original Artwork"]
    games = [["FH6"], ["FH5", "FH6"], ["FM8"], ["FH6", "FM8"]]
    created = 0
    duplicates = 0
    for index in range(16):
        title = f"Artificial Gallery {index + 1:02d}"
        if title in existing_titles:
            duplicates += 1
            continue
        payload = {
            "client_version": CLIENT_VERSION,
            "title": title,
            "description": "Procedural test fixture for community browsing, filtering, caching, and layout verification.",
            "category": categories[index % len(categories)],
            "classification": "handmade" if index % 2 == 0 else "toolmade",
            "tags": ["artificial", "test", f"set-{index % 4 + 1}"],
            "games": games[index % len(games)],
            "license": "kfps-community-share-v1",
            "confirm_rights": True,
            "design": design(index),
            "preview_base64": base64.b64encode(preview_png(index)).decode("ascii"),
            "thumbnail_base64": base64.b64encode(preview_png(index)).decode("ascii"),
        }
        status, result = request("/artworks", "POST", payload, tokens[index // 8])
        if status == 201:
            created += 1
        elif status == 409 and result.get("error", "").startswith("duplicate"):
            duplicates += 1
        else:
            print(f"Fixture {index + 1} failed: HTTP {status}: {result}")
    print(f"Artificial catalog ready: {created} created, {duplicates} already present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
