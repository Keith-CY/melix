# MLX Audio PCM Float Conversion Elision

## Goal

Reduce per-sample Python work in the MLX audio WAV PCM conversion path by fast-pathing numeric list/tuple items in `iter_samples` before slower array-like introspection and by avoiding a redundant `float(...)` conversion inside `audio_to_pcm_chunks` after `iter_samples` has already normalized every yielded sample to `float`.

## Scope

This slice is limited to:

- `services/mlx-worker-python/worker/runtime/wav_helpers.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `infra/perf/pr_scoped_probes.json`
- this plan document

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `mlx-audio-wav-streaming-pcm` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches `wav_helpers.py`, `mlx_audio_runtime.py`, focused tests, and the checked-in probe script.

This slice also updates the probe's `coverage_command` and checked-in `probe_command` launcher to use `python3` so scheduled Linux validation follows the current operator requirement.

## Expected behavior

No audio semantics change. `iter_samples` remains responsible for flattening array-like, list, tuple, and scalar inputs and for yielding floats; `audio_to_pcm_chunks` clamps those already-normalized floats and writes little-endian 16-bit PCM chunks.

## Validation plan

- Focused pytest for the WAV conversion and PR-scoped probe selection tests.
- Changed-scope coverage for the touched Python files.
- Local Linux registered probe comparison with `scripts/pr_scoped_performance_run.py` against a detached `origin/main` baseline worktree.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Registered probe reports unchanged WAV byte size and non-regressing peak memory; elapsed time is informational for this probe.
