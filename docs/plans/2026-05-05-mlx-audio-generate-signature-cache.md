# MLX Audio Generate Signature Cache Plan

## Goal

Avoid repeated `inspect.signature(...)` calls on the MLX audio TTS `generate` method for every `speak(...)` request. The generate signature is stable for a loaded model, so the runtime can cache the parameter names at `load_model(...)` time and reuse them during request dispatch.

## Touched Files

- `services/mlx-worker-python/worker/runtime/audio_runtime_protocols.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_audio_generate_signature_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-Only Constraint

This is a Python-only runtime slice and is verified on Linux with fake MLX audio model objects. It does not require the macOS/Swift surfaces or real MLX audio packages.

## Performance Probe

Registered PR-scoped probe: `mlx-audio-generate-signature-cache`.

The probe runs repeated `MLXAudioSpeechRuntime.speak(...)` calls against a fake TTS model while wrapping `worker.runtime.mlx_audio_runtime.signature` to count per-request signature introspection calls.

## Success Metrics

- `signature_calls_mean` should drop to `0.0` during the repeated `speak(...)` loop on the optimized branch.
- `elapsed_ms_mean` is recorded as informational because the structural reflection-call metric is the stable signal for this tiny Python hot path.
- Focused tests and changed-scope coverage must pass with at least 95% coverage for changed executable lines.

## Verification Commands

- Focused pytest for MLX audio and PR-scoped probe tests.
- Changed-scope coverage over the touched Python/test/script files.
- Local run of `scripts/mlx_audio_generate_signature_probe.py`.
- `git diff --check`.
