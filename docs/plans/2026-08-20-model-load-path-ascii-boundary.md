# Model Load Path ASCII Boundary Fast Path

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/model_load_trust.py`, specifically the `_model_config_path()` boundary whitespace check used before resolving `config.json` for a model path.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. This slice extends that registry entry to watch this plan and include the new focused path-boundary tests in both the focused `test_command` and changed-scope `coverage_command`. The same entry already provides the local/CI `probe_command` via `scripts/model_load_config_json_bytes_probe.py`.

## Optimization

Plain absolute model paths are the common hot path during repeated trust-policy resolution. `_model_config_path()` previously called `str.isspace()` on both the first and last character for every non-empty plain string. This slice checks visible ASCII boundary characters first and returns the cached `config.json` path immediately for the common case, falling back to the existing Unicode-aware whitespace checks for non-ASCII, ASCII whitespace, blank, and padded paths.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, `git diff --check`, and the registered `model-load-config-json-bytes` probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Success Criteria

- Focused model-load trust and PR-scoped registry tests pass.
- Changed-scope coverage for touched Python/test/probe paths is at least 95%.
- The registered probe reports non-regression or improvement for `elapsed_ms_mean` and `executable_elapsed_ms_mean` with unchanged rejection counts.
