# Audio Local URI Exists Elision

## Goal

Avoid redundant `Path.exists()` filesystem metadata probes while preprocessing local audio URIs. The hot zero-copy transcription path already performs the necessary `Path.stat()` call to capture byte size, and the read-bytes path already surfaces missing files through `Path.read_bytes()`.

## Touched files

- `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`
- `services/mlx-worker-python/tests/test_audio_runtime.py`
- `scripts/mlx_audio_local_uri_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker slice and can be locally verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance probe

Use the existing `mlx-audio-local-uri-zero-copy-preprocess` probe. Extend its checked-in script to report `local_uri_exists_calls_mean` so the optimization has a structural metric in addition to elapsed time and peak memory.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python files.
- Branch-side local probe reports:
  - `local_uri_read_bytes_calls_mean == 0.0`
  - `local_uri_exists_calls_mean == 0.0`
- Existing probe remains selected by the touched files and remains base-compatible for hosted PR-scoped performance CI.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_zero_copy_uri_skips_exists_probe \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_rejects_missing_and_unsupported_inputs \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_mlx_audio_transcription_runtime_uses_local_uri_path_without_reading_bytes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_audio_local_uri_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_audio_local_uri_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_audio_local_uri_probe_script_main_covers_checked_in_file

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ...
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json ...
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/mlx_audio_local_uri_probe.py
python scripts/pr_scoped_performance_run.py --probe-id mlx-audio-local-uri-zero-copy-preprocess --base-ref origin/main --head-ref HEAD --output /tmp/mlx-audio-local-uri-probe.json
```
