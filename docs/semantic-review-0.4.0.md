# Soundfetch 0.4.0 semantic review guide

This is the required human review entry point for the first public beta. It
does not record approval. Because no prior version was tagged or published,
use `c0f6453` (the parent-side 0.3.0 state before the 0.4.0 version bump) as the
review baseline and the final candidate commit as the comparison endpoint.

## Review commands

```bash
git log --oneline c0f6453..<candidate>
git diff --stat c0f6453..<candidate>
git diff c0f6453..<candidate> -- pyproject.toml src/soundfetch/__init__.py
git diff c0f6453..<candidate> -- src/soundfetch/api.py src/soundfetch/cli.py
git diff c0f6453..<candidate> -- src/soundfetch/core src/soundfetch/providers
git diff c0f6453..<candidate> -- src/soundfetch/mcp.py src/soundfetch/export.py
git diff c0f6453..<candidate> -- .github/workflows docs README.md
```

## Semantic review checklist

- **Public API and CLI:** selected downloads preserve input order; JSON output
  keeps provider identity, status, checksum, and error attribution aligned.
- **Manifest:** append-only, last-record-wins behavior and existing record
  compatibility remain intact; provider-specific fields remain in metadata.
- **Providers and downloader:** lazy optional dependencies, bounded pacing and
  concurrency, partial-file resume, checksum validation, atomic replacement,
  and per-item failure checkpointing remain shared invariants.
- **Security boundaries:** redirects and private/internal URLs are rejected as
  intended; filenames and write paths stay confined; MCP paths remain beneath
  `SOUNDFETCH_MCP_ROOT`; remote text remains untrusted and bounded.
- **Packaging:** version and extras are intentional, base imports require no
  optional dependency, and Linux/Python 3.10–3.13 is the complete supported
  beta claim.
- **Release process:** final evidence refers to one immutable candidate and
  exact artifacts; tagging and manual PyPI upload remain explicitly gated.

Record approval, rejected claims, and required corrections outside this file
or in the pull-request review. Approval must identify the exact candidate SHA.
