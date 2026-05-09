# Event Extraction Similarity Normalization Translate Slice

## Scope

This Python-only performance slice keeps event-extraction string similarity semantics unchanged while replacing the per-character ignored-character filter in `_normalize_similarity_text` with a precomputed `str.translate` deletion table.

Touched path:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `event-extraction-alignment-accepted-edge-cache` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused event-extraction alignment and string-similarity tests.
- `coverage_command` for changed-scope coverage.
- `probe_command` reporting `elapsed_ms_mean` and `similarity_elapsed_ms_mean`.

## Verification Plan

Run the registered focused tests, changed-scope coverage, and the local PR-scoped probe on Linux before pushing. The optimization is accepted only if behavior stays identical and the registered probe does not regress.

## Expected Benefit

Normalization currently lowercases and then filters ignored characters through a Python generator. A precomputed translation table lets CPython delete ignored characters in C after lowercasing, reducing overhead on uncached similarity inputs while preserving the same normalized strings.
