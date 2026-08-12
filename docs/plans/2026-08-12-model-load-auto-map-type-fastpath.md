# Model load auto_map exact string fast path

## Scope

This Python-only performance slice is limited to custom-loader detection in
`services/mlx-worker-python/worker/model_load_trust.py`, specifically the
`_auto_map_has_custom_loader()` loop used while resolving model-load trust
policy from `config.json` `auto_map` metadata.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The entry
has focused `test_command`, `coverage_command`, and `probe_command` entries for
`model_load_trust.py`, focused model-load trust tests, PR-scoped performance
registry tests, and `scripts/model_load_config_json_bytes_probe.py`.

## Optimization

Common Hugging Face `auto_map` payloads decode JSON string values as exact
builtin `str` objects. This slice adds an exact-type fast path before the
subclass-preserving `isinstance(value, str)` branch. Behavior remains unchanged:
blank strings remain non-custom, nonblank strings still require trust, and
non-string values keep the existing fallback coercion.

## Verification plan

Run on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_builtin_string_skips_isinstance_dispatch services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_custom_loader_scan_preserves_blank_string_behavior services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_load_config_json_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_load_config_json_bytes_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_builtin_string_skips_isinstance_dispatch services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_common_string_uses_leading_character_fast_path services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_custom_loader_scan_preserves_blank_string_behavior services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_auto_map_custom_loader_scan_preserves_non_string_fallback services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_load_config_json_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_load_config_json_bytes_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_load_trust.py services/mlx-worker-python/tests/test_model_load_trust.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_load_config_json_bytes_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-load-config-json-bytes --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/model_load_auto_map_type_fastpath_probe.json
```

GitHub Actions PR-scoped performance remains the registered probe merge gate.

## Success criteria

- Focused behavior and probe-registry tests pass.
- Changed-scope coverage for touched Python/test/probe paths is at least 95%.
- The registered probe reports non-regression or improvement for
  `elapsed_ms_mean` / `executable_elapsed_ms_mean` with unchanged rejection
  counts.
