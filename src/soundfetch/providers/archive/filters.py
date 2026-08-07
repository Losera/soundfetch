"""Translate provider-agnostic filters into an Internet Archive query clause.

IA has no `license` enum like Freesound's — items publish a free-text
`licenseurl`. The patterns below match the Creative Commons URL shapes IA
items actually use in practice (confirmed against live items during
implementation), not an exhaustive enumeration; fix here if a live query
ever misses an obvious case. `duration` and `gen_ai` have no IA equivalent
and are silently ignored rather than erroring, since a caller may be
fanning the same filters out to multiple providers at once.
"""

from __future__ import annotations

LICENSE_PATTERNS: dict[str, str] = {
    "cc0": "licenseurl:(*publicdomain* OR *cc0*)",
    "cc-by": "licenseurl:*licenses/by/*",
    "cc-by-sa": "licenseurl:*licenses/by-sa/*",
    "cc-by-nc": "licenseurl:*licenses/by-nc*",
}


def build_query(query: str, filters: dict[str, str]) -> str:
    """Combine the free-text query with provider-agnostic filters.

    Always ANDs in `mediatype:(audio)` since this tool only ever wants
    sound-bearing items, and excludes `access-restricted-item:true` —
    those are lending/streaming-only items whose files 401 on direct
    download, so a batch downloader has no use for them in results.
    Supported filter keys: license (repeatable, OR-joined), tag (mapped
    to IA's `subject` field, repeatable, OR-joined), plus any raw Lucene
    passed through as 'raw'.
    """
    clauses = [f"({query})"] if query else []
    clauses.append("mediatype:(audio)")
    clauses.append("NOT access-restricted-item:true")

    licenses = _as_list(filters.get("license"))
    if licenses and "any" not in licenses:
        terms = [LICENSE_PATTERNS[code] for code in licenses if code in LICENSE_PATTERNS]
        if terms:
            clauses.append("(" + " OR ".join(terms) + ")")

    tags = _as_list(filters.get("tag"))
    if tags:
        quoted = " OR ".join(f'"{t}"' for t in tags)
        clauses.append(f"subject:({quoted})")

    raw = filters.get("raw")
    if raw:
        clauses.append(raw)

    return " AND ".join(clauses)


def _as_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
