"""Translate Soundfetch filters to stable Openverse audio parameters."""

from __future__ import annotations

LICENSE_CODES = {
    "cc0": "cc0",
    "cc-by": "by",
    "cc-by-sa": "by-sa",
    "cc-by-nc": "by-nc",
    "cc-by-nd": "by-nd",
    "cc-by-nc-sa": "by-nc-sa",
    "cc-by-nc-nd": "by-nc-nd",
    "pdm": "pdm",
}


def build_params(filters: dict[str, str]) -> dict[str, str]:
    """Return only stable, deliberately supported Openverse parameters."""
    result: dict[str, str] = {}
    licenses = _values(filters.get("license"))
    if licenses and "any" not in licenses:
        mapped = [LICENSE_CODES[value] for value in licenses if value in LICENSE_CODES]
        if mapped:
            result["license"] = ",".join(mapped)

    for key in ("category", "source", "extension", "length"):
        values = _values(filters.get(key))
        if values:
            result[key] = ",".join(values)
    return result


def _values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
