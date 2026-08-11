# Deferred adapter and export work

The framework adapters and dataset exporters developed for the 0.3.0 beta are
deliberately deferred. Their implementation and tests remain recoverable from
the retained `feat/agent-usability` branch at commit `0c4a9b3`.

## Deferred files

The following files are preserved at that source commit:

- `src/soundfetch/adapters/__init__.py`
- `src/soundfetch/adapters/langchain.py`
- `src/soundfetch/adapters/llamaindex.py`
- `src/soundfetch/adapters/smolagents.py`
- `src/soundfetch/export.py`
- `tests/unit/test_adapters.py`
- `tests/unit/test_export.py`

The corresponding optional dependency groups and public documentation were
removed from the 0.3.0 release surface. They can be reconstructed from the same
commit's `pyproject.toml`, `README.md`, and `llms.txt` without merging the
commit wholesale.

## Why this is excluded from 0.3.0

The adapters commit the project to three distinct optional framework contracts:
LangChain, LlamaIndex, and Smolagents. The exporters add a separate dataset and
attribution API surface backed by Hugging Face Datasets, WebDataset, and
SoundFile. There is not yet concrete usage evidence to justify maintaining
these contracts, and validation against the real optional dependencies is
incomplete. Shipping them in the beta would make provisional integrations look
supported before their compatibility boundaries and maintenance cost are
understood.

## Revisit triggers

Reconsider this work only when all of the following are available:

- concrete user demand for the relevant adapter or export workflow;
- a named maintenance owner;
- documented supported dependency and version matrices;
- integration tests using the real optional dependencies; and
- an approved proposal for the public Python API and packaging extras.

Each adapter or exporter may be reconsidered independently; demand for one is
not evidence that all of them should ship.

## Selective recovery

Do not merge `feat/agent-usability` wholesale: it contains unrelated work that
is already integrated or may have evolved. Recover only the approved files from
the retained source commit, for example:

```bash
git show 0c4a9b3:src/soundfetch/export.py > /tmp/soundfetch-export.py
git diff 0c4a9b3^ 0c4a9b3 -- src/soundfetch/export.py tests/unit/test_export.py
```

Review the historical implementation against the current manifest and public
API contracts, restore only the selected files and dependency group, add
real-dependency integration coverage, and run the current verification suite.
Treat restoration as a new public-API proposal requiring semantic review.
