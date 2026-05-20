# Agentic LoRA SFT Smoke Training

## Goal

Implement issue #692 by adding a tiny repository-owned
`agentic_tool_trace` fixture and a deterministic local smoke path that proves
the LoRA SFT pipeline can consume agentic traces end to end.

## Governing Specs

- `docs/agentic-trajectory-dataset-contract.md`
- `docs/plans/2026-05-20-agentic-lora-sft-formatting.md`
- `docs/runbooks/phase-8-lora-adapter-workflow.md`

## Scope

This slice is limited to local training-path evidence for
`training_objective=agentic_sft`:

- Add a clean smoke fixture package with one train trace and one validation
  trace.
- Add a script that runs `LoRATrainingPipeline` with the checked-in
  deterministic LoRA runner.
- Persist adapter manifest, normalized dataset snapshot, trainer rows, and
  original trace rows under a caller-selected output directory.
- Assert the smoke evidence includes trace quality, SFT projection metrics,
  token metrics, response-only boundaries, and adapter receipt provenance.

Out of scope:

- Real MLX-LM model training.
- Adapter activation or quality comparison.
- Benchmark or evaluation improvement claims.
- Changes to protobuf schemas or Swift control-plane APIs.

## Performance And Metrics

The smoke path is an offline CI/developer verification path. It does not add
serving-path overhead.

Measurement points:

- Smoke wall-clock duration.
- Source trace count.
- Trainer row count.
- Validation trainer row count.
- Tool-call and observation counts.
- Response-only boundary count.
- Agentic SFT trace, tool-call, observation, and final-answer token counts.
- Focused pytest runtime for the smoke script and agentic SFT contract tests.
- Changed-scope coverage for the new Python smoke path, target >= 95%.

## Implementation Plan

- [x] Add a clean `agentic-lora-sft-smoke.dev.v1` fixture package.
- [x] Add `scripts/agentic_lora_sft_smoke.py`.
- [x] Add focused pytest coverage for the smoke payload, CLI output, and
  persisted artifacts.
- [x] Update the trajectory contract anchors to name the smoke fixture and
  script.
- [x] Run focused tests, changed-scope coverage, and the smoke command.

## Success Criteria

- The smoke exits zero and emits machine-readable evidence.
- The adapter manifest records `training_objective: agentic_sft`,
  `dataset_contract: agentic_tool_trace`, and
  `trainer_dataset_format: chat_messages`.
- The normalized snapshot writes `train.jsonl`, `valid.jsonl`,
  `agentic-traces.train.jsonl`, and `agentic-traces.valid.jsonl`.
- The smoke report confirms response-only and mask-prompt boundaries for all
  trainer rows.
- The smoke report records `agentic_sft_token_metrics` and
  `trajectory_quality_metrics`.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_lora_sft_smoke.py services/mlx-worker-python/tests/test_agentic_sft_training_contract.py`
  - Result: 6 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py -k 'agentic or trajectory' services/mlx-worker-python/tests/test_agentic_lora_sft_smoke.py services/mlx-worker-python/tests/test_agentic_sft_training_contract.py`
  - Result: 28 passed, 53 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/agentic_lora_sft_smoke.coverage -m pytest -q services/mlx-worker-python/tests/test_agentic_lora_sft_smoke.py services/mlx-worker-python/tests/test_agentic_sft_training_contract.py`
  - Result: 6 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/agentic_lora_sft_smoke.coverage -o /tmp/agentic_lora_sft_smoke_coverage.json`
  - Result: wrote `/tmp/agentic_lora_sft_smoke_coverage.json`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json /tmp/agentic_lora_sft_smoke_coverage.json scripts/agentic_lora_sft_smoke.py services/mlx-worker-python/tests/test_agentic_lora_sft_smoke.py`
  - Result: changed-line coverage 99.33% (149/150).
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/agentic_lora_sft_smoke.py --json --output-dir .runtime/agentic-lora-sft-smoke`
  - Result: passed with `trainer_row_count=2`, `trainer_validation_row_count=2`,
    `response_only_boundary_count=4`, and persisted adapter/snapshot evidence
    under `.runtime/agentic-lora-sft-smoke`.
- `git diff --check`
  - Result: passed.
