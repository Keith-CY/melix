# Evaluation final result slotted records

## Goal

Reduce per-record Python allocation overhead on the evaluation final-result path by making the immutable request, source, and result records slotted. The behavior stays unchanged: extraction, scoring, materialization request wiring, and Hugging Face source defaults remain the same.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `evaluation-final-result-json-typed-score-aggregate` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_json_typed_score_probe.py`

The probe reports elapsed time and peak bytes for repeated JSON typed scoring against a deterministic nested payload.

## Slice

- Add `slots=True` to immutable evaluation final-result dataclasses.
- Add a regression test proving the public records do not expose per-instance `__dict__` while preserving extraction, scoring, request, materialization, and HF source behavior.
- Do not change extraction heuristics, scoring semantics, cache keys, file formats, or probe behavior.

## Verification

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. GitHub Actions PR-scoped performance remains the final registered probe validation and merge gate.
