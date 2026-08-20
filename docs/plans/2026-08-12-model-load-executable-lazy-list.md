# Model load executable-file single-match list elision

## Scope

This Python-only performance slice is limited to executable model-file detection
in `services/mlx-worker-python/worker/model_load_trust.py`, specifically the
`_detect_executable_model_files_for_stat()` scan used after `config.json` does
not require `trust_remote_code`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
has focused `test_command`, `coverage_command`, and `probe_command` entries for
`model_load_trust.py`, focused model-load trust tests, PR-scoped performance
registry tests, and `scripts/model_load_config_json_bytes_probe.py`.

This slice extends the registered metrics with
`executable_single_file_list_allocations_mean` so CI keeps checking that the
single executable-file case remains allocation-free for the temporary list used
only by multi-file sorting.

## Optimization

Most unsafe model-file detections stop at one executable Python file such as
`configuration_*.py` or `modeling_*.py`. The previous implementation allocated a
list for every scan even when there were zero or one matching files. This slice
keeps the first matching filename in a scalar and creates the list only when a
second matching executable file appears and sorting is required.

Behavior remains unchanged: no match returns an empty tuple, one match returns a
single-item tuple, and multiple matches still return sorted filenames.

2026-08-20 follow-up slice: keep the same registered probe and executable scan
path, but reject filenames whose first character cannot match an executable
model-file prefix before checking the `.py` suffix. Large model directories often
contain many Python adapter/helpers whose first character is outside the trusted
prefix set, so the scan avoids a suffix slice for those distractors while still
statting only names that pass the prefix and suffix guards.

## Verification plan

Run on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_single_executable_model_file_avoids_list_allocation services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_multiple_executable_model_files_stay_sorted services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_caches_executable_model_files_by_directory_stat services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_load_config_json_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_load_config_json_bytes_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_single_executable_model_file_avoids_list_allocation services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_multiple_executable_model_files_stay_sorted services/mlx-worker-python/tests/test_model_load_trust.py::test_trust_policy_caches_executable_model_files_by_directory_stat services/mlx-worker-python/tests/test_model_load_trust.py::test_worker_rejects_custom_loader_metadata_without_explicit_trust services/mlx-worker-python/tests/test_model_load_trust.py::test_worker_trusted_custom_loader_receipt_passes_trust_remote_code services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_load_config_json_bytes_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_load_config_json_bytes_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_load_trust.py services/mlx-worker-python/tests/test_model_load_trust.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_load_config_json_bytes_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-load-config-json-bytes --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/model_load_executable_lazy_list_probe.json
```

GitHub Actions PR-scoped performance remains the registered probe merge gate.

## Success criteria

- Focused behavior and probe-registry tests pass.
- Changed-scope coverage for touched Python/test/probe paths is at least 95%.
- The registered probe reports non-regression or improvement for
  `executable_elapsed_ms_mean` / `executable_peak_bytes_mean` with unchanged
  rejection counts and zero `executable_single_file_list_allocations_mean`.
