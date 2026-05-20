# Agentic LoRA Eval Compare Evidence

## Goal

Implement issue #693 by adding a deterministic local evidence path that trains
the repository-owned agentic LoRA SFT smoke fixture, activates the resulting
adapter as an adapter-backed runtime target, and runs EvaluationCore compare
against that activated adapter with persisted paired sample evidence.

## Governing Specs

- `docs/agentic-trajectory-dataset-contract.md`
- `docs/plans/2026-05-20-agentic-lora-sft-smoke-training.md`
- `docs/plans/2026-04-21-lora-adapter-native-compare.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

## Scope

This slice is limited to deterministic local evidence for the
OpenSearch-VL-aligned agentic fixture:

- Reuse the checked-in `agentic-lora-sft-smoke.dev.v1` fixture and deterministic
  LoRA training runner.
- Activate the generated adapter with `activation_mode=adapter_backed_runtime`.
- Register the activated derived model id as the compare target in a local
  deterministic registry.
- Run the existing EvaluationCore base-vs-target compare path and persist
  compare job, summary, CSV, markdown report, and paired sample JSONL artifacts.
- Emit a top-level JSON evidence payload that records activation provenance,
  compare artifact paths, score deltas, and release-gate counts.

Out of scope:

- Real MLX-LM training or inference.
- Claims about production model quality.
- New protobuf, Swift, or menu bar API surface.
- Replacing the existing adapter-manifest compare target flow.

## Performance And Metrics

The path is an offline developer/CI smoke path. It does not add serving-path
overhead.

Measurement points:

- Smoke wall-clock duration.
- Adapter activation duration and activation mode.
- Paired compare sample count.
- Base accuracy, target accuracy, and delta accuracy.
- Win, loss, tie, and regression counts.
- Persisted compare artifact paths.
- Focused pytest runtime for the script.
- Changed-scope coverage for the new Python smoke path, target >= 95%.

## Implementation Plan

- [x] Add `scripts/agentic_lora_eval_compare_smoke.py`.
- [x] Add focused pytest coverage for the evidence payload, persisted artifacts,
  CLI output, and failure exit behavior.
- [x] Update the trajectory dataset contract anchors to name the eval compare
  smoke evidence path.
- [x] Run focused tests, changed-scope coverage, the smoke command, and
  `git diff --check`.

## Success Criteria

- The smoke exits zero and emits machine-readable evidence.
- The adapter activation manifest records
  `activation_mode: adapter_backed_runtime`.
- The compare job targets the activated derived model id.
- The paired sample artifact records base and target raw responses, extracted
  results, typed scores, and outcome.
- The target score is higher than the base score on the validation trace and
  the release gate reports no regressions.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_lora_eval_compare_smoke.py`
  - Result: 4 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_lora_eval_compare_smoke.py services/mlx-worker-python/tests/test_agentic_lora_sft_smoke.py services/mlx-worker-python/tests/test_evaluation_core.py -k 'agentic_lora or compare'`
  - Result: 27 passed, 78 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/agentic_lora_eval_compare.coverage -m pytest -q services/mlx-worker-python/tests/test_agentic_lora_eval_compare_smoke.py`
  - Result: 4 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/agentic_lora_eval_compare.coverage -o /tmp/agentic_lora_eval_compare_coverage.json`
  - Result: wrote `/tmp/agentic_lora_eval_compare_coverage.json`.
- `git add -N docs/plans/2026-05-20-agentic-lora-eval-compare-evidence.md scripts/agentic_lora_eval_compare_smoke.py services/mlx-worker-python/tests/test_agentic_lora_eval_compare_smoke.py`
  - Result: staged intent-to-add so changed-line coverage can measure new
    Python files before the commit.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic_lora_eval_compare_coverage.json scripts/agentic_lora_eval_compare_smoke.py services/mlx-worker-python/tests/test_agentic_lora_eval_compare_smoke.py`
  - Result: changed-line coverage 98.29% (230/234).
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/agentic_lora_eval_compare_smoke.py --json --output-dir .runtime/agentic-lora-eval-compare-smoke`
  - Result: passed with `base_accuracy=0.0`, `target_accuracy=1.0`,
    `delta_accuracy=1.0`, `win_count=1`, `regression_count=0`, activated
    adapter target `agentic-lora-sft-smoke-model-lora-e682d3a2`, and persisted
    compare artifacts under `.runtime/agentic-lora-eval-compare-smoke`.
- `git diff --check`
  - Result: passed.
