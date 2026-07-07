# Dataset source SHA-256 binding slice

## Scope

This Python-only performance slice is limited to dataset preparation hashing in
`services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The common ingest path repeatedly hashes normalized source text, source paths,
and deterministic validation split IDs. This slice reuses a module-level SHA-256
constructor binding instead of resolving `hashlib.sha256` or rebinding it per
record call.

No dataset ingest, segmentation, privacy, validation split, or receipt semantics
change.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for dataset preparation ingest behavior,
`scripts/dataset_source_records_probe.py`, and PR-scoped performance registry
coverage.

## Validation plan

Run locally on Linux before pushing:

1. Focused registered test command for `dataset-source-records-scandir`.
2. Registered changed-scope coverage command for the same probe.
3. Registered local PR-scoped performance runner comparing `origin/main` to this
   branch for `dataset-source-records-scandir`.

GitHub Actions PR-scoped performance remains the merge gate after opening the PR.

## Acceptance criteria

- Focused tests pass.
- Changed-scope coverage for touched files is at least 95%.
- The registered probe shows a clear improvement or non-regression for
  `record_elapsed_ms_mean` and no behavior guard failures.
