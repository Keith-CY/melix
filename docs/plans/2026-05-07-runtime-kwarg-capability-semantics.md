# Runtime Kwarg Capability Semantics

## Goal

Make runtime callable kwarg checks explicit enough to preserve hot-path signature caching without conflating two different semantics:

- a callable explicitly declares a keyword parameter
- a callable can accept arbitrary `**kwargs`

## Scope

Touched files:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/worker/runtime/mlx_text_runtime.py`
- `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_mlx_backend.py`
- `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_text_stop_kwarg_signature_probe.py`
- `scripts/mlx_audio_generate_signature_probe.py`
- `scripts/mlx_audio_speech_signature_probe.py`

## Design

`worker.runtime.runtime_utils` owns a single cached callable kwarg capability analysis result. Runtime callers choose between:

- `callable_declares_kwarg(...)` when a backend library must explicitly declare a keyword-accessible parameter.
- `callable_accepts_kwarg(...)` when forwarding to an adapter that safely accepts arbitrary `**kwargs`.

Text stop-sequence forwarding, VLM MTP/video capability detection, and audio speech parameter detection use the explicit-declaration path. Engine/runtime adapter optional arguments keep using the accept-any-kwargs path.

## Performance Probes

Existing scoped probes remain authoritative:

- `runtime-utils-kwarg-signature-cache`
- `mlx-text-stop-kwarg-signature-cache`
- `mlx-audio-generate-signature-cache`
- `mlx-audio-speech-signature-cache`

## Success Metrics

- `make py-test` passes on `origin/main` plus this fix.
- Focused runtime utility, text backend, VLM backend, and audio runtime tests pass.
- Signature inspections remain cached per callable instead of per generation/speech request.
- Variadic `**kwargs` backends are not treated as explicitly supporting backend-specific kwargs such as text `stop`, VLM `video`, or MTP `draft_*` arguments.
