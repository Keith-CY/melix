# Cron WAV PCM Float Fast Path

## Goal

Reduce redundant per-sample work in the MLX audio WAV PCM streaming path by preserving already-float sample values from `iter_samples(...)` instead of calling `float(...)` again for every float value in nested lists, tuples, and flat array-like segments.

## Touched files

- `services/mlx-worker-python/worker/runtime/wav_helpers.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`

## Linux-only constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing MLX audio WAV PR-scoped performance probe.

## Performance probe

Registered probe: `mlx-audio-wav-streaming-pcm`

Local probe command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/mlx_audio_wav_streaming_probe.py
```

The probe builds a synthetic nested audio payload, converts it to WAV bytes repeatedly, and reports elapsed time, peak traced bytes, sample count, and output size.

## Success metrics

- Preserve WAV PCM output shape and clamping behavior.
- Add a focused regression test proving `iter_samples(...)` does not re-cast already-float sample values in nested and flat array-like inputs.
- Achieve at least 95% changed executable line coverage for the touched Python files.
- Keep the registered `mlx-audio-wav-streaming-pcm` probe green locally and in PR-scoped performance CI.
