Plan: Rebuild Freesound-Batch-Downloader as soundfetch — a multi-source sound collection CLI

Context

The repo /home/losera/Freesound-Batch-Downloader holds a single ~70-line script (freesound_download.py) that does not work as written. Verified against the official Freesound API v and the freesound-pythonsource:

1. Hardcoded sys.path to /Users/jnaran/Desktop/... — breaks on any other machine
(the vendored-path bug c
2. retrieve_preview is called with a file path where the library expects a
directory — signature isname, quality, file_format). Passing folder/name.wav makes the real target folder/name.wav/<uuid>.mp3,
requiring name.wav to beror. The script cannotdownload anything as written.
3. Wrong extension: namereviews are only mp3(64–128kbps) or ogg (80–192kbps). Never wav.
4. Original lossless filound resource isOAuth2-only). The token-only script can never get WAV/FLAC/AIFF originals — only
low-quality previews.
5. No pagination: iterates only the first page of the Pager; the page_size arg is
mislabeled "amount of pa
6. No requirements.txt/packaging, no license or gen_ai_preference filtering
(critical for ML-traininure, no 429 handling, noretry/resume/checkpointing, no filename-collision handling, and
print("Authentication sually even when the key isinvalid.

Goal: replace it with a well-packaged, working CLI — soundfetch — architected as
a platform for extractinrnet. First-class sourcesper user's answers: Freesound (OAuth2 originals + preview fallback), Internet
Archive, YouTube/video, s (Zapsplat/BBC class).Primary users are ML/data researchers — so license compliance filtering, full
metadata export, and los CLI first; a web UI is alater phase, so the CLI must emit machine-readable artifacts (a JSONL manifest) a
UI can consume.

---
Design decisions

#: D1
Decision: Drop the freessound API v2 JSON endpoints
directly with requests
Why: SDK's retrieve/retrs directly (no .part, noresume,
no checksum), its Pager  bug, and it can't expose
Retry-After. Direct URLs are what the multi-source abstraction needs anyway
(previews are plain CDN d GET). Removes the
vendored-path bug class entirely.
────────────────────────
#: D2
Decision: One provider P a lazy string→classregistry.
Core owns naming/collisiable stream_to_file()
Why: A second source is one new module + one registry line. No abstract-factory
pyramid.
────────────────────────────────────────
#: D3
Decision: Single append-only manifest.jsonl in the output dir; effective record
per
sound = last line per (provider, provider_id)
Why: One artifact servesheckpoint, resume log, and
dataset input for the future web UI. O(1) appends, no rewriting.
────────────────────────
#: D4
Decision: click for the
Why: Nested subcommands (soundfetch freesound search|download|auth), typed
options,
progress bars. argparse would be ~2× boilerplate.
────────────────────────
#: D5
Decision: Deps kept to c (+ dev: pytest,requests-mock)
Why: No DB, no ORM, no a
────────────────────────────────────────
#: D6
Decision: Preview mode = CDN URLs (no auth); original mode = GET
/apiv2/sounds/<id>/downler (OAuth2)
Why: Matches verified API. Both funnel through the same core streaming downloader
—
that's what makes the "platform" real.

---
Repository layout (new)

Old freesound_download.p/home/losera/Freesound-Batch-Downloader/:

pyproject.toml              # packaging + `soundfetch`/`freesound-fetch` console
scripts
README.md                   # usage, env vars, manifest schema pointer
.env.example            SOUND_CLIENT_ID/SECRET
.gitignore                  # add: out/, .env, credentials.json, *.part
src/soundfetch/
  __init__.py               # __version__
  cli.py                subcommand wiring
  core/
    model.py            e, SoundRef, DownloadResult(dataclasses)
    provider.py         ISTRY + get_provider()
    engine.py               # search loop, download loop, checkpoint/resume
    manifest.py         e helpers
    names.py                # filename sanitize + unique_path collision logic
    downloader.py       , Range resume, rename
    net.py                  # retry with Retry-After/backoff, HTTPError parsing
  providers/
    __init__.py             # registers provider names → import paths
    freesound/
      provider.py           # FreesoundProvider: search + download
      filters.py         → Solr filter string
      auth.py               # OAuth2 code flow, token cache, refresh
    archive/            ve)
    video/                  # Phase 3 (yt-dlp-based YouTube)
tests/
  conftest.py  fakes.py  fixtures/freesound/
  unit/{test_names,test_wnloader,test_freesound_provider,test_engine}.py
  live/test_smoke.py    ND_API_KEY

Provider abstraction (co platform seam

class Provider(Protocol)
    name: str
    def search(self, pars=None) -> SearchPage: ...
    def download(self, ref: SoundRef, dest_dir: Path) -> DownloadResult: ...

REGISTRY = {"freesound":
"soundfetch.providers.frvider"}

search() returns pages;  engine.py so providersnever duplicate pagination. download() is the only other method; core supplies
stream_to_file(url, destand providers call it(Freesound original passes Authorization: Bearer; Internet Archive passes none).
The registry is lazy-impre never pulls providercode. Graduating to package entry-point groups is explicitly deferred.

---
CLI surface

soundfetch [--config-dir
├── freesound
│   ├── search QUERY  -o,cc-by-sa,cc-by-nc,any}…]
│   │                  [--duration "[1 TO 30]"] [--tag TAG]…
│   │                  [ied,any}] [--raw-filterSOLR]
│   │                  [-max-results N]
│   │                  [--with-descriptors bpm,pitch,spectral_centroid]   # mfcc
always opt-in
│   ├── download QUERY | --manifest FILE  -o OUTDIR
│   │                  [-quality {hq,lq}] [--format{mp3,ogg}]
│   │                  [no-resume] [--overwrite]
│   │                  [--rate-delay 0.5] [--fail-fast|--continue-on-error]
│   ├── auth [--client-iedirect-urihttp://localhost:8765/callback]
│   └── status
└── sources                    # list registered providers

Global: env vars FREESOUND_API_KEY, FREESOUND_CLIENT_ID, FREESOUND_CLIENT_SECRET,
SOUNDFETCH_CONFIG_DIR; . precedence CLI > env >config. No unconditional "Authentication successful!" — nothing authenticates at
startup; status is the e

---
Freesound provider specifics

- Search: GET /apiv2/search/ with query, filter, sort, fields, page, page_size
(≤150). Loop next until  list:id,name,url,description,tags,username,license,gen_ai_preference,duration,samplera
te,channels,type,filesizimages (+ descriptors whenrequested). Fixes the one-page bug.
- Filters (filters.py): icense:("Creative Commons0"), cc-by→license:("Attribution"), repeatable tags OR-joined, duration:[1 TO
30], gen_ai_preference:"gs confirmed against a livefixture during implementation (isolated in one table).
- gen_ai_preference: opa always recorded in manifest (ML-training legality), never silently dropped.
- Download: previews fro-mp3|hq-ogg|lq-ogg} with noauth; originals resolve detail GET /sounds/<id>/, then GET /sounds/<id>/download/
with Bearer token; filenelse sanitized name + typeextension; verify md5 for originals. Missing token for original → clear "run
soundfetch freesound aut
- Names: sanitize to [A-Za-z0-9._-], collapse whitespace, cap ~120 chars,
fallback sound-<id>;  (1
- Net: retry(fn, attempts=5, retry_on={429,500,502,503,504}) honoring Retry-After
else exp backoff + jitteate-delay floor.
- Resume: the manifest is the checkpoint. Skip status:"downloaded" entries whose
local_file exists unless

---
Metadata export (the web-UI seam)

Single artifact <outdir>/manifest.jsonl, one JSON object per line, append-only,
last-wins per (provider,

{"provider":"freesound",snare.wav","url":"https://freesound.org/s/1234/",
 "file_format":"wav","ch":"https://…/download/",
 "metadata":{"license":"Creative Commons
0","tags":["snare"],"use
             "samplerate":44100,"type":"wav","gen_ai_preference":"allow","preview
s":{…},"images":{…}},
 "status":"downloaded","local_file":"snare.wav","downloaded_at":"…","error":null}

JSONL over CSV/sidecar: nested fields don't flatten to CSV; append-safe for
checkpointing; consumed  lines=True) + dedupe byprovider_id), jq, and a future web UI serving local_file from the outdir.
docs/MANIFEST.md + JSON

---
Testing

- Offline (CI-safe, no API key): recorded fixtures served via requests_mock →
pagination loop, has_moration, page_size cap, refconversion. test_downloader: .part + atomic rename, Range-resume, md5 mismatch.
test_engine with FakePro_results, manifest dedupe,resume-skip, continue-on-error. Pure units for names/manifest; 429-retry with
Retry-After asserted.
- Live smoke: tests/live/test_smoke.py, skipped without FREESOUND_API_KEY;
page_size=1 search assernloads one hq preview.
- CI: pytest -m "not live" every push; scheduled job with the key runs live.

---
Phased rollout (each pha

Phase 1 — Working Freesosrc/soundfetch/{cli,core/*,providers/freesound/*},
README/.env.example/.gitreview-only downloads,correct extensions (mp3 not wav), directory args are directories, no fake auth
print, env-var key. Accendfetch freesound search"piano" -o out/ writes manifest; soundfetch freesound download "piano" -o out/
downloads hq mp3 previewy local_file exists, emptyresult doesn't crash.

Phase 2 — Metadata, licensing, pagination, originals. core/engine.py (full
paging, checkpoint/resumth.py (OAuth2: authorize URL → localhost callback → token exchange → cached credentials.json at
$SOUNDFETCH_CONFIG_DIR, ode original with md5verify, --manifest two-phase workflow, collision suffixes, --resume/--overwrite,
descriptors. Acceptance:; originals require OAuth2and produce lossless files; search→download pipeline idempotent.

Phase 3 — Provider platform + second sources. providers/archive/provider.py
(Internet Archive: advan + /download/<id>/<file>,~150 lines, no auth), providers/video/provider.py (yt-dlp-based, URL-driven),
soundfetch sources, docs soundfetch archive searchand soundfetch freesound search produce schema-identical manifests; a dataset
consumer can't tell whic

Later (post-Phase 3, outng the manifest; packaging(freesound-fetch alias already wired).

---
Open items to confirm duking)

- Exact Freesound licenseference enum values —confirmed once against live API during fixture capture; isolated in filters.py.
- /apiv2/search/ vs deprendpoint kept constant inone place.
- Freesound rate-limit qhonors Retry-After +configurable --rate-delay rather than guessing RPM.

Verification

1. pip install -e . (or python -m venv + install) inside
/home/losera/Freesound-B
2. pytest -m "not live" → green offline.
3. With FREESOUND_API_KEearch "piano" --license cc0-o out/ → inspect out/manifest.jsonl; soundfetch freesound download "piano"
--mode preview -o out/ →zes match, no .wavmislabeled files.
4. Phase 2: soundfetch frowser dance; --modeoriginal downloads a lossless file and md5 matches.
5. Phase 3: soundfetch ags" -o ia-out/ produces amanifest identical in shape to Freesound's.

Sources: Freesound API v2 resources, Freesound OAuth2 authentication, freesound-python.
