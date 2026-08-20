# Model Load Auto-Map ASCII First-Character Fast Path

## Scope

This Python-only performance slice is limited to custom-loader detection in
`services/mlx-worker-python/worker/model_load_trust.py`, specifically the
`_auto_map_has_custom_loader()` loop used after `config.json` `auto_map` metadata
has been decoded.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The registry
entry has focused `test_command`, `coverage_command`, and `probe_command` entries
for `model_load_trust.py`, focused model-load trust tests, PR-scoped performance
registry tests, and `scripts/model_load_config_json_bytes_probe.py`.

## Optimization

Common `auto_map` custom loader entries start with visible ASCII characters such
as `c` in `custom.Loader`. The detector now checks `value[0] > " "` before the
existing Unicode-aware whitespace checks. This avoids a `str.isspace()` call for
that common ASCII path while preserving blank, ASCII-whitespace-only, and
Unicode-whitespace-only behavior through the existing fallback.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, `git diff --check`,
and the registered `model-load-config-json-bytes` probe locally on Linux before
opening the PR. GitHub Actions PR-scoped performance remains the merge gate for
the registered probe report.

## Success Criteria

- Focused model-load trust and PR-scoped probe tests pass.
- Changed-scope coverage for touched Python/test/probe paths is at least 95%.
- The registered probe reports non-regression or improvement for
  `elapsed_ms_mean` with unchanged rejection counts.
