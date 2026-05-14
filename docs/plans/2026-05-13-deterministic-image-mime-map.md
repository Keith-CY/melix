# Deterministic image MIME map reuse

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`.

The deterministic image runtime resolves MIME types for each generated or edited image job. The previous helper rebuilt the same literal mapping every time `_mime_type_for_format()` was called. This slice hoists that stable mapping to a module-level constant so repeated image generation/edit paths reuse one dictionary while preserving the existing supported format contract.

## Registered probe

The affected runtime path is already covered by the registered PR-scoped probe `deterministic-image-output-byte-accounting` in `infra/perf/pr_scoped_probes.json`. That entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_image_output_bytes_probe.py`

The local Linux probe compares `elapsed_ms_mean` and preserves output byte accounting guard rails. GitHub Actions PR-scoped performance remains the merge gate after push.

## Verification plan

1. Run the focused image runtime pytest selection from the registered probe.
2. Run changed-scope coverage through the registered coverage command.
3. Run `scripts/pr_scoped_performance_run.py` for `deterministic-image-output-byte-accounting` against a clean `origin/main` base worktree and this branch.
4. Accept only if behavior stays equivalent and the registered probe is green with no metric regression beyond noise.

## Success criteria

- Focused image tests pass.
- Changed-scope coverage for touched executable scope remains at least 95%.
- The registered probe completes locally and in CI.
- The PR-scoped performance workflow reports the registered probe successfully before merge.
