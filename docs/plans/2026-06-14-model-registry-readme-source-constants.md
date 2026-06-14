# Model Registry README Source Constant Fast Path

This Python performance slice narrows the Gemma 4 QAT README `base_model:` source parser in `worker.model_registry.catalog._gemma4_qat_source_model()`.

## Scope

- Hoist repeated parser constants used by the `base_model:` scan.
- Replace the two-step value strip with a single equivalent strip character set.
- Reuse the module-level Gemma 4 QAT size map for the fallback source model string.

No model registry behavior changes are intended.

## Registered probe

The affected path is covered by the existing PR-scoped probe `model-registry-readme-source-fastpath` in `infra/perf/pr_scoped_probes.json`.

The registered entry includes focused `test_command`, `coverage_command`, and `probe_command` fields. Its `scripts/model_registry_readme_source_probe.py` workload compares the legacy line-splitting parser with the current parser on a synthetic README where `base_model:` appears after 5,000 metadata lines.

## Verification plan

Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_marks_gemma4_qat_assistant_as_draft_companion services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_raw_model_spec_loads_config_payload_when_not_supplied services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_keeps_gemma4_qat_target_when_readme_mentions_assistant services/mlx-worker-python/tests/test_model_registry_catalog.py::test_registry_snapshot_marks_gemma4_qat_assistant_as_draft_companion services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_model_registry_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_readme_source_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_registry_readme_source_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -c 'if [ -f scripts/model_registry_readme_source_probe.py ]; then python3 scripts/model_registry_readme_source_probe.py; else for PREFIX in "${MELIX_MODEL_REGISTRY_README_SOURCE_HEAD_REPO:-}" "${GITHUB_WORKSPACE:-}/head" "../head"; do CANDIDATE="$PREFIX/scripts/model_registry_readme_source_probe.py"; if [ -f "$CANDIDATE" ]; then python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for scripts/model_registry_readme_source_probe.py" >&2; exit 2; fi'
```

CI remains the merge gate for the registered PR-scoped performance report. The probe gates `new_elapsed_ms_mean` and `new_peak_bytes_mean`; `delta_ms` and `speedup` are informational because they incorporate the probe's in-run legacy helper timing, so base/head noise in the legacy side can invert the PR comparison even when the current helper is faster.
