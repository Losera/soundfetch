# Soundfetch product and workflow roadmap

**Status:** Product hypotheses and sequencing guidance; not an approved
implementation plan

**Last reviewed:** 2026-08-12

**Current release focus:** 0.4.0 beta candidate

This document consolidates the product, workflow, scale, and portfolio ideas
discussed in August 2026. It is a prioritized decision aid. Items below become
committed work only through an approved task or proposal. Changes to provider
boundaries, manifest semantics, the public API, persistent storage, or
deployment architecture require a separate proposal and human approval.

## Product direction

Soundfetch should become a dependable, governed audio-data acquisition layer:

```text
discover -> review -> download -> verify -> describe -> export -> reproduce
```

Its advantage should be trustworthy collection rather than an ever-growing
list of AI frameworks. Provider behavior stays behind the existing provider
interface; orchestration, resume, checkpointing, and manifest behavior stay in
the shared core. The append-only, last-record-wins JSONL manifest remains the
source of truth and a compatibility boundary.

## P0: finish and ship 0.4.0

### Completed candidate evidence

- The mixed-provider selected-download ordering defect was fixed before
  release, preserving the JSON attribution contract used by Incant Audio.
- Fetch/write boundaries and the MCP tool surface received a dedicated
  security-hardening pass with regression coverage.
- The deterministic suite, distribution build, Twine validation, wheel-only
  install, and bounded Archive smoke test passed for the recorded candidate.
- A bounded like-for-like benchmark rerun produced 12/12 valid samples without
  relaxing its safety caps. The small network-bound sample supports no
  performance-regression or improvement claim.
- One real Claude Desktop trial passed tool discovery, provider status, and a
  bounded Archive search on unofficial Arch/AUR packaging.

The detailed evidence and its exact commit scope live in
[`beta-readiness-0.4.0.md`](beta-readiness-0.4.0.md). Evidence from an earlier
candidate must not be treated as verification of later changes.

### Remaining release gates

Complete these before adding product surface or publishing:

- Complete the required human semantic review of the release diff.
- Decide which operating systems and MCP hosts the beta actually claims to
  support. Test those exact combinations and record the evidence.
- Exercise `download_manifest` through Claude Desktop, including clean stdout,
  progress on stderr, shutdown, output location, and filesystem side effects.
- Confirm the selected-download workflow end to end with Incant Audio rather
  than only through Soundfetch's own MCP client.
- Repeat the offline suite, build, Twine validation, wheel-only installation,
  CLI/API/MCP smoke tests, and `git diff --check` against the final candidate.
- Publish only after the release checklist is satisfied and publication is
  explicitly authorized. Then verify installation from the published artifact.
- Produce a short install-and-collect demonstration and make limitations,
  licensing behavior, supported platforms, and recovery instructions obvious.

## P1: strengthen the existing workflow

### Search quality and review

- Measure provider result relevance with a small versioned query set before
  changing ranking behavior.
- Improve Internet Archive relevance only from measured failure cases. Prefer
  structured metadata filters and deterministic ranking over an LLM.
- Add a clear review experience for manifests: filtering, sorting, selection,
  and inspection without downloading again.
- Preserve exact provider metadata and provenance so users can audit why an
  item was included.
- Make empty, restricted, oversized, malformed, and irrelevant result states
  understandable and recoverable.

### Download reliability

- Extend real-provider validation beyond the happy path: Freesound, video,
  overwrite, resume, partial files, worker concurrency, rate limits,
  `fail_fast`, checksum mismatch, retries, and interrupted runs.
- Keep bounded concurrency, input-order reporting, token-bucket pacing,
  partial-file resume, checksum verification, and atomic replacement as
  explicit invariants.
- Add fault-injection or deterministic integration tests for network failures,
  truncated responses, incorrect sizes/checksums, and process interruption.
- Make retryability and terminal per-item failures explicit in machine-readable
  output.
- Measure throughput, latency, error rates, and provider throttling with safe,
  reproducible benchmark configurations. Report distributions and failures,
  not just averages.

### API, CLI, and MCP usability

- Keep CLI, Python, and MCP behavior aligned around the same core operations.
- Maintain stable, versioned JSON contracts for machine clients such as Incant
  Audio; document compatibility and deprecation policy before changing them.
- Add contract tests that run the packaged wheel, not only the checkout.
- Test MCP discovery, search, download, progress isolation, cancellation, and
  shutdown in supported real hosts.
- Improve actionable diagnostics for missing credentials, OAuth, optional
  dependencies, provider restrictions, rate limits, and invalid manifests.
- Add framework-specific adapters only after concrete demand, a maintainer,
  supported-version policy, and real-dependency CI exist. MCP remains the
  default generic integration surface.

## P2: make Soundfetch a stronger dataset foundation

Build dataset preparation adjacent to the stable collection core rather than
turning providers into ML code:

- Validate decoded audio, duration, sample rate, channel count, format, and
  corruption after download.
- Define optional, reproducible normalization steps such as resampling, channel
  conversion, loudness policy, and clipping detection. Record every transform.
- Add exact duplicate detection by checksum and investigate acoustic
  near-duplicate detection as a separately evaluated feature.
- Generate deterministic train/validation/test splits. Split by source item,
  uploader, recording session, or acoustic group when needed to prevent data
  leakage.
- Produce dataset statistics, quality summaries, license distributions, and
  generated dataset cards.
- Preserve source manifest, transformation configuration, tool version, split
  assignment, checksums, and output lineage so a dataset can be reconstructed.
- Support analytical access through Parquet and DuckDB where it improves large
  manifest analysis without replacing JSONL as the compatibility source.
- Keep WebDataset and attribution exports verified against real dependencies.
- Repair and restore the Hugging Face exporter only with a current API design,
  real-library tests, and CI coverage.
- Provide one end-to-end tutorial that uses Soundfetch data to train and
  evaluate a small audio model.

The best downstream demonstration is an audio-effect parameter estimator:
Soundfetch supplies governed source recordings; a separate PyTorch project
creates dry/processed pairs, leakage-safe splits, baselines, training, and
evaluation.

## P3: product expansion justified by users

The possible source integrations listed under
[Future provider candidates](../README.md#future-provider-candidates) are an
investigation backlog, not a provider-count target. Apply the new-provider
decision gate below before proposing implementation.

### Incant Audio integration

- Validate the exact manifest-selection and local-file handoff expected by
  Incant Audio.
- Preserve user review and explicit selection before download.
- Keep license and generative-AI preference enforcement deterministic; an LLM
  must never invent or override compliance metadata.
- Consider text-guided sample discovery for future sampler or granular features,
  but retain provider filters and the manifest as authoritative.

### Local manifest application

A local UI could sit above the public Python API and manifest to support search,
review, preview, selection, download status, attribution, and dataset export.
Before building it, validate that CLI/MCP users actually need this workflow and
approve the UI/API boundary. Do not duplicate provider implementations in the
UI.

### Semantic audio retrieval

Consider text-to-audio or audio-to-audio retrieval only after a labeled
evaluation set exists. Compare metadata/lexical retrieval with audio embeddings
and hybrid retrieval using recall-at-k and human relevance judgments. This is a
better fit for a separate retrieval/index component than for provider core.

Generic document RAG and a vector database are not current Soundfetch needs.
Structured metadata, exact identifiers, provider search, SQL, and lexical
ranking should be the baseline.

## P4: scale hypotheses after local product evidence

Everything in this section is a hypothesis. It does not approve a container,
service, database, queue, cloud account, or orchestration change.

### Containerized batch worker

Docker is appropriate for a headless collection/export worker or reproducible
evaluation environment, not necessarily for normal desktop CLI/MCP use. A
container design must explicitly handle mounted persistent output, manifests,
credentials, OAuth limitations, optional dependencies, resource limits, and
graceful interruption.

### Modest cloud service

If real users need scheduled or remote jobs, begin with the smallest operable
architecture:

```text
typed API -> job queue -> Soundfetch worker -> object storage
                                      \-> manifest + attribution + metrics
```

Potential AWS building blocks are ECR, one managed container/compute option,
S3, a queue, CloudWatch, and Secrets Manager or Parameter Store. Required work
includes least-privilege IAM, authentication, quotas, cost alarms, encryption,
retention, observability, cancellation, idempotency, rollback, and provider
terms/redistribution review.

Do not put a long download directly inside a synchronous web request. Do not
move the JSONL compatibility model to a database without an approved migration
and rollback plan. PostgreSQL may serve accounts/jobs and object storage may
hold artifacts, while manifests remain durable exported records.

### Kubernetes

Do not adopt Kubernetes now. Reconsider it only after measured demand requires
multiple independently deployed services, horizontal replicas, high
availability, rolling operations, and an owner for cluster operations. A single
managed container or virtual machine is the preferred first deployment.

## Engineering execution

Repository workflow, verification, Git, architecture-review, and handoff rules
live in [`../AGENTS.md`](../AGENTS.md) and remain authoritative. Roadmap work
must also preserve machine-readable stdout, validate optional integrations
against real dependencies, retain reproducible benchmark evidence, and treat
credentials, remote metadata, URLs, filenames, redirects, and downloaded media
as security boundaries.

## Optional learning opportunities

These are learning opportunities, not dependencies or implementation
commitments. Use them only when they solve the next demonstrated problem:

1. **SQL, DuckDB, and Parquet** for manifest and dataset analysis.
2. **Dataset versioning and lineage** through immutable manifests, checksums,
   transformations as code, and optionally DVC after the workflow is clear.
3. **Audio validation and features** with NumPy, SciPy, SoundFile, and relevant
   audio tooling.
4. **PyTorch** in a separate downstream audio-ML project using Soundfetch data.
5. **FastAPI** for a typed job or model-inference API.
6. **Docker** for reproducible headless workers and inference services.
7. **AWS fundamentals**: IAM, S3, one compute service, queues, secrets, logs,
   budgets, and rollback.
8. **Observability**: structured events, p50/p95/p99 latency, throughput,
   provider errors, retries, job state, and cost.
9. **CI/CD and supply-chain hygiene** for wheels, containers, dependency scans,
   signed/provenanced artifacts where appropriate, and post-publish smoke tests.

LangGraph is not needed for deterministic search/download orchestration. It may
be learned in a separate human-approval workflow, but should not replace the
shared engine. Kubernetes is conceptual learning only until scale proves a need.

## Decision gates and success metrics

Expand only when evidence passes the relevant gate:

| Area | Evidence before implementation | Success measure |
|---|---|---|
| Search ranking | Versioned relevance failures | Better relevance without license/filter regressions |
| New provider | Named user need and terms/API review | Stable mapping into core models and live verification |
| Framework adapter | Concrete demand and maintenance owner | Real-dependency CI and supported version matrix |
| Dataset feature | Downstream training/research need | Reproducible dataset and leakage/quality evidence |
| Semantic retrieval | Labeled retrieval queries | Improvement over metadata/lexical baseline |
| Web UI | Observed review-workflow friction | Users complete collection with fewer failures |
| Cloud worker | Remote/scheduled job demand | Reliable bounded jobs with controlled cost and recovery |
| Kubernetes | Sustained multi-service scale | Operational benefit exceeds cluster complexity |

Track product outcomes such as successful clean installs, completed collection
jobs, resume success, checksum failures detected, search relevance, attribution
completeness, dataset reproducibility, p95 latency, provider error rate, support
burden, and external-user retention. Avoid vanity metrics such as provider count
or framework count.

## Recommended sequence

1. Finish, review, publish, and independently install-verify 0.4.0.
2. Prove the Incant Audio selected-download workflow end to end.
3. Improve measured search relevance and harden real download failure paths.
4. Add dataset validation, statistics, deterministic splits, and lineage in a
   separately reviewed layer.
5. Use Soundfetch in one complete PyTorch audio-ML case study.
6. Validate demand for a local manifest review UI or semantic audio retrieval.
7. Containerize only the headless worker/evaluation use case.
8. Deploy one small cloud job service only when remote use is demonstrated.
9. Reassess orchestration and storage architecture from real usage data; do not
   pre-emptively add LangGraph, a vector database, or Kubernetes.
