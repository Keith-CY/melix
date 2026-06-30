# Model registry direct MLX exact-match fast path

## Scope

This Python-only performance slice is limited to the model registry direct MLX metadata signal check in `services/mlx-worker-python/worker/model_registry/catalog.py`.

The common decoded-Hub/config path already carries exact string values such as `library_name: "mlx"` or `tags: ["mlx"]`. The previous direct-signal helper normalized every candidate with `strip().lower()` before checking it, allocating normalized strings even for the exact hot path.

## Registered probe

The affected path is covered by the registered PR-scoped probes in `infra/perf/pr_scoped_probes.json` that watch `services/mlx-worker-python/worker/model_registry/catalog.py`:

- `model-registry-readme-source-fastpath`
- `model-registry-plain-local-manifest-stat-elision`

Both registry entries include focused `test_command`, `coverage_command`, and `probe_command` entries. This slice uses `model-registry-readme-source-fastpath` as the local direct probe because it exercises the direct MLX metadata signal path and associated README/config fallback behavior.

## Implementation plan

1. Add an exact `"mlx"` comparison before the normalized `strip().lower()` fallback for `library_name` and tag entries.
2. Keep existing behavior for whitespace/case variants by retaining the normalization fallback.
3. Add a focused unit test that proves exact and normalized values still return the same boolean results.
4. Run the focused model-registry test, changed-scope coverage, and the registered probe locally on Linux before opening the PR.

## Validation boundary

This is a Python-only change and is locally verifiable on Linux. CI remains the source of truth for the registered PR-scoped performance report and any wider context probes.
