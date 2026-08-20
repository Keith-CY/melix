# Model Load Config No-Auto-Map JSON Skip

## Scope

This Python-only performance slice is limited to model-load trust detection in
`services/mlx-worker-python/worker/model_load_trust.py`.

The custom-loader detector now scans the raw `config.json` bytes for the common
`"auto_map"` key before decoding JSON on the trust-detection hot path. Valid
configs without `auto_map` keep the existing `config_json` detection source while
avoiding a full JSON decode before executable model-file scanning. Configs that
contain `auto_map` continue through the existing JSON parser and custom-loader
value checks.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry
entry includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/model_load_trust.py`
- `services/mlx-worker-python/tests/test_model_load_trust.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_load_config_json_bytes_probe.py`

The probe reports both `config.json` auto-map detection metrics and the
executable-file fallback metrics (`executable_elapsed_ms_mean`,
`executable_peak_bytes_mean`). The 2026-08-20 follow-up slice keeps the detector
semantics unchanged and only binds the rejection policy `CopyFrom` method at the
call site so cached template copies avoid a repeated bound-method lookup during
custom-loader rejection loops.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `model-load-config-json-bytes` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.
