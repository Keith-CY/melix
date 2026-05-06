# MLX Audio Speech Signature Cache Optimization

## Goal

Reduce repeated per-request `inspect.signature(...)` work in the MLX audio TTS speech runtime by caching the `generate(...)` parameter names when the model is loaded.

## Linux-only constraint

This is a Python-only worker runtime change. It can be verified on Linux with fake `mlx_audio` modules, focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/audio_runtime_protocols.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_audio_speech_signature_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Registered probe: `mlx-audio-speech-signature-cache`.

The probe installs a fake MLX audio TTS backend, tracks calls to `worker.runtime.mlx_audio_runtime.signature`, loads one model, and runs repeated `speak(...)` calls. The structural success metric is `inspect_signature_calls_mean` dropping from per-request behavior on `origin/main` to one load-time call on the optimized branch.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Local probe emits concrete `elapsed_ms_mean`, `inspect_signature_calls_mean`, and workload size metrics.
- PR-scoped performance CI selects and runs `mlx-audio-speech-signature-cache`.
