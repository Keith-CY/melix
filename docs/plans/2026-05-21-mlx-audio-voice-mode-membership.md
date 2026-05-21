# MLX audio voice mode direct comparison fast path

## Scope

This Python-only performance slice targets the per-request MLX audio TTS speech
keyword path in `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`.
The behavior remains unchanged: `hybrid` and `named` voice modes accept a voice
argument, while instructional/plain modes do not.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`mlx-audio-generate-signature-cache` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values, and watches `mlx_audio_runtime.py`, the audio runtime
protocols, focused tests, and `scripts/mlx_audio_generate_signature_probe.py`.

## Optimization

Avoid constructing a short set literal on every `_speech_generation_kwargs(...)`
call by resolving `loaded_model.voice_mode` once and using direct string
comparisons for the two supported voice modes. The change keeps the hot path
local to one attribute read plus direct comparisons and does not change signature
fallback behavior.

## Verification plan

- Run the registered focused test command for `mlx-audio-generate-signature-cache`.
- Run the registered changed-scope coverage command and require at least 95% for
  the changed scope.
- Run the registered probe locally on Linux before and after the change with the
  same workload and compare `elapsed_ms_mean`; `signature_calls_mean` must remain
  `0.0` for the cached loaded-model path.
- GitHub Actions PR-scoped performance must select and complete the registered
  probe before merge.

## Environment boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime
performance claim is made.
