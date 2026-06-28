# Dataset source normalize-once slice

## Scope

This slice keeps dataset source ingest behavior unchanged while removing the
plain-text pre-normalization call in `_iter_source_records`. `_record` already
normalizes line endings before hashing, byte accounting, and storing record
text, so pre-normalizing plain file text performed the same two string replace
passes twice for non-structured source files.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `dataset_preparation.py`, its focused ingest tests,
and `scripts/dataset_source_records_probe.py`.

## Implementation plan

1. Add a focused regression test proving plain-text source ingest normalizes line
   endings exactly once while preserving normalized output text.
2. Pass the raw file text into `_record` for non-structured source files and let
   `_record` remain the single normalization boundary.
3. Run the registered focused test command, changed-scope coverage, and the
   registered probe locally on Linux against `origin/main` and this branch.

## Validation boundary

This is a Python-only Linux-verifiable slice. No Swift runtime behavior is
changed.
