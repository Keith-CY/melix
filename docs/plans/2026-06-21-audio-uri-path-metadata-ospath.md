# Audio URI Path Metadata Ospath Slice

## Objective

Reduce small but repeated path metadata overhead in the MLX audio local-URI
preprocessing hot path. The transcription runtime already avoids reading local
`audio_uri` bytes before handing the filesystem path to the STT backend; this
slice keeps that behavior and avoids extra `Path` property parsing when filling
`PreparedAudioInput.local_path`, `format`, and `filename`.

## Scope

- Affected code path: `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`.
- Registered PR-scoped probe: `mlx-audio-local-uri-zero-copy-preprocess`.
- Probe coverage: focused test, coverage, and command-json probe entries already
  exist in `infra/perf/pr_scoped_probes.json`.

## Implementation

Use the filesystem string produced by `os.fspath(path)` as the single source for
local URI metadata in `prepare_audio_input(...)`, then derive optional suffix and
basename through `os.path.splitext(...)` and `os.path.basename(...)`. This keeps
`_path_from_uri(...)` semantics unchanged and preserves the existing local URI
zero-copy contract.

## Verification Plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_zero_copy_uri_skips_exists_probe \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_prepared_input_uses_slots \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_rejects_missing_and_unsupported_inputs \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_mlx_audio_transcription_runtime_uses_local_uri_path_without_reading_bytes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_audio_local_uri_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_audio_local_uri_probe_script_emits_metrics
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_zero_copy_uri_skips_exists_probe \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_prepared_input_uses_slots \
  services/mlx-worker-python/tests/test_audio_runtime.py::test_audio_preprocessing_rejects_missing_and_unsupported_inputs \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py::test_mlx_audio_transcription_runtime_uses_local_uri_path_without_reading_bytes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_mlx_audio_local_uri_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_mlx_audio_local_uri_probe_script_emits_metrics && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/audio_preprocessing.py \
  services/mlx-worker-python/tests/test_mlx_audio_runtime.py \
  services/mlx-worker-python/tests/test_audio_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/mlx_audio_local_uri_probe.py
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/mlx_audio_local_uri_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id mlx-audio-local-uri-zero-copy-preprocess \
  --base-repo /root/.hermes/profiles/coder/workspace/melix \
  --head-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-audio-uri-path-metadata-ospath-20260621 \
  --output /tmp/mlx-audio-uri-path-metadata-probe.json
```
