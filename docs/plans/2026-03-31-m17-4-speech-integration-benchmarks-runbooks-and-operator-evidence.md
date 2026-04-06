# M17.4 Speech Integration Benchmarks, Runbooks, And Operator Evidence

## Status

Completed on 2026-04-06. The repository now owns a live-path speech smoke workflow that lazy-loads
cataloged managed speech families through the real HTTP surface, emits a machine-readable speech
operator-evidence report, promotes `Whisper`, `Parakeet`, `Kokoro`, and `Qwen3-TTS` from
`contract_only` to repository-owned live-path evidence, and documents reproduction plus diagnosis
in a dedicated runbook.

## Goal

Leave speech support with real integration evidence, benchmark data, and operator guidance across transcription and synthesis paths.

## Scope

- add live-path integration coverage for transcription and synthesis
- record backend-family and voice-specific metrics
- document operator workflows, dependency setup, and failure diagnosis

## Files

- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Benchmarks should distinguish backend family and voice family so operator guidance stays actionable.
- Runbooks should include missing-dependency diagnosis and locale or voice fallback inspection.

## Verification

- `make phase17-metrics`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/m17_4_py.coverage --source=services/mlx-worker-python/worker,tests/integration,scripts -m pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py -q`
- `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m17_4_py_coverage.json services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/worker/productization/__init__.py services/mlx-worker-python/worker/productization/family_support_matrix.py tests/integration/helpers.py scripts/m17_speech_runtime_smoke.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py`
- `swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests'`
- `swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests' --enable-code-coverage`
- `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
- `make proto`
- `make py-test`
- `make integration-test`
- `make swift-test`
- `make py-test`
- `make integration-test`

## Acceptance

- Speech integration coverage is live-path and reproducible.
- Metrics and runbooks provide concrete operator evidence for supported speech backend families.
