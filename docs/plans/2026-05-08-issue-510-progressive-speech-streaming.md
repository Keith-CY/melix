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

## Verification Plan

- Regenerate protocol artifacts with `make proto`.
- Python focused tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- Swift focused tests:
  `HOME="$PWD/.swift-home/control-plane-swift" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/control-plane-swift" xcrun swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- Diff hygiene: `git diff --check`.

## Success Metrics

- Streaming `/v1/audio/speech` returns a streamed `audio/wav` body whose first
  bytes are the progressive WAV envelope.
- Streaming requests forward `stream=true` and `stream_interval_ms` to the
  worker and expose first-audio metrics.
- Buffered speech requests continue to use the unary worker path.
- Focused Python and Swift tests pass.
