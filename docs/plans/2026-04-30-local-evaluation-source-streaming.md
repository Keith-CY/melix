# Local Evaluation Source Streaming Plan

## Scope

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`

## Goal

Reduce redundant memory use when materializing local evaluation datasets from Linux-verifiable Python paths without changing cache keys, parsed rows, or error semantics.

## Proposed Change

1. Replace local source hashing based on `read_bytes()` with chunked streaming SHA-256 plus `stat().st_size`.
2. Replace JSONL loading based on `read_text().splitlines()` with line-by-line streaming that preserves row ordering and blank-line skipping.
3. Keep CSV behavior unchanged.

## Performance Probe

Run a self-contained Python probe that compares the previous in-memory local-source path against the updated branch path for a synthetic JSONL file and records:

- parsed row equivalence
- metadata equivalence (`sha256`, size)
- elapsed seconds
- peak traced allocation via `tracemalloc`

## Success Metrics

- Materialized datasets and metadata remain behaviorally equivalent for the touched path.
- Focused pytest for `test_evaluation_final_result.py` passes.
- Coverage for `evaluation_final_result.py` is at least 95%.
- The probe shows lower peak traced allocation for the streamed path.

## Verification Commands

```text
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_evaluation_final_result.py
PYTHONPATH=<repo>:<repo>/services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/productization/evaluation_final_result.py
python /tmp/<probe>.py
git diff --check
```
