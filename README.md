# soundfetch

Batch sound/data collection from the internet. A CLI that queries sound databases,
downloads audio (previews or lossless originals), and writes a machine-readable
manifest of every sound it finds — built to grow into a platform with many sources.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Configure

Copy `.env.example` to `.env` and add your Freesound API key
(apply at https://freesound.org/apiv2/apply/):

```bash
cp .env.example .env
```

`soundfetch` reads `.env` from the current directory (via `python-dotenv`) and also
accepts real environment variables. Precedence: CLI flag > env var > `.env`.

## Usage

```bash
# Search Freesound and write the manifest (no downloads)
soundfetch freesound search "piano" --license cc0 -o out/

# Download high-quality mp3 previews for a query
soundfetch freesound download "piano" --mode preview -o out/

# Two-phase workflow: search once, review the manifest, then download from it
soundfetch freesound search "field recording rain" --license cc-by -o out/
soundfetch freesound download --manifest out/manifest.jsonl -o out/

# Check what's configured
soundfetch freesound status
soundfetch sources
```

Download parallelism & rate control:

```bash
# Download 4 files in parallel (token-bucket paced per provider)
soundfetch freesound download "piano" -o out/ --workers 4

# Cap at 2 requests/sec with the token-bucket Pacing (overrides --rate-delay)
soundfetch archive download --manifest out/manifest.jsonl -o out/ --rate 2
```

`--workers N` downloads with N threads through a bounded pool (results still
report in input order). `--rate R` throttles the run to at most R requests/sec
via a shared token bucket that also paces search; the legacy `--rate-delay`
(seconds between requests) remains the default and is overridden when `--rate`
is given.

### Internet Archive

No API key or auth needed — Internet Archive serves original-quality files to
anyone. Access-restricted (lending/streaming-only) items are excluded
automatically since they can't be downloaded directly.

```bash
soundfetch archive search "field recording rain" --license cc0 -o out/
soundfetch archive download --manifest out/manifest.jsonl -o out/

# Machine clients can download an exact reviewed result and receive a stable JSON result.
soundfetch archive download --manifest out/manifest.jsonl \
  --provider-id archive-item-123 --json -o out/
# or search-then-download in one step:
soundfetch archive download "rain storm" --license cc0 -o out/
```

`--tag` matches Internet Archive's `subject` field. `--license` uses the same
short codes as Freesound, mapped to the closest `licenseurl` patterns IA
items actually use. Archive searches fetch metadata for each result; concise
`archive metadata: N/T` progress is written to stderr, including when `--json`
keeps stdout machine-readable.

Archive search covers IA's entire audio-mediatype catalog, not a curated
sound-effects library — a bare keyword like `rain` can rank a music track
whose *title* contains the word above an actual field recording, since that's
a genuine relevance match, not a bug. Prefer descriptive queries (as above)
or `--tag` to narrow results.

### Original (lossless) downloads

Freesound serves low-quality previews (mp3/ogg, ~64–192 kbps) to a plain API key.
Original WAV/FLAC/AIFF files require OAuth2:

```bash
# One-time: create a Freesound app, then run the browser auth flow
soundfetch freesound auth

# Now you can download originals
soundfetch freesound download "piano" --mode original -o out/
```

Tokens are cached at `$SOUNDFETCH_CONFIG_DIR/freesound.json` (default
`~/.config/soundfetch/`, mode 0600) and auto-refresh when they expire.

## License-aware collection

For ML/data work, license compliance is load-bearing. `--license` accepts repeatable
codes (`cc0`, `cc-by`, `cc-by-sa`, `cc-by-nc`, `any`). `--gen-ai` filters by
Freesound's `gen_ai_preference` field (`allow`, `deny`, `unspecified`, `any`).
Every sound's license and `gen_ai_preference` are recorded in the manifest.

## The manifest

Every command writes `<outdir>/manifest.jsonl` — one JSON object per line, append-only,
last-wins per `(provider, provider_id)`. It serves as search output, download
checkpoint, resume log, and dataset index. Each record includes the provider id,
metadata (license, tags, duration, samplerate, format, ...), and download status.

`--provider-id` is repeatable and requires `--manifest`; only matching records are
downloaded, in manifest order. With `--json`, downloads emit one object containing
`ok`, `provider`, `manifest`, and an `items` array with each selected result's
`provider_id`, `status`, `local_path`, byte count, checksum, and error. This is the
supported integration contract for Incant-Audio and other native clients.

Consume it with pandas: `pd.read_json("out/manifest.jsonl", lines=True)`.

## Python API

`soundfetch` is also a library — the CLI is a thin wrapper over the same
functions. Everything provider-agnostic; pass `provider=` to pick a source
(`freesound`, `archive`, `video`), or inject a configured provider instance
for explicit API-key/options control.

```python
import soundfetch

# Search a source (pure: returns SoundRefs, writes nothing)
refs = soundfetch.search(
    "piano",
    provider="freesound",
    license="cc0",
    max_results=100,
)
soundfetch.save_search(refs, "out/manifest.jsonl")

# Two-phase: review the manifest, then download from it (resumes by default)
refs = soundfetch.refs_from_manifest("out/manifest.jsonl")
results = soundfetch.download(refs, dest_dir="out/")

# Mixed-provider manifests just work — download() groups refs by source
```

Explicit provider instances (e.g. an API key passed directly, or a custom
provider):

```python
from soundfetch.providers.freesound.provider import FreesoundProvider

prov = FreesoundProvider(api_key="...")  # or let env vars resolve
refs = soundfetch.search(
    "piano",
    providers={"freesound": prov},  # injected instance wins over provider=
)
```

Manifest reads for the dataset-index use case:

```python
import soundfetch

for record in soundfetch.iter_latest("out/manifest.jsonl"):
    print(record["provider_id"], record["metadata"])
```

Top-level exports: `search`, `download`, `save_search`, `refs_from_manifest`,
`read_records`, `iter_latest`, `latest_by_sound`, `ref_record`, plus the types
`SoundRef`, `SearchParams`, `DownloadResult`, `Provider`, `ProgressCallback`,
and `provider_names`. Library callers can pass `provider_progress=` to
`search()` for provider-specific `(completed, total)` updates.

## Agents & MCP

`soundfetch` speaks MCP. Four tools are exposed: `search_sounds`,
`download_manifest`, `check_provider_status`, `list_sources`.

```bash
pip install "soundfetch[mcp]"
soundfetch mcp   # MCP server over stdio
```

Register it in Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "soundfetch": { "command": "soundfetch", "args": ["mcp"] }
  }
}
```

## Data exports

Turn a completed manifest into WebDataset shards or a compliance-ready
attribution file:

```python
pip install "soundfetch[export]"
from soundfetch.export import to_webdataset, export_attribution

to_webdataset("out/manifest.jsonl", out_dir="out/shard.tar")  # tar shards
export_attribution("out/manifest.jsonl", dest_dir="out/")     # ATTRIBUTION.md
```

Heavy dependencies (`webdataset`, `soundfile`) are imported lazily inside
`to_webdataset`, so `import soundfetch.export` is cheap. A HuggingFace
`datasets` exporter was attempted and deliberately left out — see
[`docs/deferred-work.md`](docs/deferred-work.md).

## Live benchmarks

The benchmark scripts run small real-network collections against Freesound and
Internet Archive; add `--video` to include the video provider when `yt-dlp` is
installed. Freesound requires `FREESOUND_API_KEY`.

```bash
# Black-box CLI benchmark and ASCII timing table
python scripts/benchmark_cli.py --limit 3 --query rain

# In-process API benchmark, CSV/JSON metrics, and four matplotlib charts
pip install -e ".[bench]"
python scripts/benchmark_api.py --limit 3 --query rain
```

Each run uses a fresh timestamped directory under `benchmarks/`. The API script
accepts repeated `--trials`, comma-separated `--workers`, and hard
`--max-file-mb` / `--max-total-mb` safety caps. It writes raw metrics,
summaries, environment and Git metadata, a failure list, and comparison charts.
Named `benchmarks/review-*` snapshots may retain those evidence files; downloaded
audio and manifests remain ignored. Both scripts exit nonzero if a source fails.

## Development

```bash
pip install -e ".[dev]"
pytest -m "not live"          # offline suite (no API key needed)
pytest -m live                # live smoke test (requires FREESOUND_API_KEY)
```

Release preparation, wheel-only smoke checks, publishing gates, and recovery
steps are documented in [`docs/RELEASE.md`](docs/RELEASE.md).

## Roadmap

- **Phase 1** (done): working Freesound CLI — search, preview downloads, manifest.
- **Phase 2** (done): OAuth2 originals, full pagination, license/gen-ai filters, resume.
- **Phase 3** (in progress): provider platform — Internet Archive and the
  optional `yt-dlp`-backed video provider are available, with one shared
  manifest schema across providers.
- **Later**: web UI over the manifest.
