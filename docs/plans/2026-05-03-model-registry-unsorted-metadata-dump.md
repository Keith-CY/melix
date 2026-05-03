# Model registry unsorted metadata signal dump performance slice

## Goal

Reduce Python CPU overhead in plain-local model registry scans by avoiding deterministic key sorting when converting already-loaded metadata payloads into text for MLX-signal detection.

## Scope

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This slice is Python-only under `services/mlx-worker-python`, so it is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Optimization Hypothesis

`_metadata_payload_has_mlx_signal()` only searches the serialized metadata text for MLX marker substrings. The order of JSON object keys is irrelevant for that predicate, but `json.dumps(..., sort_keys=True)` sorts every mapping. Removing key sorting preserves the signal predicate while reducing per-model serialization work in registry scans that pass non-empty `config.json` payloads.

## Registered Probe

The affected path is covered by `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values and measures:

- `elapsed_ms_mean` (lower is better)
- `manifest_is_file_calls_mean` (lower is better; must remain `0.0`)
- `config_load_calls_mean` (lower is better; expected unchanged for this slice)

This slice also registers the new regression test in the probe commands so changed-scope coverage includes the no-sort assertion.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_plain_local_tree_scan_and_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_reuses_hf_cache_config_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_empty_supplied_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_skips_config_text_fallback_for_nonempty_payload_without_mlx_signal \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_has_mlx_signal_falls_back_to_config_text_for_unserializable_nonempty_payload \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_does_not_sort_keys \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_does_not_stat_plain_local_manifest_after_tree_scan \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_load_json_dict_file_reads_json_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused node list>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_registry/catalog.py \
  services/mlx-worker-python/tests/test_model_registry_catalog.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id model-registry-plain-local-manifest-stat-elision \
  --base-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-base-model-registry-unsorted-metadata-dump-20260503015724 \
  --head-repo "$PWD" \
  --output /tmp/model_registry_unsorted_metadata_probe.json

git diff --check
```

## Success Criteria

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- Local registered probe shows lower or non-regressing `elapsed_ms_mean` with `manifest_is_file_calls_mean == 0.0` and unchanged config-load count.
- PR-scoped performance CI completes successfully before merge.

## Local Probe Evidence

Three local registered probe runs against `origin/main` showed an aggregate improvement while preserving `manifest_is_file_calls_mean == 0.0` and `config_load_calls_mean == 800.0`:

| Run | base `elapsed_ms_mean` | head `elapsed_ms_mean` | delta | speedup |
| --- | ---: | ---: | ---: | ---: |
| 1 | 228.824186 | 235.176033 | +6.351847 | 0.973x |
| 2 | 239.991061 | 230.322020 | -9.669041 | 1.042x |
| 3 | 223.144575 | 212.034061 | -11.110514 | 1.052x |

Aggregate mean: base `230.653274 ms`, head `225.844038 ms`, delta `-4.809236 ms`, speedup `1.021x`.
