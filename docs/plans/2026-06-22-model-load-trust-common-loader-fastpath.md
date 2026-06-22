# Model load trust common loader fast path

## Scope

This Python-only performance slice is limited to `worker.model_load_trust._is_trust_applicable(...)` in `services/mlx-worker-python/worker/model_load_trust.py`.

The hot path resolves model-load trust policy for common MLX loader names (`mlx-lm`, `mlx-vlm`) while probing `config.json` custom loader metadata. The slice adds exact common-name membership checks before the normalized `strip().lower().replace("-", "_")` fallback path. Semantics for uncommon casing, alternate aliases, deterministic VLM runtimes, explicit `supports_trust_policy`, and non-applicable runtimes remain unchanged.

## Registered probe

Affected paths are covered by the existing registered PR-scoped performance probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Verification plan

1. Add a regression test proving common loader names bypass the normalized fallback membership path.
2. Run the registered focused pytest command for `model-load-config-json-bytes` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux and require at least 95% changed-scope coverage.
4. Run the registered probe locally against `origin/main` baseline and this branch with at least three samples.
5. Use GitHub Actions PR-scoped performance as the final merge gate before squash merge.

## Expected performance signal

The probe should show a small but measurable `elapsed_ms_mean` reduction for the common `mlx-lm` trust-policy resolution loop by avoiding repeated string normalization on each request. Memory should remain flat or slightly lower; behavior should be unchanged.
