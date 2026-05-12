# Text family metadata copy elision

## Scope

This slice is limited to the Python text-family adapter resolver in
`services/mlx-worker-python/worker/runtime/text_family_adapters.py`.
It avoids copying resolver metadata mappings on every call while preserving the
existing read-only behavior for standard dictionaries and custom `Mapping`
implementations.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe provides:

- `test_command` for focused text-family adapter and PR-scoped performance tests.
- `coverage_command` for changed-scope coverage over the resolver, focused tests,
  probe test, and probe script.
- `probe_command` for `scripts/text_family_config_probe.py`, which reports
  resolver elapsed time, peak bytes, and config copy calls.

## Verification plan

This is a Python-only slice and is locally verifiable on Linux before CI:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_text_family_config_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_text_family_config_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_text_family_config_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_text_family_config_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/text_family_adapters.py services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/text_family_config_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/text_family_config_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.

## Acceptance

- Focused tests and changed-scope coverage pass.
- The probe reports `config_copy_calls_mean == 0.0`.
- The head probe has a lower or otherwise acceptable `elapsed_ms_mean` compared
  with the `origin/main` baseline.
