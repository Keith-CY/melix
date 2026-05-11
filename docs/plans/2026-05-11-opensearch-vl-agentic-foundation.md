# OpenSearch-VL Agentic Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first OpenSearch-VL data foundation slice: an agentic tool trace training dataset contract plus construction-time leakage and trace quality reporting.

**Architecture:** The Python worker training dataset builder remains the ingestion boundary for local and packaged fine-tuning data. This slice adds an additive `agentic_tool_trace` format to the existing package/local-source pipeline, preserving structured trace fields while reporting tool-call, observation, fatal-stage, and explicit leakage-term metrics in the manifest quality block.

**Tech Stack:** Python 3.12, `pytest`, Melix `ModelOperationError`, existing `worker.model_ops.training_dataset` JSONL package builder.

---

## Scope

- Covers GitHub issues #664 M1 and #734 M1/M2.
- Adds the first contract hook that #674 can consume later, but does not implement the unified tool runtime in this slice.
- Touches only the Python worker training dataset package path, tests, fixture data, and this plan.

## Files

- Modify: `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- Modify: `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- Create: `services/mlx-worker-python/fixtures/training/agentic-tool-trace.dev.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/training/agentic-tool-trace.dev.v1/samples.jsonl`
- Create: `docs/plans/2026-05-11-opensearch-vl-agentic-foundation.md`

## Metrics And Probes

- `agentic_trace_count`: number of normalized trace samples inspected.
- `tool_call_count`: total assistant tool calls across inspected traces.
- `tool_observation_count`: total tool observations across inspected traces.
- `fatal_trace_count`: traces with a non-empty `fatal_stage`.
- `leakage_count`: traces where explicit `leakage_terms` appear in question text, turn content, tool-call arguments, or tool observations.
- `token_stats`: existing whitespace estimator extended to count agentic prompt context and final answer completion text.

## Implementation Tasks

### Task 1: Plan And Red Tests

- [x] Add this plan under `docs/plans/`.
- [x] Add a failing test that loads an `agentic_tool_trace` package and verifies structured normalization preserves `trace_id`, `question`, `media_refs`, `tools`, `turns`, `final_answer`, `expected_answer`, `evidence_ids`, `reward`, and `fatal_stage`.
- [x] Add failing validation tests for empty turns, tool observations without matching assistant calls, and explicit `leakage_terms` appearing in a trace.
- [x] Add a failing builder test proving local JSONL inference converts agentic trace rows and emits quality metrics.
- [x] Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py -k 'agentic or leakage'
```

Expected: fail because `agentic_tool_trace` is not yet a supported format.

### Task 2: Dataset Contract Implementation

- [x] Add `agentic_tool_trace` to `_SUPPORTED_FORMATS`.
- [x] Add `_normalize_agentic_tool_trace_sample(...)` and call it from `_normalize_sample(...)`.
- [x] Validate that `trace_id`, `question`, `turns`, and `final_answer` are non-empty.
- [x] Validate every `tool` turn references a prior assistant `tool_call.id`.
- [x] Preserve optional structured fields: `media_refs`, `tools`, `expected_answer`, `evidence_ids`, `reward`, `fatal_stage`, and `leakage_terms`.
- [x] Keep the implementation additive; existing formats must preserve their current behavior.

### Task 3: Local Conversion And Quality Metrics

- [x] Add `agentic_tool_trace` to explicit and automatic local conversion template resolution.
- [x] Add agentic trace quality metrics and merge their fields into the existing quality report only when `format_name == "agentic_tool_trace"`.
- [x] Extend `_sample_token_counts(...)` and `_sample_text_segments(...)` for agentic traces.
- [x] Treat explicit leakage findings as dirty samples with the reason `leakage_terms`.
- [x] Run the focused test command from Task 1 and confirm it passes.

### Task 4: Fixture And Verification

- [x] Add a small `agentic-tool-trace.dev.v1` fixture package that can be loaded by the dataset package loader.
- [x] Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py -k 'agentic or leakage or training_dataset'
```

- [x] Run changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source services/mlx-worker-python/worker/model_ops/training_dataset.py -m pytest -q services/mlx-worker-python/tests/test_training_dataset_builder.py -k 'agentic or leakage or training_dataset'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report --include 'services/mlx-worker-python/worker/model_ops/training_dataset.py'
```

- [x] Run `git diff --check`.

## Success Criteria

- The agentic trace fixture loads through `load_training_dataset_package(...)`.
- Local JSONL builder inference emits `format: agentic_tool_trace`.
- Manifest quality reports include agentic trace and explicit leakage metrics.
- Focused tests pass.
- Changed-scope coverage for `training_dataset.py` is at least 95 percent or the exact measurable gap is reported.
- `git diff --check` passes.
