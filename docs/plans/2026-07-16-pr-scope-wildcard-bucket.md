# PR-scoped scope matcher wildcard bucket slice

## Scope

This Python-only performance slice targets the PR-scoped performance scope matcher in `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The affected path is already covered by the registered PR-scoped probe `pr-scoped-performance-scope-matcher` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, so this slice does not add a new probe.

## Optimization

Keep exact and wildcard watch-glob semantics unchanged while reducing wildcard matcher scans for large changed-file sets. Bucket wildcard probe matchers by the first literal path segment in their prefix so paths such as `docs/...` do not rescan all `services/...` wildcard probes.

## Verification

- Run the registered focused `test_command` for `pr-scoped-performance-scope-matcher`.
- Run its registered `coverage_command` and require changed-scope coverage to remain at or above the repository threshold.
- Run the registered probe locally on Linux against `origin/main` and this branch using `scripts/pr_scoped_performance_run.py`.
- Use GitHub Actions PR-scoped performance CI as the merge gate.

## Known boundary

This slice is Python-only and fully locally verifiable on Linux; no Swift runtime validation is involved.
