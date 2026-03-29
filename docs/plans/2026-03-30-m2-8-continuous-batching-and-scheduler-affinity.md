# M2.8 Continuous Batching And Scheduler Affinity

## Goal

Upgrade the scheduler to batch compatible requests continuously while still honoring cache affinity, latency class, and operator-facing fairness.

## Scope

- add continuous-batching admission and merge logic
- preserve latency-sensitive routing where batching would be harmful
- keep cache-affinity and queue-aging policies explicit

## Files

- update `services/control-plane-swift/Sources/Requests/`
- update `services/control-plane-swift/Sources/EnginePool/`
- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/mlx-worker-python/worker/registry.py`

## Implementation Notes

- batching policy must be observable through scheduler metrics
- affinity should prefer safe cache reuse without starving cold requests forever
- completed capability reporting should no longer claim batching is unsupported on the target runtime path

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- compatible requests can batch continuously on the supported runtime path
- scheduler metrics expose batch size, occupancy, and affinity decisions
