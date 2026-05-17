# Event Dialogue Diagnostics Top-K Probe Plan

## Goal

Reduce redundant work in event-extraction dialogue diagnostics by avoiding a full descending sort of every dialogue trace when the summary only retains the five slowest dialogues. This follow-up aggregate-streaming slice also avoids materializing numeric vectors for raw response size and throttle-sleep totals when only sum/count/max summary values are needed.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and the PR-scoped performance harness.

## Touched files

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- this plan file

## Performance probe definition

Register `evaluation-dialogue-diagnostics-top-k` in `infra/perf/pr_scoped_probes.json` as a `command_json` probe. The probe builds a deterministic large trace set, runs `EvaluationCore._event_extraction_dialogue_diagnostics(...)`, and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `peak_bytes_mean` (`lower_is_better`)
- `trace_count`
- `slowest_count`
- `top_duration_checksum`

## Success metrics

- Preserve dialogue diagnostics output shape and top-five slowest dialogue ordering.
- Preserve raw response `mean`/`max` and throttle sleep total semantics while streaming those aggregates in a single pass without intermediate lists.
- Changed executable line coverage for touched Python/test scope is at least 95%.
- Local base-vs-head probe shows lower elapsed time and/or peak traced memory for the top-k diagnostics path and streamed numeric aggregate path.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...focused tests...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ...focused tests... && ... coverage json ... && python3 scripts/changed_scope_coverage.py ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "...registered probe command..."`
- `python3 scripts/pr_scoped_performance_run.py --probe evaluation-dialogue-diagnostics-top-k ...` for base-vs-head evidence when available.
- `git diff --check`
