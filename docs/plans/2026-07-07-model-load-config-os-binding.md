# Model Load Config OS Binding Performance Slice

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py` and the repeated model-load trust policy path that probes `config.json` for custom loader metadata.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for `model_load_trust.py`, `test_model_load_trust.py`, `test_pr_scoped_performance.py`, and `scripts/model_load_config_json_bytes_probe.py`.

## Optimization

Bind the hot OS and stat helpers used by the repeated config probe path at module import time:

- `os.stat` -> `_OS_STAT`
- `os.scandir` -> `_OS_SCANDIR`
- `stat.S_ISREG` -> `_STAT_ISREG`

This keeps trust-policy semantics unchanged while avoiding repeated global attribute resolution in the hot config stat and executable-file fallback paths.

## Verification Plan

Run locally on Linux before PR:

1. Focused model-load trust tests and PR-scoped performance probe dispatch tests.
2. Changed-scope coverage using the registered coverage command for `model-load-config-json-bytes`.
3. Registered probe locally with `scripts/model_load_config_json_bytes_probe.py`.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
