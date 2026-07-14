# Audio file URI direct fast path performance slice

## Scope

This Python-only performance slice is limited to `worker.runtime.audio_preprocessing._path_from_uri` for the common local `file:///...` audio URI path used before MLX audio transcription.

The behavior stays equivalent for local file URIs, `file://localhost/...` URIs, remote-authority file URIs, plain local paths, percent-encoded paths, and unsupported non-file schemes. The change adds an earlier direct branch for already-absolute `file:///` URIs and lets the zero-copy size probe use the decoded local path string directly, avoiding the extra localhost/authority branch checks, `Path` construction, and `Path.stat()` method dispatch on the hot path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `mlx-audio-local-uri-zero-copy-preprocess` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/audio_preprocessing.py`
- `services/mlx-worker-python/worker/runtime/mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_audio_runtime.py`
- `services/mlx-worker-python/tests/test_mlx_audio_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_audio_local_uri_probe.py`

This slice extends the registered focused test command with a regression assertion that `file:///` preprocessing does not call `urlparse`.

## Validation plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`, and the registered local probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
