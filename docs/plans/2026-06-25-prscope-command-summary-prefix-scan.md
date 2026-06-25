# PR-scoped command summary prefix scan

## Context

The PR-scoped performance workflow summarizes long shell commands for CI
heartbeat logs. The registered `pr-scoped-performance-scope-matcher` probe
covers this hot path through `_probe_pr_scoped_scope_matcher`, including a
20,000-iteration command summary microprobe.

## Slice

Optimize `_summarize_command` only:

- preserve existing compact-summary behavior for blank, single-line, multiline,
  leading-whitespace, and truncated commands;
- use `str.index("\n")` in the common multiline path so the summary avoids the
  additional negative-branch check from `str.find()`;
- keep the change limited to the command summary prefix path.

## Verification Plan

Run the registered focused commands for `pr-scoped-performance-scope-matcher`:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/run_prscope_scope_probe.py
```

The local Linux probe validates Python behavior and direction. CI remains the
registered PR-scoped performance source of truth for merge gating.
