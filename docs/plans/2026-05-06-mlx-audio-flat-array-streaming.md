# MLX Audio Flat Array Streaming Plan

## Context

This Linux-verifiable Python slice targets `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`.
The WAV encoder already writes PCM frames in bounded chunks, but `_iter_samples(...)` still calls
`tolist()` before iteration for array-like audio payloads. NumPy/MLX-style arrays commonly expose a
`.flat` iterator that can stream samples without materializing a full Python list first.

## Proposed Change

- Prefer a `.flat` iterator for non-list/tuple array-like audio payloads before falling back to
  `tolist()`.
- Preserve scalar, nested `list`/`tuple`, and legacy `tolist()` behavior.
- Extend the focused WAV streaming test to assert flat array-like inputs do not call `tolist()`.
- Update the existing `mlx-audio-wav-streaming-pcm` probe script workload so branch-side probe runs
  exercise the `.flat` streaming path while retaining the existing metrics contract.

## Verification Plan

- Focused pytest:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_streams_nested_samples_and_clamps_values services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_does_not_materialize_flat_sample_list services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_audio_to_wav_bytes_writes_little_endian_chunks_on_big_endian_hosts services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_audio_wav_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_audio_wav_streaming_probe_script_emits_metrics`
- Changed-scope coverage with the registered `mlx-audio-wav-streaming-pcm` coverage command.
- Local performance probe:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/mlx_audio_wav_streaming_probe.py`
- Diff hygiene: `git diff --check`.

## Success Metrics

- Changed executable scope coverage is at least 95%.
- The `mlx-audio-wav-streaming-pcm` local probe emits concrete `elapsed_ms_mean` and
  `peak_bytes_mean` numbers without changing WAV byte size or sample count.
- Hosted PR-scoped performance CI validates the registered `mlx-audio-wav-streaming-pcm` probe before merge.
