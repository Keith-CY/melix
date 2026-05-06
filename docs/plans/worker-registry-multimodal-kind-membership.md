# Worker registry multimodal kind membership optimization

## Goal

Avoid rebuilding the same multimodal request-kind membership set on every worker request lifecycle counter update.

## Linux-only constraint

This is a Python worker slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and the existing worker registry PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/registry.py`
- `services/mlx-worker-python/tests/test_runtime_edges.py`
- `scripts/worker_registry_resident_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation approach

- Hoist the multimodal runtime-kind membership values into a module-level frozenset.
- Keep `WorkerRegistry._is_multimodal_request_kind(...)` as the compatibility boundary and have it query the prebuilt frozenset.
- Add focused regression coverage for every multimodal kind plus text/unknown/empty non-multimodal inputs.
- Extend the existing worker registry resident-bytes probe with a request lifecycle churn measurement that exercises `start_request`, `set_request_phase`, and `finish_request`, where the optimized helper is on the hot path.

## Performance probe

Existing registered probe: `worker-registry-resident-bytes-accumulator`.

New metric added to the existing probe:

- `request_lifecycle_elapsed_ms_mean` — lower is better, measures per-request lifecycle counter churn for a synthetic mix of multimodal and text requests.

Success means semantics are unchanged and the branch does not regress the request lifecycle measurement versus `origin/main`.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...focused worker registry tests...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ...focused tests... && coverage json ... && python scripts/changed_scope_coverage.py ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/worker_registry_resident_probe.py`
- `python scripts/pr_scoped_performance_run.py --probe-id worker-registry-resident-bytes-accumulator ...` for base-vs-head evidence
- `git diff --check`
