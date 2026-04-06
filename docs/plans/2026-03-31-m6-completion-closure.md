# M6 Completion Closure

## Status

Completed on 2026-04-04. Melix now ships repository-owned acceleration benchmark evidence for
active KV quantization and sparse prefill, protected-scope conflict locking for quantization
operations, and runbook plus metrics coverage sufficient to record a parent-level `M6` completion
state in the execution index.

## Goal

Close the remaining implementation and verification gaps for `M6 Quantization And Inference Acceleration` on `main` without widening scope into later milestones.

## Why This Exists

Repository audit showed that most quantization pipeline slices are already implemented, but M6 still has three closure gaps:

- `M6.7` has feature and unit-test coverage for active KV quantization, but the plan still expects benchmark evidence.
- `M6.8` has feature and unit-test coverage for sparse prefill, but the plan still expects benchmark or runbook evidence.
- `M6.9` currently blocks conflicts at a request or artifact-path scope, but the plan wording targets incompatible work on the same protected model family.

## Scope

- add executable benchmark evidence for active KV and sparse-prefill acceleration flows
- publish a repository-visible runbook for the acceleration evidence commands
- tighten quantization conflict locking to use a protected scope derived from model identity rather than only the raw request path
- add or update tests for the new lock semantics and benchmark outputs

## Out Of Scope

- redesigning the full quantization architecture
- adding new quantization algorithms beyond the current M6 set
- changing unrelated Phase 2 or Phase 5 milestone behavior unless required to close the M6 gaps

## Measurement Points

- active-KV acceleration probe exports `swift_text.active_kv_quantization_ratio`
- sparse-prefill probe exports:
  - `swift_text.sparse_prefill_accepted_skip_count`
  - `swift_text.sparse_prefill_rejected_opportunity_count`
  - `swift_text.sparse_prefill_protected_region_count`
- conflict-lock tests prove blocked operations fail explicitly on the same protected scope

## Success Metrics

- active-KV and sparse-prefill probes are executable from repository-owned scripts
- repository runbooks document the commands and expected evidence shape
- M6-focused Python tests pass after the changes
- metrics output for the touched scope is non-`N/A`

## Verification

- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_phase5_model_ops_metrics.py`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/quantization_benchmarks.py --json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/quantization_release_gate.py --json`
- touched-scope acceleration benchmark command for active-KV and sparse-prefill evidence

## Acceptance

- `M6.7` benchmark evidence is executable and documented.
- `M6.8` sparse-prefill evidence is executable and documented.
- `M6.9` conflict locking is protected-scope aware and test-covered.
- The repository exposes a credible path to call M6 complete on `main`.
