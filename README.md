# soundfetch

Soundfetch searches public sound sources, downloads audio, and records every
result in an append-only JSONL manifest. It supports Internet Archive,
Freesound, and an optional `yt-dlp`-backed video provider through one CLI and
Python API.

## Status and installation

Soundfetch 0.4.0 is a beta candidate under active review. It has not been
tagged or published to a package index yet, so install it from a source
checkout:

```bash
git clone https://github.com/Losera/soundfetch.git
cd soundfetch
python -m venv .venv
. .venv/bin/activate
pip install -e .
soundfetch --version
```

Optional features are installed as extras:

```bash
pip install -e ".[video]"  # yt-dlp video provider
pip install -e ".[mcp]"    # MCP server
pip install -e ".[export]" # WebDataset and audio export dependencies
```

Python 3.10 or newer is required.

## Five-minute quick start: Internet Archive

Internet Archive requires no API key. Search for a descriptive sound, review
the resulting manifest, and then download its listed files:

```bash
soundfetch archive search "field recording rain" \
  --license cc0 --max-results 5 -o out/

# Review out/manifest.jsonl before downloading.
soundfetch archive download --manifest out/manifest.jsonl -o out/
```

Search and download commands maintain `manifest.jsonl` in the output directory.
Status, source-listing, authentication, and MCP commands do not write a
manifest.

Internet Archive serves original-quality files without authentication.
Access-restricted lending or streaming-only items are excluded because they
cannot be downloaded directly. Searches resolve file metadata for each result,
so even a small page may take several seconds; concise
`archive metadata: completed/total` progress is written to stderr.

Internet Archive covers its complete audio catalog rather than a curated
sound-effects library. A broad query such as `rain` may rank music with “rain”
in its title above a field recording. Prefer descriptive queries or narrow the
search with repeatable `--tag` and `--license` options.

## Freesound configuration and original downloads

Freesound search and preview downloads require an API key. Apply for one at
<https://freesound.org/apiv2/apply/>, then either export it or place it in a
`.env` file in the directory where Soundfetch runs:

```bash
export FREESOUND_API_KEY="your-api-key"

# Or, from the repository checkout:
cp .env.example .env
```

Soundfetch reads real environment variables and a `.env` file in its current
directory. Explicit CLI options take precedence over environment variables,
which take precedence over `.env` values.

Search or download high-quality MP3 previews:

```bash
soundfetch freesound search "piano" --license cc0 -o out/
soundfetch freesound download "piano" --mode preview -o out/
```

Original WAV, FLAC, and AIFF files require Freesound OAuth2 credentials in
addition to the API key:

```bash
export FREESOUND_CLIENT_ID="your-client-id"
export FREESOUND_CLIENT_SECRET="your-client-secret"
soundfetch freesound auth
soundfetch freesound download "piano" --mode original -o out/
```

OAuth tokens are cached at `$SOUNDFETCH_CONFIG_DIR/freesound.json` (by default
`~/.config/soundfetch/freesound.json`) with mode `0600` and are refreshed when
they expire. Run `soundfetch freesound status` to inspect configuration.

For license-aware collection, `--license` accepts repeatable `cc0`, `cc-by`,
`cc-by-sa`, `cc-by-nc`, or `any` values. Freesound's `--gen-ai` filter accepts
`allow`, `deny`, `unspecified`, or `any`. License and
`gen_ai_preference` metadata are retained in the manifest.

## Review-first manifest workflow

The recommended workflow separates discovery from downloading:

```bash
# 1. Search without downloading.
soundfetch freesound search "field recording rain" \
  --license cc-by --max-results 20 -o out/

# 2. Review or programmatically filter out/manifest.jsonl.

# 3. Download the reviewed manifest. Completed records resume by default.
soundfetch freesound download --manifest out/manifest.jsonl -o out/
```

The manifest contains one JSON object per line and is:

- append-only;
- last-record-wins per `(provider, provider_id)`;
- a search result, download checkpoint, resume log, and dataset index;
- provider-independent at the record level, with provider-specific fields
  retained under `metadata`.

Each record includes its provider and provider ID, source and download URLs,
license and descriptive metadata, download status, local file path, and
checksum when available. It can be read directly with pandas:

```python
import pandas as pd

records = pd.read_json("out/manifest.jsonl", lines=True)
```

Downloads use a bounded worker pool. Results remain in input order even when
downloads run concurrently:

```bash
soundfetch freesound download --manifest out/manifest.jsonl \
  --workers 4 --rate 2 -o out/
```

`--rate 2` applies a shared token-bucket limit of two requests per second and
overrides `--rate-delay`. Run a provider command with `--help` for its complete
filter and download options.

The optional video provider accepts a video, playlist, or channel URL, or a
search query:

```bash
pip install -e ".[video]"
soundfetch video search "creative commons ocean waves" --max-results 5 -o out/
soundfetch video download "https://www.youtube.com/watch?v=VIDEO_ID" -o out/
```

Video license filtering is best-effort because upstream license metadata is
free text. Review every result before using it in a dataset.

## Incant-Audio and machine-readable contracts

Incant-Audio and other native clients should select reviewed records by
provider ID and request JSON output:

```bash
soundfetch archive download --manifest out/manifest.jsonl \
  --provider-id archive-item-123 --json -o out/
```

`--provider-id` is repeatable, requires `--manifest`, and selects records in
manifest order. A successful download writes one JSON object to stdout with
this shape:

```json
{
  "ok": true,
  "command": "download",
  "provider": "archive",
  "manifest": "out/manifest.jsonl",
  "items": [
    {
      "provider": "archive",
      "provider_id": "archive-item-123",
      "status": "downloaded",
      "local_path": "out/example.wav",
      "bytes": 123456,
      "checksum": "0123456789abcdef...",
      "error": null
    }
  ]
}
```

Errors use `{"ok": false, "error": {"type": "...", "message": "..."}}`
and a nonzero process exit. Human progress is kept on stderr so JSON on stdout
remains machine-readable. The manifest and download JSON are compatibility
boundaries; native clients should tolerate additional object fields.

## Python API

The CLI delegates to the provider-independent Python API:

```python
import soundfetch

# Search is pure: it returns SoundRef values and writes nothing.
refs = soundfetch.search(
    "piano",
    provider="freesound",
    license="cc0",
    max_results=100,
)
soundfetch.save_search(refs, "out/manifest.jsonl")

# Reconstruct pending refs and download them, resuming by default.
pending = soundfetch.refs_from_manifest("out/manifest.jsonl")
results = soundfetch.download(pending, dest_dir="out/")
```

Mixed-provider input is supported. `download()` dispatches each reference to
its provider while preserving the original result order.

Inject an explicitly configured or custom provider when environment-based
configuration is undesirable:

```python
from soundfetch import search
from soundfetch.providers.freesound.provider import FreesoundProvider

provider = FreesoundProvider(api_key="...")
refs = search(
    "piano",
    provider="freesound",
    providers={"freesound": provider},
)
```

Read the latest record for each sound without loading the entire manifest:

```python
import soundfetch

for record in soundfetch.iter_latest("out/manifest.jsonl"):
    print(record["provider_id"], record["metadata"])
```

Top-level exports include `search`, `download`, `save_search`,
`refs_from_manifest`, `read_records`, `iter_latest`, `latest_by_sound`,
`ref_record`, `SoundRef`, `SearchParams`, `DownloadResult`, `Provider`, and
`provider_names`. `ProgressCallback` is available from `soundfetch.api`.
Library callers can pass `provider_progress=` to `search()` for
provider-specific `(completed, total)` updates.

## MCP server

The optional MCP server exposes four tools over stdio:

- `search_sounds`
- `download_manifest`
- `check_provider_status`
- `list_sources`

Install the extra and locate the executable:

```bash
pip install -e ".[mcp]"
command -v soundfetch
```

Register the absolute executable path in Claude Desktop and set an explicit
workspace root:

```json
{
  "mcpServers": {
    "soundfetch": {
      "command": "/absolute/path/to/venv/bin/soundfetch",
      "args": ["mcp"],
      "env": {
        "SOUNDFETCH_MCP_ROOT": "/absolute/path/to/sound-workspace"
      }
    }
  }
}
```

Model-supplied manifest and destination paths are confined to
`SOUNDFETCH_MCP_ROOT`. If it is unset, the server uses its process working
directory. Use a dedicated workspace and pass paths relative to that root.
Provider titles, descriptions, and tags are remote, untrusted content; MCP
responses bound their length but do not make them trustworthy.

## Data exports

Install the export dependencies:

```bash
pip install -e ".[export]"
```

Create WebDataset shards or a compliance-oriented attribution file from a
completed manifest:

```python
from soundfetch.export import export_attribution, to_webdataset

shards = to_webdataset(
    "out/manifest.jsonl",
    dest_dir="out/",
    out_dir="out/shards/",
)
attribution = export_attribution(
    "out/manifest.jsonl",
    dest_dir="out/",
)
```

`to_webdataset()` imports WebDataset lazily and writes numbered `.tar.gz`
shards by default. The export extra also includes SoundFile for real-audio
integration validation. A Hugging Face `datasets` exporter was deliberately
deferred; see [`docs/deferred-work.md`](docs/deferred-work.md).

## Future provider candidates

This is an investigation backlog, not a compatibility promise. A provider
should be added only when it serves a demonstrated user workflow, exposes a
maintainable programmatic interface, permits the intended downloads, and can
map provenance and licensing into the existing manifest without weakening its
guarantees.

| Candidate | What it would add | Main integration question |
|---|---|---|
| [Openverse](https://api.openverse.org/) | A broad, normalized search over openly licensed audio, including a `sound_effect` category and anonymous API access | How should Soundfetch preserve the original source identity and deduplicate results already available through Freesound or Internet Archive? |
| [Wikimedia Commons](https://www.mediawiki.org/wiki/API:Imageinfo) | Historical recordings, pronunciations, speeches, music, and community-contributed audio with rich attribution metadata | Can file search, `imageinfo`, and Commons extension metadata be normalized reliably enough to enforce per-file rights and attribution? |
| [Library of Congress](https://www.loc.gov/apis/json-and-yaml/) | Publicly searchable historical and cultural audio collections without an API key | Rights and downloadable-media availability vary by item, so discovery must not imply permission or a usable audio file. |
| [xeno-canto](https://xeno-canto.org/explore/api) | A focused wildlife and bioacoustics source that would serve field-recording and audio-ML users | Confirm current API access, reuse terms, attribution requirements, and acceptable automated-download behavior before design work. |
| [Jamendo](https://developer.jamendo.com/v3.0/tracks) | Searchable Creative Commons music with musical metadata and stream/download URLs | The provider must honor `audiodownload_allowed`, distinguish streaming from downloading, and represent licenses Soundfetch does not currently accept. |
| [Zenodo](https://developers.zenodo.org/) | Versioned research deposits, DOIs, checksums, and downloadable audio datasets | Zenodo records often contain archives or heterogeneous files rather than individual sounds; decide whether this belongs in the provider model or a dataset-ingestion layer. |
| [Hugging Face Hub](https://huggingface.co/docs/hub/datasets-audio) | Versioned community audio datasets, including audio files, Parquet, and WebDataset layouts | Repository snapshots and dataset rows do not naturally map one-to-one to `SoundRef`; integration may fit an import/export adapter better than a search provider. |

Openverse is the strongest next general-purpose candidate because its audio
search and license metadata closely resemble Soundfetch's existing model.
xeno-canto is the strongest specialized candidate because it adds a distinct
bioacoustics corpus rather than another broad media catalog. Zenodo and the
Hugging Face Hub should remain discovery work until Soundfetch decides whether
dataset-level sources belong behind the current per-sound provider interface.

## Development and release status

Create a worktree-local environment and run the offline suite:

```bash
scripts/bootstrap-worktree.sh
.venv/bin/python -m pytest -m "not live"
```

Live provider tests are deliberate and may require credentials or optional
tools:

```bash
.venv/bin/python -m pytest -m live
```

Small real-network benchmarks are available for Freesound and Internet
Archive. They use fresh timestamped output directories and support hard file
and total-size caps:

```bash
.venv/bin/python scripts/benchmark_cli.py --limit 3 --query rain
.venv/bin/python scripts/benchmark_api.py \
  --limit 3 --query rain --max-file-mb 1 --max-total-mb 10
```

Release preparation, wheel-only smoke tests, publishing gates, and recovery
steps are documented in [`docs/RELEASE.md`](docs/RELEASE.md). The current beta
evidence and remaining human gates are recorded in
[`docs/beta-readiness-0.4.0.md`](docs/beta-readiness-0.4.0.md).
