# M3.4 Harmony Protocol Compatibility

## Goal

Add compatibility for harmony-style request and response semantics without introducing a second internal text runtime model.

## Scope

- add translation at the HTTP boundary
- map harmony semantics into the shared text semantic model
- keep streaming and completed-output behavior aligned with the existing execution path

## Files

- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- update `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
- update `services/control-plane-swift/Tests/HTTPGatewayTests/`

## Implementation Notes

- compatibility should stay in the translation layer
- request metadata must preserve enough fidelity for later tool-calling and reasoning integration
- avoid wire-shape drift between live and non-stream responses
- worker streaming assembly must suppress Harmony internal channels such as `thought`,
  `analysis`, and `reasoning` from public assistant content while preserving visible
  `final` and `commentary` channel text
- the same suppression applies to the Swift text worker generate/decode path because
  local serving may route text generation there instead of through the Python worker

## Verification

- `make swift-test`
- `make integration-test`
- Focused worker checks:
  - `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_generate_stream.py`
  - `xcrun swift build --package-path services/mlx-text-worker-swift --product melix-text-worker-swift`

## Acceptance

- harmony-compatible inputs can be translated into Melix execution requests
- streaming and completed outputs are contract-tested
- internal Harmony channel markers do not leak into streamed content or completed
  `assistant_text`
