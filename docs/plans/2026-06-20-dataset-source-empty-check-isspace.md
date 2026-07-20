# Dataset source empty check isspace fast path

This Python-only performance slice is limited to `worker.productization.dataset_preparation._iter_source_records()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/dataset_preparation.py`
- `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_source_records_probe.py`

## Optimization

Replace `not text.strip()` with `not text or text.isspace()` when detecting empty ingest sources. This preserves the empty/whitespace-only rejection behavior while avoiding allocation of a stripped copy for normal non-empty source files.

## Verification plan

1. Extend the focused ingest failure test to include a whitespace-only text source.
2. Run the registered focused test command for `dataset-source-records-scandir` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally via `scripts/pr_scoped_performance_run.py` against `origin/main` and this branch.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Focused tests pass and the whitespace-only source remains classified as `DATASET_INGEST_EMPTY_SOURCE`.
- Changed-scope coverage for touched files remains at or above 95%.
- The registered local and CI probes show non-regression or improvement for `elapsed_ms_mean` and related source-record metrics.

## 2026-06-27 follow-up: JSONL blank-line skip

The next focused slice keeps the same Python boundary and registered
`dataset-source-records-scandir` probe, but narrows to JSONL structured data
ingest in `_structured_records(...)`. Blank JSONL records previously used
`line.strip()` before skipping empty lines, allocating a stripped copy even
though the common non-empty line immediately flows into `json.loads(...)`.

This slice replaces that guard with `not line or line.isspace()`, preserving
blank and whitespace-only line skipping while avoiding stripped-copy allocation
for populated JSONL rows. The existing focused ingest test now includes a
whitespace-only JSONL line to keep behavior parity explicit.

## 2026-06-27 follow-up: common lowercase source suffix fast path

This Python-only follow-up stays within `_classify_source_kind_name(...)` and
the existing registered `dataset-source-records-scandir` probe. The source tree
probe repeatedly classifies lowercase `.md`, `.py`, and `.jsonl` filenames, but
those names previously fell through to the generic suffix path that finds the
last dot and lowercases the suffix before set membership checks.

This slice adds exact lowercase suffix returns for `.md`, `.py`, and `.jsonl`
after the existing text fast paths. Uppercase and mixed-case names still fall
through to the generic lowercase path, preserving current behavior while
avoiding generic suffix allocation/work for common generated dataset inputs.

## 2026-06-29 follow-up: structured source suffix fast path

This Python-only follow-up extends the lowercase structured source suffix fast
path to `.json`, `.csv`, and `.tsv` in `_classify_source_kind_name(...)`.
Uppercase and mixed-case structured suffixes still fall through to the generic
lowercase path so ingest behavior remains unchanged.

The registered `dataset-source-records-scandir` probe fixture now includes all
structured ingest suffixes (`.jsonl`, `.json`, `.csv`, `.tsv`) so local Linux
and PR-scoped CI probe classification timing covers the optimized path before
the slice is merged.

## 2026-07-20 follow-up: source-id digest cache

This Python-only follow-up keeps the same registered `dataset-source-records-scandir`
probe and narrows to `_record(...)` source-id construction. Repeated source record
materialization for stable paths previously encoded and hashed the path text on
every pass even though the source-id is deterministic for a path. This slice adds
a bounded LRU cache for the path-text-to-source-id digest while keeping content
digest caching, metadata copying, normalized text handling, and the public source-id
value unchanged.

Success remains gated by the registered focused tests, changed-scope coverage,
local Linux probe output for `record_elapsed_ms_*`, and PR-scoped performance CI.
