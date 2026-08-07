"""Filename sanitization and collision handling."""

from __future__ import annotations

import re
from pathlib import Path

_MAX_STEM = 120
_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_stem(name: str, fallback: str) -> str:
    """Return a safe stem for a file: keep [A-Za-z0-9._-], collapse other
    runs to a single underscore, strip leading dots/dashes, cap length.
    Empty results fall back to `fallback`."""
    cleaned = _ALLOWED.sub("_", name).strip("._- ")
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned[: _MAX_STEM].rstrip("._- ")
    if not cleaned:
        cleaned = fallback
    return cleaned


def unique_path(dest_dir: Path, stem: str, ext: str, *, taken: set[str] | None = None) -> Path:
    """Pick a non-colliding path under dest_dir.

    Collision detection considers both `taken` (names already planned this
    run) and files already on disk. Appends " (1)", " (2)", ... as needed.
    """
    taken = set(taken or ())
    ext = ext.lstrip(".")
    candidate = f"{stem}.{ext}"
    counter = 1
    while candidate in taken or (dest_dir / candidate).exists():
        candidate = f"{stem} ({counter}).{ext}"
        counter += 1
    return dest_dir / candidate
