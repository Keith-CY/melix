# Model registry README quoted base_model fast-path slice

This Python-only performance slice is limited to `worker.model_registry.catalog._gemma4_qat_source_model`.

## Scope

Gemma 4 QAT model classification scans README/model-card text for a YAML `base_model:` marker. The current fast path already avoids materializing all README lines. This slice keeps behavior unchanged while adding a direct scan for the common quoted model-card form (`\n  'base_model:`), so matching README cards can parse the value without the generic candidate-prefix validation loop.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `model-registry-readme-source-fastpath` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches:

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/model_registry_readme_source_probe.py`

## Verification plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_gemma4_qat_source_model_rejects_non_marker_prefix_without_prefix_strip services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_direct_mlx_signal_accepts_exact_and_normalized_values services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_skips_json_for_direct_metadata services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_payload_has_mlx_signal_does_not_request_sorted_json services/mlx-worker-python/tests/test_model_registry_catalog.py::test_metadata_text_has_mlx_signal_short_circuits_negative_metadata services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_gemma4_qat_source_model_rejects_non_marker_prefix_without_prefix_strip services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_marks_gemma4_qat_assistant_as_draft_companion services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_root_tree_records_plain_local_weight_presence_during_single_scandir_pass services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_registry_readme_source_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/model_registry_readme_source_probe.py
```

GitHub Actions PR-scoped performance remains the final merge gate.
