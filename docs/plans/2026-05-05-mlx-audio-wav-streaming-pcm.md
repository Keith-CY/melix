# MLX Audio WAV PCM Streaming Plan

## Goal

Reduce transient memory pressure in MLX audio text-to-speech WAV serialization by avoiding a fully materialized flat sample list and whole PCM byte buffer before writing WAV frames.

## Linux-only constraint

This is a Python-only worker-runtime slice. It can be validated on Linux with focused pytest, changed-scope coverage, and a synthetic WAV conversion performance probe. It does not require macOS or Swift execution.

## Touched files

- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_audio_wav_streaming_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Register `mlx-audio-wav-streaming-pcm` in the PR-scoped performance registry. The probe converts a nested synthetic 240,000-sample mono audio payload to WAV bytes and reports:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `peak_bytes_mean`
- `sample_count`
- `wav_bytes`

## Success metrics

- Preserve WAV sample rate, mono channel count, 16-bit sample width, frame count, clamping, and returned bytes.
- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe reports the same `wav_bytes` and `sample_count` with lower peak memory than `origin/main`.
