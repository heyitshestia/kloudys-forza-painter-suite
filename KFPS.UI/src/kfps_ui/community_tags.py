"""Local tag suggestions and validation matching the community API's tag format."""
from __future__ import annotations

import unicodedata


MAX_TAGS = 10
MAX_TAG_LENGTH = 24
SUGGESTED_TAGS = (
    "abstract", "anime", "cartoon", "characters", "colorful", "cute", "dark",
    "drift", "fan art", "fantasy", "flags", "floral", "funny", "futuristic",
    "gaming", "geometric", "gradient", "graffiti", "itasha", "lettering",
    "logos", "manga", "minimalist", "monochrome", "motorsport", "nature",
    "numbers", "original art", "patterns", "portrait", "racing", "rally",
    "realistic", "retro", "sci-fi", "space", "street", "stripes", "track",
)


def prepare_tags(current: list[str], entered: str) -> dict:
    """Validate the whole addition before committing, including comma-separated paste."""
    tags = list(current)
    seen = {tag.lower() for tag in tags}
    for value in str(entered).split(","):
        tag = value.strip()
        if not tag:
            continue
        letters_or_numbers = [unicodedata.category(char)[0] in {"L", "N"} for char in tag]
        if not letters_or_numbers[0] or any(
            not valid and char not in " _.-" for char, valid in zip(tag, letters_or_numbers)
        ):
            return {"tags": current, "error": "Start tags with a letter or number. Use only letters, numbers, spaces, hyphens, underscores or dots."}
        # The server measures JavaScript string length, including two units for astral letters.
        if len(tag.encode("utf-16-le")) // 2 > MAX_TAG_LENGTH:
            return {"tags": current, "error": f"Keep each tag to {MAX_TAG_LENGTH} characters or fewer."}
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        return {"tags": current, "error": f"You can add up to {MAX_TAGS} tags. Remove one before adding another."}
    return {"tags": tags, "error": ""}
