# Dataset split lowercase fast path

This Python-only performance slice narrows the registered dataset registry split
matching hot path in `worker.dataset_registry.catalog._path_part_matches_split`.

The common Hugging Face cache path uses lowercase split names such as
`validation-00000.jsonl`. The prior implementation lowercased every candidate
path part before checking exact/prefix and stem matches. This slice first checks
whether the path part can match the requested split by its first character,
returns early for obvious non-matches, then uses the existing lowercase fallback
for mixed-case filenames and directories.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`dataset-registry-limited-read-streaming` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries over:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/dataset_registry_split_match_probe.py`

## Verification plan

Run the registered focused tests, changed-scope coverage, and local Linux probe.
Compare the direct probe against an `origin/main` baseline worktree before
opening the PR; GitHub Actions PR-scoped performance remains the merge gate.