# Model Registry Artifact Module Scandir Fallback

## Context

This Python performance slice is limited to the sentence-transformer artifact
embedding module fallback in
`worker.model_registry.catalog._artifact_embedding_module_paths(...)` when a
local model directory does not provide `modules.json`.

The affected path is covered by the registered PR-scoped probe
`model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`. This slice extends that registered probe to
exercise the fallback module discovery path and to report
`module_path_glob_calls_mean` plus `module_path_scandir_calls_mean` alongside the
existing model-registry scan metrics. The registry entry has focused
`test_command`, `coverage_command`, and `probe_command` entries for the changed
production code, tests, probe script, registry, and this plan.

## Slice

Replace the two fallback `Path.glob("*_Pooling/config.json")` and
`Path.glob("*_Normalize/config.json")` traversals with a single top-level
`os.scandir(...)` pass. The behavior remains equivalent for supported local
sentence-transformer layouts because the fallback only accepts regular
`config.json` files under exactly one `*_Pooling` directory and at most one
`*_Normalize` directory, and still rejects unreadable or non-regular candidates
through `_artifact_embedding_regular_file(...)`.

## Validation

Run locally on Linux before PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_artifact_embedding_catalog_contract.py::test_catalog_fallback_sentence_transformer_modules_uses_single_scandir services/mlx-worker-python/tests/test_artifact_embedding_catalog_contract.py::test_catalog_resolves_explicit_and_fallback_sentence_transformer_modules services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_artifact_embedding_catalog_contract.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_artifact_embedding_catalog_contract.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/model_registry_plain_child_path_probe.py infra/perf/pr_scoped_probes.json docs/plans/2026-08-08-model-registry-artifact-module-scandir.md
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_MODEL_REGISTRY_PLAIN_CHILD_PROBE_SAMPLES=20 uv run --project services/mlx-worker-python python3 scripts/model_registry_plain_child_path_probe.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-model-registry-pooling-baseline-20260808 --head-repo "$PWD" --output /tmp/model_registry_pooling_probe.json
```

The hosted registered PR-scoped performance workflow remains the merge gate for
this slice.
