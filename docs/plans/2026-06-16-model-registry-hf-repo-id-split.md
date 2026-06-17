# Model registry Hugging Face repo id split fast path

## Scope

This Python-only performance slice is limited to the Hugging Face cache repo-name
parser in `services/mlx-worker-python/worker/model_registry/catalog.py`.
It preserves model registry semantics while avoiding the temporary list and
`removeprefix()` allocation in `_hf_cache_repo_id(...)` for repeated registry
and Hugging Face cache scans. It also reuses the existing pruned-subtree name
constant instead of rebuilding the same set literal for each prune check.

## Registered probe

The affected path is covered by the registered PR-scoped probes:

- `model-registry-plain-local-manifest-stat-elision`
- `model-registry-readme-source-fastpath`

Both registry entries in `infra/perf/pr_scoped_probes.json` include focused
`test_command`, `coverage_command`, and `probe_command` values for the model
registry catalog path. This slice does not add a new probe; it relies on those
registered model registry probes plus a local microbenchmark for the parser-only
hot path.

## Implementation plan

1. Add a focused regression test for `_hf_cache_repo_id(...)` covering valid,
   invalid, empty owner/model, and extra `--` suffix cases.
2. Replace the current `removeprefix().split("--", maxsplit=1)` parser with a
   direct prefix slice and first-separator lookup.
3. Run focused pytest, changed-scope coverage, the registered probe commands,
   and a parser-only local before/after microbenchmark.
4. Use PR-scoped performance CI as the merge gate for the registered probe
   report.

## Success criteria

- Behavior remains identical for valid and invalid Hugging Face cache repo names.
- Changed-scope coverage for the touched model registry/test/probe scope remains
  at or above 95%.
- Local parser microbenchmark and registered model registry probes do not regress;
  CI PR-scoped performance report is green before merge.
