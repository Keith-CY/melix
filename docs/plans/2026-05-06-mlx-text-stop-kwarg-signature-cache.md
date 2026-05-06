# MLX Text Stop Kwarg Signature Cache Optimization

## Goal

Reduce repeated runtime signature introspection in the MLX text generation stop-sequence hot path.

## Scope

Touched files:

- `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_backend.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_text_stop_kwarg_signature_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker runtime slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and an explicit command-json performance probe. No Swift or macOS-only validation is required for the local evidence.

## Performance probe

Registered scoped probe: `mlx-text-stop-kwarg-signature-cache`.

The probe runs repeated synthetic `AutoMLXBackend.generate_tokens(...)` calls with stop sequences and records:

- `elapsed_ms_mean` — lower is better.
- `inspect_signature_calls_mean` — lower is better.
- `stream_signature_calls_mean` — structural metric proving stream-generation signature introspection is cached.

## Success metrics

- Preserve stop-sequence forwarding behavior.
- Reduce stream-generation signature inspections from once per generation request on `origin/main` to one cache miss per sample on the branch.
- Maintain at least 95% changed-scope automated coverage for touched executable Python files.
