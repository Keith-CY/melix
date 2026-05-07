# Issue 510 Progressive Speech Streaming Plan

## Context

Issue #510 tracks the first end-to-end contract slice for low-latency speech
streaming. The existing `/v1/audio/speech` path is buffered: the control plane
calls the worker's unary `Speak` RPC and returns the fully materialized audio
bytes after synthesis finishes.

## Proposed Change

- Extend `SpeakRequest` with an explicit `stream` flag and bounded
  `stream_interval_ms` cadence.
- Add a worker `SpeakStream` RPC that emits a self-describing progressive WAV
  envelope before PCM chunks, then a finish diagnostic event.
- Preserve the existing unary `Speak` path as the buffered fallback when
  streaming is absent or disabled.
- Expose the streaming receipt through worker runtime stats and control-plane
  metrics:
  - `speech_streaming_enabled`
  - `speech_streaming_interval_ms`
  - `speech_first_audio_latency_ms`

## Implementation Notes

- The progressive WAV envelope uses a standard RIFF/WAVE header with unknown
  RIFF and data chunk sizes so clients can begin playback before the final
  byte count is known.
- `stream_interval_ms` controls PCM chunk frame bounds rather than adding
  artificial sleeps. Runtime generation cadence remains backend-owned.
- The deterministic speech runtime emits valid progressive WAV bytes for
  streaming fixtures while keeping the buffered deterministic payload stable
  for existing compatibility tests.
- The Swift text worker keeps speech ownership explicit by exposing the new
  streaming RPC as a structured unimplemented stream event, matching the unary
  speech fallback that routes speech work to the Python worker family.
- The `M17.4` repository-owned speech smoke now records a progressive
  Qwen3-TTS fixture for the same prompt/voice pair as the buffered fallback.
  It compares streamed first-audio latency against buffered response latency
  and records progressive WAV playability, parity, malformed-stream count, and
  chunk-count evidence.

## Verification Plan

- Regenerate protocol artifacts with `make proto`.
- Python focused tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- Swift focused tests:
  `HOME="$PWD/.swift-home/control-plane-swift" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/control-plane-swift" xcrun swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- Diff hygiene: `git diff --check`.
- Speech smoke acceptance:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx python scripts/m17_speech_runtime_smoke.py --json`

## Success Metrics

- Streaming `/v1/audio/speech` returns a streamed `audio/wav` body whose first
  bytes are the progressive WAV envelope.
- Streaming requests forward `stream=true` and `stream_interval_ms` to the
  worker and expose first-audio metrics.
- Buffered speech requests continue to use the unary worker path.
- The speech smoke reports at least a 50 percent first-audio latency reduction
  for the progressive Qwen3-TTS fixture versus the same prompt/voice buffered
  fallback, with zero malformed progressive WAV streams.
- Focused Python and Swift tests pass.

## Verification Results

- `make proto-check`: passed.
- `git diff --check`: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --frozen --project services/mlx-worker-python --extra mlx python scripts/m17_speech_runtime_smoke.py --json`: passed with `ok=true`, `speech.synthesis.qwen3_tts.streaming_ttfa_reduction_pct=65.99`, `speech.synthesis.qwen3_tts.streaming_malformed_wav_count=0.0`, and `speech.synthesis.qwen3_tts.streaming_chunk_count=6.0`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --frozen --project services/mlx-worker-python --extra mlx pytest -q tests/integration/test_m17_speech_runtime_smoke.py services/mlx-worker-python/tests/test_acceptance_metrics.py::test_build_phase17_speech_metrics_report_tracks_backend_and_locale_evidence`: `2 passed`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --frozen --project services/mlx-worker-python --extra mlx pytest -q tests/integration/test_m17_speech_runtime_smoke.py::test_m17_speech_runtime_smoke_records_live_audio_operator_evidence`: `1 passed`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --frozen --project services/mlx-worker-python pytest -q tests/integration/test_recovery_flows.py::test_warm_followup_prefers_hot_route_and_records_ttft_delta`: `1 passed`.
- Python focused tests for the worker streaming, runtime, bridge, acceptance,
  recovery jitter guard, and smoke scope: `96 passed`.
- Python changed-line coverage for the touched worker/smoke scope: `96.62%`
  (`372/385`).
- Python changed-line coverage after CI-failure hardening: `96.63%`
  (`373/386`).
- Swift control-plane focused streaming/worker-client suite: `257 passed`.
- Swift control-plane changed-line coverage for the touched handwritten scope:
  `98.31%` (`641/652`).
- Swift text-worker focused RPC fallback test: passed.
- Swift text-worker changed-line coverage for the touched handwritten scope:
  `100.00%` (`26/26`).
