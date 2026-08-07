# Audio local URI basename rfind slice

This Python-only performance slice is limited to the local audio URI transcription path through `worker.runtime.audio_preprocessing.prepare_audio_input()` and `worker.runtime.mlx_audio_runtime.MLXAudioTranscriptionRuntime.transcribe()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `mlx-audio-local-uri-zero-copy-preprocess` in `infra/perf/pr_scoped_probes.json`.

The probe already watches:

- `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- focused audio runtime tests
- `scripts/mlx_audio_local_uri_probe.py`

This slice extends the registered focused test and coverage commands with a regression test proving filename derivation does not call `os.path.basename()`.

## Optimization

`prepare_audio_input()` already keeps the transcription runtime zero-copy for local audio URIs by passing the resolved path to the backend and using one `os.stat()` call for byte accounting. The remaining filename derivation used `os.path.basename(local_path)` on every URI request when no media filename was provided.

This slice replaces that call with a local `str.rfind(os.sep)` helper, matching the existing suffix fast path and avoiding the generic `os.path` basename dispatch on the hot local URI path. Behavior remains unchanged for POSIX paths, including no separator and trailing-separator inputs.

The same hot transcription path also binds the backend `generate` callable and request language once before entering the execution gate, avoiding repeated protobuf and model attribute lookups while preserving the existing kwargs and language fallback behavior.

## Verification plan

1. Run the new regression test and the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered local probe before and after the implementation and compare `elapsed_ms_mean`, `local_uri_read_bytes_calls_mean`, and `peak_bytes_mean`.
4. Use the PR-scoped performance GitHub Actions report as the merge gate.
