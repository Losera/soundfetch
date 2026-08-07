"""soundfetch: batch sound/data collection across the internet.

The public Python API lives in :mod:`soundfetch.api` and is re-exported
here for convenience::

    import soundfetch

    refs = soundfetch.search("piano", provider="freesound", license="cc0")
    soundfetch.save_search(refs, "out/manifest.jsonl")
    soundfetch.download(refs, dest_dir="out/")
"""

from .api import (
    DownloadResult,
    Provider,
    SearchParams,
    SoundRef,
    download,
    iter_latest,
    latest_by_sound,
    provider_names,
    read_records,
    ref_record,
    refs_from_manifest,
    save_search,
    search,
)

__version__ = "0.2.0"

__all__ = [
    # Types
    "SearchParams",
    "SoundRef",
    "DownloadResult",
    "Provider",
    "provider_names",
    # Functional API
    "search",
    "download",
    "save_search",
    "refs_from_manifest",
    # Manifest readers (dataset-index use case)
    "read_records",
    "iter_latest",
    "latest_by_sound",
    "ref_record",
    "__version__",
]
