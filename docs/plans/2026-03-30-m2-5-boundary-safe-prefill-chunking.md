# M2.5 Boundary-Safe Prefill Chunking

## Goal

Chunk long prefill work at safe restore boundaries so large prompts remain restart-safe and cache-aware.

## Scope

- define safe chunk boundaries for prefill
- preserve restore safety and cache identity across chunks
- keep scheduling and progress reporting aware of chunked execution

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/`

## Implementation Notes

- chunk boundaries must align with restore semantics rather than only token counts
- prefill progress should remain understandable when one logical request spans multiple chunks
- chunking should remain compatible with future VLM reuse work

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- long prefill requests can execute in safe chunks without breaking restore correctness
- chunk-aware progress and restore behavior are test-covered
