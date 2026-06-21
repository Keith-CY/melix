# Model load config path stat performance slice

## Scope

This Python-only performance slice is limited to `worker.model_load_trust._read_model_config()` in `services/mlx-worker-python/worker/model_load_trust.py`.

## Change

`resolve_model_load_trust_policy(...)` consults `_read_model_config()` for applicable text/VLM model loads. The previous plain-path flow built `Path(model_path) / "config.json"` and then called `Path.stat()` before passing the string path into the cached JSON reader.

This slice keeps the tilde expansion behavior unchanged, but lets the common plain-path case build the `config.json` path as a string and call `os.stat(...)` directly. That avoids per-resolution `Path` construction and `Path.__truediv__` overhead on the hot path while preserving the same file-type check, cache key, missing-file handling, and JSON byte loading behavior.

## Probe coverage

The affected path is covered by the registered PR-scoped probe `Model load config JSON bytes` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` commands for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Local validation plan

Run on Linux:

1. Focused model-load trust tests.
2. Registered changed-scope coverage command for the `Model load config JSON bytes` probe.
3. Registered probe command with repeated samples and the same iteration count before/after the implementation.

## Expected effect

The slice removes plain-path `Path` object construction from each model-load trust config lookup before the cached config JSON reader. Accept only if the registered probe shows directionally better elapsed-time metrics without behavior drift.
