# Probe policy environment parse static dispatch

## Scope

This Python-only performance slice targets the empty-environment probe policy parse path in
`services/mlx-worker-python/worker/productization/probe_policy.py`.

The affected path is covered by the registered PR-scoped performance probe
`probe-policy-noop-overhead` in `infra/perf/pr_scoped_probes.json`. The registry entry has
focused `test_command`, `coverage_command`, and `probe_command` entries, and the probe reports
`env_parse_empty_call_ms_mean` together with the existing no-op policy overhead metrics.

## Hypothesis

`ProbePolicy.from_env(...)` is called on hot productization setup paths and is also exercised by
the registered no-op overhead probe. It does not need dynamic subclass construction, so changing the
factory from a classmethod to a staticmethod avoids classmethod binding and removes one descriptor
argument on the hot empty-env path while preserving the same cached policy instances.

## Verification plan

Run the focused registered probe policy tests, changed-scope coverage, and the local Linux registered
probe comparison:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_probe_policy.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_probe_policy_overhead_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_policy_noop_overhead_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_probe_policy.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_probe_policy_overhead_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_policy_noop_overhead_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/probe_policy.py services/mlx-worker-python/tests/test_probe_policy.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/probe_policy_noop_overhead_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id probe-policy-noop-overhead --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/probe_policy_noop_overhead.json
```

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. GitHub Actions PR-scoped performance
remains the merge gate for the registered CI probe report.
