# Rerank top-k=1 fast path

## Goal

Reduce redundant bounded top-k ranking overhead in the Python rerank core when callers request only the single best document.

## Scope

- `services/mlx-worker-python/worker/engine/rerank_core.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `scripts/rerank_top_k_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Proposed optimization

`RerankCore._rank_scores(...)` currently sends every bounded request through `heapq.nsmallest(...)`. For `top_k == 1`, a single strict max scan preserves the existing ordering contract — highest score first, earliest index on ties — without constructing heap key tuples.

## Probe

Update the existing registered scoped CI probe `rerank-core-top-k-heap-selection` so its checked-in script measures the `top_k=1` workload that this slice changes.

Success metrics:

- identical selected result and checksum versus the legacy sort contract
- lower `elapsed_ms_mean`
- no material regression in `peak_bytes_mean`

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <focused rerank tests and probe registry tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json <touched executable/test files>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/rerank_top_k_probe.py
git diff --check
```
