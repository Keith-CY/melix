# Event Dialogue Diagnostics Top-K Probe Plan

## Goal

Reduce redundant work in event-extraction dialogue diagnostics by avoiding a full sort when the summary only keeps the five slowest dialogue traces.

## Touched Files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-Only Constraint

This is a Python worker optimization and can be verified on Linux with focused pytest, changed-scope coverage, and the PR-scoped performance harness.

## Performance Probe Definition

Register `evaluation-dialogue-diagnostics-top-k` in `infra/perf/pr_scoped_probes.json`.

The probe builds a large synthetic dialogue trace list, repeatedly calls `EvaluationCore._event_extraction_dialogue_diagnostics(...)`, and reports:

- `elapsed_ms_mean` — lower is better.
- `sorted_calls_mean` — lower is better; expected to drop from one full `sorted(...)` call per diagnostics pass to zero.
- `trace_count` and `iteration_count` — structural workload metrics.

## Success Metrics

- Preserve the exact five slowest-dialogue payloads and ordering.
- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local base-vs-head scoped probe shows zero full-sort calls and improved elapsed time.

## Verification Commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && coverage json ... && python scripts/changed_scope_coverage.py ...`
- `python scripts/pr_scoped_performance_run.py --probe evaluation-dialogue-diagnostics-top-k --base-ref origin/main --head-ref HEAD --output /tmp/...json`
- `git diff --check`
