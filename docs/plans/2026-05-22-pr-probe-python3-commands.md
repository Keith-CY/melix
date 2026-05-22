# PR-scoped Probe Python 3 Command Normalization

## Scope

This slice normalizes registered PR-scoped performance probe command launchers from
bare `python` to `python3` where the commands execute through the MLX worker `uv`
project. The change is limited to the probe registry and the registry smoke test
that prevents regressions.

## Rationale

Scheduled performance slices run on Linux environments where `python` may be
absent while `python3` is available. Registered PR-scoped performance probes are
part of the performance validation path, so the registry should use the same
interpreter contract as repository automation and operator instructions.

## Registered probe coverage

The affected path is the probe registry itself: `infra/perf/pr_scoped_probes.json`.
It is covered by `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
including `test_registered_probes_expose_focused_commands`, which verifies that
registered probes expose focused `test_command`, `coverage_command`, and
`probe_command` entries and now rejects bare `uv ... python` probe launchers.

Representative registered probes still provide their focused commands and machine
readable metrics; this slice does not change measured workload code or metric
semantics.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json infra/perf/pr_scoped_probes.json services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dev-up-mlx-metal-dist-info-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/dev_up_probe_python3.json
```

## Success criteria

- Registry-focused pytest passes.
- Changed-scope coverage for the touched test remains above 95%.
- A representative registered probe executes through `python3` and reports the
  same metric keys as before.
- CI PR-scoped performance validation is green before merge.
