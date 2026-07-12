# Model load executable file scan single-sort fast path

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py` and the fallback scan that checks top-level model bundle files for executable custom-loader modules after `config.json` does not request a custom loader.

## Probe Coverage

The affected path is already covered by the registered PR-scoped performance probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

## Plan

1. Add a focused regression test proving the common single executable-loader file path does not call `sorted(...)` while preserving the public detection source.
2. Replace the eager `tuple(sorted(...))` generator in `_detect_executable_model_files(...)` with a single pass that sorts only when more than one executable loader file is present.
3. Run the registered focused tests, changed-scope coverage, and registered local probe on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Validation Notes

Local Linux validation covers the Python implementation and registered Python probe. No Swift runtime effect is claimed for this slice.
