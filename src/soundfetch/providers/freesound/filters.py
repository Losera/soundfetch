"""Translate provider-agnostic filters into Freesound Solr filter syntax.

The short codes map to the exact strings Freesound returns in the `license`
field. If a live search result ever shows a different string, fix it here —
this table is the single source of truth.
"""

from __future__ import annotations

# Short code -> the value Freesound returns in the `license` field.
LICENSES: dict[str, str] = {
    "cc0": "Creative Commons 0",
    "cc-by": "Attribution",
    "cc-by-sa": "Attribution ShareAlike",
    "cc-by-nc": "Attribution Noncommercial",
}

GEN_AI_VALUES = ("allow", "deny", "unspecified")


def build_filter(filters: dict[str, str]) -> str:
    """Combine provider-agnostic filters into a Freesound `filter` string.

    Supported keys: license (repeatable, OR-joined), duration (raw Solr range),
    tag (repeatable, OR-joined), gen_ai (single value), plus any raw Solr
    passed through as 'raw'.
    """
    clauses: list[str] = []

    licenses = _as_list(filters.get("license"))
    if licenses and "any" not in licenses:
        terms = [f'"{LICENSES[code]}"' for code in licenses if code in LICENSES]
        if terms:
            clauses.append(f"license:({' OR '.join(terms)})")

    duration = filters.get("duration")
    if duration:
        clauses.append(f"duration:{duration}")

    tags = _as_list(filters.get("tag"))
    if tags:
        quoted = " OR ".join(f'"{t}"' for t in tags)
        clauses.append(f"tag:({quoted})" if len(tags) > 1 else f'tag:"{tags[0]}"')

    gen_ai = filters.get("gen_ai")
    if gen_ai and gen_ai != "any":
        if gen_ai in GEN_AI_VALUES:
            clauses.append(f'gen_ai_preference:"{gen_ai}"')
        else:
            raise ValueError(
                f"invalid --gen-ai value {gen_ai!r}; "
                f"expected one of {', '.join(GEN_AI_VALUES)} or 'any'"
            )

    raw = filters.get("raw")
    if raw:
        clauses.append(raw)

    return " AND ".join(clauses)


def _as_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
