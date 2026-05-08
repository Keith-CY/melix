# Cron WAV PCM Recast Elision

## Goal

Reduce redundant per-sample work in the MLX audio WAV PCM streaming path by avoiding an extra `float(...)` conversion after `iter_samples(...)` has already normalized values to floats.

## Touched files

- `services/mlx-worker-python/worker/runtime/wav_helpers.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`

## Linux-only constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing MLX audio WAV PR-scoped performance probe.

## Performance probe

Registered probe: `mlx-audio-wav-streaming-pcm`

Local probe command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/mlx_audio_wav_streaming_probe.py
```

The probe builds a synthetic nested audio payload, converts it to WAV bytes repeatedly, and reports elapsed time, peak traced bytes, sample count, and output size.

## Success metrics

- Preserve WAV PCM output shape and clamping behavior.
- Add a focused regression test proving `audio_to_pcm_chunks(...)` does not re-cast the already-normalized values yielded by `iter_samples(...)`.
- Achieve at least 95% changed executable line coverage for the touched Python files.
- Keep the registered `mlx-audio-wav-streaming-pcm` probe green locally and in PR-scoped performance CI.
