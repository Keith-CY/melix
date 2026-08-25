# Evaluation dialogue diagnostics top-k materialization

## Scope

This Python-only performance slice is limited to `EvaluationCore._event_extraction_dialogue_diagnostics()` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

The current implementation already uses `heapq.nlargest()` for the five slowest dialogues, but then materializes the output with an append loop. This slice keeps the same top-k selection, ordering, fields, and fallback defaults while materializing the five result dictionaries with a direct list comprehension.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe `evaluation-dialogue-diagnostics-top-k` in `infra/perf/pr_scoped_probes.json`.

The registry entry watches the changed engine path, focused event-extraction tests, PR-scoped performance tests, and the probe registry. It includes focused `test_command`, `coverage_command`, and `probe_command` entries. The probe measures `elapsed_ms_mean` and `peak_bytes_mean` for a synthetic 50k-trace diagnostics workload.

## Implementation plan

1. Preserve the existing `heapq.nlargest()` key and top-five ordering.
2. Replace the append loop with a list comprehension for the fixed-size output materialization.
3. Run the focused test, changed-scope coverage, and registered probe locally on Linux.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched files is at least 95%.
- Registered `evaluation-dialogue-diagnostics-top-k` probe reports lower `elapsed_ms_mean` on head versus `origin/main` without a material memory regression.

GitHub Actions PR-scoped performance remains the merge gate after the branch is pushed.
