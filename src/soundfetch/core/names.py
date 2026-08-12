"""Filename sanitization and collision handling."""

from __future__ import annotations

import re
from pathlib import Path

_MAX_STEM = 120
_MAX_EXT = 12
_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")
_EXT_ALLOWED = re.compile(r"[^A-Za-z0-9]+")


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


def sanitize_ext(ext: str | None, fallback: str) -> str:
    """Return a safe file extension: strip a leading dot, keep only
    [A-Za-z0-9], cap length. Empty results fall back to `fallback`.

    Extensions arrive from remote providers (Freesound's `type`, yt-dlp's
    `ext`) or a replayed manifest's `file_format` and are never a path
    component we can trust as-is — unlike the stem, a bare `.lstrip(".")`
    leaves `/` and `..` intact, so a value like
    `../../../home/x/.bashrc` would otherwise survive into the joined
    filename `unique_path` builds.
    """
    cleaned = _EXT_ALLOWED.sub("", (ext or "").lstrip("."))
    cleaned = cleaned[:_MAX_EXT]
    if not cleaned:
        cleaned = fallback
    return cleaned


def unique_path(dest_dir: Path, stem: str, ext: str, *, taken: set[str] | None = None) -> Path:
    """Pick a non-colliding path under dest_dir.

    Collision detection considers both `taken` (names already planned this
    run) and files already on disk. Appends " (1)", " (2)", ... as needed.

    `stem`/`ext` are expected to already be sanitized (`sanitize_stem` /
    `sanitize_ext`); this additionally asserts the resulting path can't
    resolve outside `dest_dir`, so a caller that skips sanitization fails
    loudly here instead of silently writing outside the output directory.
    """
    taken = set(taken or ())
    ext = ext.lstrip(".")
    candidate = f"{stem}.{ext}"
    counter = 1
    while candidate in taken or (dest_dir / candidate).exists():
        candidate = f"{stem} ({counter}).{ext}"
        counter += 1
    result = dest_dir / candidate
    if not result.resolve().is_relative_to(dest_dir.resolve()):
        raise ValueError(f"unsafe filename escapes destination directory: {candidate!r}")
    return result
