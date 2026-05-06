# MLX Audio Speech Signature Elision

## Goal

Reduce redundant reflection in the MLX audio speech runtime by reusing the speech model capability metadata already computed during `load_model()` instead of calling `inspect.signature(...)` on every `speak(...)` request.

## Touched Files

- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `scripts/mlx_audio_speech_signature_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux-Only Constraint

This slice is Python-only and uses fake MLX audio modules/models in focused tests and probes, so it can be verified on Linux without the macOS/Swift runtime surfaces.

## Performance Probe Definition

Register `mlx-audio-speech-signature-elision` in the PR-scoped performance registry. The probe runs a synthetic speech workload against `MLXAudioSpeechRuntime.speak(...)` and reports:

- `elapsed_ms_mean`
- `inspect_signature_calls_mean`
- `speak_call_count`
- `output_bytes_total`

## Success Metrics

- Preserve voice/instruction mapping semantics.
- Drive per-request speech signature calls to `0` on the optimized branch after model load.
- Improve or maintain elapsed runtime for repeated synthetic `speak(...)` calls.
- Maintain at least 95% changed-scope automated coverage.

## Verification Commands

- Focused pytest for MLX audio runtime and PR-scoped probe registry tests.
- Changed-scope coverage via `coverage json` plus `scripts/changed_scope_coverage.py`.
- Local explicit performance probe via `scripts/mlx_audio_speech_signature_probe.py` and registered PR-scoped performance runner.
- `git diff --check`.
