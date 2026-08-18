from __future__ import annotations

from collections.abc import Callable
import re


def versioned_asset_url(url: str, digest: str) -> str:
    url = str(url or "")
    digest = str(digest or "").strip().lower()
    if not url or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={digest[:16]}"


def normalize_artwork(item: dict, resolve_url: Callable[[str], str]) -> dict:
    creator = dict(item.get("creator") or {})
    supporter_only = bool(item.get("supporter_only"))
    featured = bool(item.get("featured"))
    preview_digest = str(item.get("preview_sha256") or "")
    thumbnail_digest = str(item.get("thumbnail_sha256") or preview_digest)
    preview_asset_url = versioned_asset_url(
        resolve_url(str(item.get("preview_url") or "")), preview_digest,
    )
    thumbnail_asset_url = versioned_asset_url(
        resolve_url(str(item.get("thumbnail_url") or item.get("preview_url") or "")),
        thumbnail_digest,
    )
    classification = str(item.get("classification") or "toolmade")
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or "Untitled"),
        "description": str(item.get("description") or ""),
        "category": str(item.get("category") or "Other"),
        "classification": classification,
        "classificationLabel": "Handmade" if classification == "handmade" else "Toolmade",
        "tagsText": ", ".join(str(value) for value in item.get("tags", [])),
        "gamesText": ", ".join(str(value) for value in item.get("games", [])),
        "license": str(item.get("license") or "kfps-community-share-v1"),
        "schemaId": str(item.get("source_schema") or "legacy-kfps"),
        "schemaLabel": str(item.get("schema_label") or "KFPS-compatible JSON"),
        "schemaKnown": bool(item.get("schema_known", True)),
        "schemaWarning": str(item.get("schema_warning") or ""),
        "shapeCount": int(item.get("shape_count") or 0),
        "groupCount": int(item.get("group_count") or 0),
        "usesMasks": bool(item.get("uses_masks")),
        "status": str(item.get("status") or "published"),
        "statusLabel": str(item.get("status") or "published").replace("_", " ").title(),
        "rejectionReason": str(item.get("rejection_reason") or ""),
        "featured": featured,
        "supporterOnly": supporter_only,
        "supporterLabel": "Supporters" if supporter_only else "Everyone",
        "revision": int(item.get("current_revision") or 1),
        "downloads": int(item.get("downloads") or 0),
        "favorites": int(item.get("favorites") or 0),
        "favorited": bool(item.get("favorited")),
        "createdAt": str(item.get("created_at") or ""),
        "updatedAt": str(item.get("updated_at") or ""),
        "publishedAt": str(item.get("published_at") or ""),
        "previewUrl": thumbnail_asset_url if supporter_only and featured else ("" if supporter_only else preview_asset_url),
        "thumbnailUrl": thumbnail_asset_url if supporter_only and featured else ("" if supporter_only else thumbnail_asset_url),
        "downloadUrl": resolve_url(str(item.get("download_url") or "")),
        "contentSha256": str(item.get("content_sha256") or ""),
        "previewSha256": preview_digest,
        "thumbnailSha256": thumbnail_digest,
        "creatorName": str(creator.get("username") or "Unknown"),
        "creatorAvatar": str(creator.get("avatar_url") or ""),
        "creatorBio": str(creator.get("bio") or ""),
        "creatorFollowers": int(creator.get("follower_count") or 0),
        "creatorFollowed": bool(creator.get("followed")),
        "_previewAssetUrl": preview_asset_url,
        "_thumbnailAssetUrl": thumbnail_asset_url,
    }
