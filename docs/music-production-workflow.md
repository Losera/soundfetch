# License-aware sound collection for music production

Soundfetch is useful when a producer needs a reviewable folder of openly
licensed source recordings. It is a batch collection tool, not a sample-store
browser: it does not currently play previews, display waveforms, detect BPM or
key, normalize loudness, resample audio, or integrate directly with a DAW.

## Collect a small CC0 folder

```bash
python -m venv .venv
. .venv/bin/activate
# After the first package-index publication:
pip install soundfetch

# Until then, run this from a source checkout instead:
# pip install .

soundfetch openverse search "single bird chirp" \
  --license cc0 --extension mp3 --max-results 10 -o sounds/birds
soundfetch manifest report sounds/birds/manifest.jsonl
```

Review each landing-page URL and license in `manifest.jsonl`. Choose the
provider IDs you want, then download only those entries:

```bash
soundfetch openverse download \
  --manifest sounds/birds/manifest.jsonl \
  --provider-id OPENVERSE_ID \
  -o sounds/birds
soundfetch manifest report sounds/birds/manifest.jsonl
```

Audition the downloaded files with the operating system, DAW, or sample manager
you already trust. Import the audio files into the DAW without renaming or
moving `manifest.jsonl`; keep the manifest beside the project as the source and
license record. Openverse metadata is an upstream assertion, not independent
license certification, so confirm the original landing page before release.

For CC-BY material, install the export extra and generate an attribution file:

```bash
pip install "soundfetch[export]"
python -c 'from soundfetch.export import export_attribution; export_attribution("sounds/birds/manifest.jsonl")'
```

If auditioning, waveform selection, conversion, or DAW handoff is the blocking
step, report the exact workflow through the feature-request template. That
evidence will determine whether Soundfetch adds a generated local review page
or stays focused on collection and provenance.
