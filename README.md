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

### Internet Archive

No API key or auth needed — Internet Archive serves original-quality files to
anyone. Access-restricted (lending/streaming-only) items are excluded
automatically since they can't be downloaded directly.

```bash
soundfetch archive search "field recording rain" --license cc0 -o out/
soundfetch archive download --manifest out/manifest.jsonl -o out/
# or search-then-download in one step:
soundfetch archive download "rain storm" --license cc0 -o out/
```

`--tag` matches Internet Archive's `subject` field. `--license` uses the same
short codes as Freesound, mapped to the closest `licenseurl` patterns IA
items actually use.

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
`SoundRef`, `SearchParams`, `DownloadResult`, `Provider`, and `provider_names`.

## Development

```bash
pip install -e ".[dev]"
pytest -m "not live"          # offline suite (no API key needed)
pytest -m live                # live smoke test (requires FREESOUND_API_KEY)
```

## Roadmap

- **Phase 1** (done): working Freesound CLI — search, preview downloads, manifest.
- **Phase 2** (done): OAuth2 originals, full pagination, license/gen-ai filters, resume.
- **Phase 3** (in progress): provider platform — Internet Archive (done, above),
  video sources (not started), one manifest schema across providers (done).
- **Later**: web UI over the manifest.
