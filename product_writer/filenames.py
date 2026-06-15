from __future__ import annotations

import re
from hashlib import md5

WINDOWS_ILLEGAL_CHARS = r'<>:"/\|?*'
_ILLEGAL_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACE_PATTERN = re.compile(r"\s+")


def safe_filename(name: str, max_length: int = 80, default: str = "untitled") -> str:
    name = name.translate(str.maketrans({"?": "？", ":": "："}))
    cleaned = _ILLEGAL_PATTERN.sub("_", name).strip().strip(".")
    cleaned = _SPACE_PATTERN.sub(" ", cleaned)
    if not cleaned:
        cleaned = default
    if len(cleaned) <= max_length:
        return cleaned
    digest = md5(cleaned.encode("utf-8")).hexdigest()[:8]
    keep = max_length - len(digest) - 1
    return f"{cleaned[:keep].rstrip()}_{digest}"
