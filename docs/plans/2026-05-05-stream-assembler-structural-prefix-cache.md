# Stream Assembler Structural Prefix Cache Plan

## Goal

Reduce repeated tuple concatenation in the Python request stream assembler hot path by caching the active structural tag prefix tuple once per assembler instance.

## Linux-only Constraint

This is a Python worker/runtime slice and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched Files

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `scripts/stream_assembler_structural_prefix_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Probe Definition

Register `stream-assembler-structural-prefix-cache` in the PR-scoped performance registry.

The probe repeatedly checks a partial structural tag suffix on a tool-enabled `RequestStreamAssembler` and records:

- `elapsed_ms_mean`
- `elapsed_ms_min`
- `peak_bytes_mean`
- `prefix_identity_hits`
- `held_suffix_hits`

## Success Metrics

- Focused stream assembler tests pass.
- Changed-scope coverage for touched Python executable lines is at least 95%.
- The local probe emits stable metrics and confirms the active prefix tuple identity remains stable for every hot-path access.
- A detached `origin/main` vs head probe comparison shows lower or equal hot-path elapsed time without changing suffix-hit counts.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_stream_assembler.py::test_structural_tag_prefixes_are_cached_per_parser_mode \
  services/mlx-worker-python/tests/test_stream_assembler.py::test_partial_structural_tag_suffix_checks_all_prefixes_in_one_endswith_call \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_structural_prefix_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python scripts/changed_scope_coverage.py --coverage-json coverage.json <touched Python files>

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/stream_assembler_structural_prefix_probe.py
```
