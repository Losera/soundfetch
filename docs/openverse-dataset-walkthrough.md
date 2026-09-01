# Build a small governed audio dataset

This walkthrough uses Openverse's anonymous API to collect a bounded CC0 sound
effects dataset, review its provenance, download with checkpoints, and export
attribution and WebDataset shards. Openverse indexes third-party hosts, so
catalog results and file availability can change between runs.

## 1. Install the candidate

Until 0.4.0 is published, run this from a Soundfetch checkout:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[export]"
```

After publication, the equivalent clean installation will be:

```bash
pip install "soundfetch[export]==0.4.0"
```

## 2. Discover and review

Keep the query bounded and request short MP3 sound effects to make this a
small demonstration rather than an unbounded collection job:

```bash
soundfetch openverse search bird \
  --license cc0 \
  --extension mp3 \
  --max-results 5 \
  -o out/bird-cc0

soundfetch manifest report out/bird-cc0/manifest.jsonl

jq -r '
  select(.status == "listed") |
  [.provider_id, .name, .url, .metadata.license] | @tsv
' out/bird-cc0/manifest.jsonl
```

Open every selected landing page and confirm that its identity and license
match the manifest. Soundfetch preserves provider metadata; it does not certify
that an upstream license assertion is correct.

## 3. Download and verify

```bash
soundfetch openverse download \
  --manifest out/bird-cc0/manifest.jsonl \
  --workers 2 \
  -o out/bird-cc0

soundfetch manifest report out/bird-cc0/manifest.jsonl --json \
  > out/bird-cc0/report.json
```

The second report uses each sound's latest manifest record. Review failed
downloads, missing files or checksums, and provenance gaps before exporting.
Re-running the download command resumes completed records by default.

## 4. Export a training-friendly artifact

```bash
python - <<'PY'
from soundfetch.export import export_attribution, to_webdataset

manifest = "out/bird-cc0/manifest.jsonl"
export_attribution(manifest)
to_webdataset(manifest, out_dir="out/bird-cc0/shards", shard_size=5)
PY

sha256sum \
  out/bird-cc0/manifest.jsonl \
  out/bird-cc0/ATTRIBUTION.md \
  out/bird-cc0/shards/*
```

Keep the manifest, report, attribution file, exact Soundfetch version, and
artifact hashes with downstream experiment records. Do not commit downloaded
audio to the Soundfetch repository.

## Evidence boundary

The commands above define the release demonstration. Exact observed counts,
artifact hashes, candidate commit, and live-provider results must be recorded
only after the final candidate has passed semantic review and release
verification. Until then, this page is a reproducible procedure rather than a
claim about a particular dataset run.
