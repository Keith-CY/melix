# Real model weight name prefilter

## Scope

This Python-only performance slice is limited to `scripts.real_model_support._has_recognized_model_weight_files()`.

The hot path validates local runtime model directories during real-model preflight. The common exact `model.safetensors` / `pytorch_model.bin` path already short-circuits before directory scanning. For noisy local model directories that contain many non-weight metadata files plus a later shard or uppercase weight file, the fallback scan still called `DirEntry.is_file()` for every entry before checking whether the filename could be a recognized weight artifact.

## Registered probe

The affected path is covered by the registered PR-scoped probe `real-model-support-hf-cache-latest-snapshot` in `infra/perf/pr_scoped_probes.json`. The probe watches `scripts/real_model_support.py`, `tests/test_real_model_support.py`, `scripts/real_model_support_hf_cache_probe.py`, and `services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and it includes focused `test_command`, `coverage_command`, and `probe_command` entries.

This slice keeps that registered probe unchanged for local Linux validation and CI merge gating. The probe's existing `weight_scan_elapsed_ms_mean` metric protects the common exact-file short-circuit from regression; this slice also records a local base-vs-head noisy-directory harness for the non-common shard-name scenario improved here.

## Change

Prefilter each scanned filename against the exact recognized weight names and supported weight suffixes before calling `DirEntry.is_file()`. This preserves the non-recursive behavior and the uppercase suffix fallback while avoiding stat calls for irrelevant directory entries.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_real_model_support.py::test_runtime_model_preflight_short_circuits_common_exact_weight_file tests/test_real_model_support.py::test_runtime_model_preflight_accepts_index_weight_files tests/test_real_model_support.py::test_has_recognized_model_weight_files_skips_path_iterdir tests/test_real_model_support.py::test_has_recognized_model_weight_files_preserves_uppercase_suffix_fallback tests/test_real_model_support.py::test_has_recognized_model_weight_files_prefilters_names_before_stat tests/test_real_model_support.py::test_has_recognized_model_weight_files_does_not_recurse_into_subdirectories services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_real_model_support_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_real_model_support_hf_cache_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_real_model_support.py::test_real_small_model_source_can_fallback_to_last_hf_cache_snapshot tests/test_real_model_support.py::test_real_small_model_source_fallback_tracks_latest_snapshot_without_sorting tests/test_real_model_support.py::test_hf_cache_snapshot_fallback_skips_stale_names_before_is_dir tests/test_real_model_support.py::test_hf_cache_snapshot_fallback_rescans_when_lexical_max_is_not_directory tests/test_real_model_support.py::test_hf_cache_snapshot_fallback_returns_none_for_empty_snapshots_dir tests/test_real_model_support.py::test_hf_cache_snapshot_fast_path_treats_stat_errors_as_not_directory tests/test_real_model_support.py::test_runtime_model_preflight_short_circuits_common_exact_weight_file tests/test_real_model_support.py::test_runtime_model_preflight_accepts_index_weight_files tests/test_real_model_support.py::test_has_recognized_model_weight_files_prefilters_names_before_stat services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_real_model_support_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_real_model_support_hf_cache_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/real_model_support.py tests/test_real_model_support.py scripts/real_model_support_hf_cache_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -c 'if [ -f scripts/real_model_support_hf_cache_probe.py ]; then python3 scripts/real_model_support_hf_cache_probe.py; fi'
```

GitHub Actions PR-scoped performance remains the merge gate after PR creation.
