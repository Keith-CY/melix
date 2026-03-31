# M6.8 Sparse Prefill Acceleration

## Goal

Add an experimental sparse-prefill acceleration mode behind a feature flag while preserving system-prompt safety and operator observability.

## Scope

- add sparse-prefill runtime policy
- preserve protected prompt regions
- expose measurable gain and rollback signals

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `tests/integration/`

## Implementation Notes

- feature gating should make the mode easy to disable globally or per model
- prompt-protection rules must be explicit and test-covered
- acceleration metrics should distinguish accepted skips from rejected opportunities
- use a first-class `sparse_prefill` acceleration mode rather than overloading `accelerated_prefill`
- protect system and developer prompt regions from sparse skipping even when later user blocks are eligible
- keep deterministic and Swift MLX backends behaviorally aligned enough that sparse-prefill probes remain comparable

## Execution Notes

- extend the worker and control-plane acceleration enums plus mode mappers to represent `sparse_prefill`
- preserve the existing `accelerated_prefill` mode semantics so current Phase 2 behavior does not regress
- add worker-local metrics for:
  - `swift_text.sparse_prefill_accepted_skip_count`
  - `swift_text.sparse_prefill_rejected_opportunity_count`
  - `swift_text.sparse_prefill_protected_region_count`
- treat user text that looks structured or repetitive as sparse-prefill eligible while keeping protected prompt regions intact
- surface the new mode through model settings and request translation without widening the desktop workflow beyond the existing acceleration selector

## Verification

- `make swift-test`
- `make integration-test`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py --json`
- inspect `swift_worker_direct.prefill[]` for `label = "prefill_sparse"`

## Acceptance

- sparse-prefill acceleration can be enabled and disabled explicitly
- protected prompt regions remain correct and test-covered
- sparse-prefill benchmark evidence is repository-visible and reproducible
