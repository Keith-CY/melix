# Model registry README source fast path slice

This Python performance slice is limited to Gemma 4 QAT README metadata parsing in
`worker.model_registry.catalog._gemma4_qat_source_model(...)`.

## Registered probe

The affected path is covered by the PR-scoped registered probe
`model-registry-readme-source-fastpath` in `infra/perf/pr_scoped_probes.json`.
The probe watches the model registry catalog, the focused tests, this probe
script, and the registry entry. It includes focused `test_command`,
`coverage_command`, and `probe_command` entries.

The probe compares the previous `readme_text.splitlines()` scan with the new
bounded `str.find()` scan against a large synthetic model card with a late
`base_model:` declaration. It reports old/new elapsed means, peak bytes, delta,
and speedup.

## Implementation plan

1. Preserve README parsing behavior for leading whitespace and quote-wrapped
   `base_model:` lines while ignoring embedded non-line-start occurrences.
2. Avoid materializing all README lines before finding the declaration.
3. Add focused regression coverage and a registered command-json probe.
4. Run the registered local test, changed-scope coverage, and probe on Linux;
   GitHub PR-scoped performance remains the merge gate.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_marks_gemma4_qat_assistant_as_draft_companion services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_marks_gemma4_qat_assistant_as_draft_companion services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_registry_readme_source_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/model_registry_readme_source_probe.py
```
