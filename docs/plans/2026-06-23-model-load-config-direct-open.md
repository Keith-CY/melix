# Model load config direct open slice

This Python-only performance slice is limited to `worker.model_load_trust._read_model_config_for_stat()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Slice

`_read_model_config_for_stat()` currently materializes a `Path` object only to call `read_bytes()` for the already-normalized `config.json` path. This slice removes that per-cache-miss `Path` construction and reads the JSON payload through direct binary `open()`.

## Verification plan

1. Add/keep a focused regression guard proving the config reader uses direct binary `open()` for the read path and does not fall back to `Path.read_bytes()` or text decoding.
2. Run the registered test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux and require changed-scope coverage to remain at or above 95%.
4. Run the registered probe locally against `origin/main` and this branch with `scripts/pr_scoped_performance_run.py`.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Success criteria

- Behavior remains unchanged for valid, invalid, missing, and non-dict `config.json` payloads.
- The registered probe shows lower `elapsed_ms_mean` or an equivalent positive metric without coverage regression.
- CI PR-scoped performance completes successfully before merge.
