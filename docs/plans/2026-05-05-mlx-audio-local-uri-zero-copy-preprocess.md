# MLX Audio Local URI Zero-Copy Preprocess

## Goal

Reduce redundant memory work in MLX audio transcription for local `audio_uri` inputs. The MLX STT backend consumes a local filesystem path, so the runtime does not need to read the entire file into memory before calling `generate(audio_path, ...)`.

## Scope

- `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_audio_local_uri_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Verification Path

- Focused pytest for MLX audio runtime and PR-scoped performance probe wiring.
- Changed-scope coverage using `scripts/changed_scope_coverage.py`, requiring at least 95% coverage for touched executable lines.
- Local performance probe comparing `origin/main` and the branch through the registered `mlx-audio-local-uri-zero-copy-preprocess` command-json probe.

## Success Metrics

- Preserve transcription behavior for local URI inputs.
- Avoid `Path.read_bytes()` on the MLX local URI transcription path.
- Reduce `preprocess_peak_memory_bytes_mean` and `preprocess_elapsed_ms_mean` in the synthetic local-URI probe.
- Keep deterministic/default audio preprocessing behavior unchanged for callers that still need decoded bytes.
