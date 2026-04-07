# Imagenette Evaluation Fixture Slice

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repository-owned Imagenette-based image evaluation fixture that can run through Melix `eval` with an MLX VLM target.

**Architecture:** Keep the current `eval` execution path unchanged and add one new multimodal suite package plus the smallest set of suite-registration updates needed to make it runnable. Store a deterministic validation subset in-repo, phrase each sample as short image-grounded classification QA, and score with the existing normalized exact-match pipeline.

**Tech Stack:** Swift, Python, MLX VLM runtime ingress, repository-owned evaluation fixtures, pytest, Swift Testing.

---

## Scope

- [x] Add a checked-in Imagenette validation subset under `services/mlx-worker-python/fixtures/evaluation/`.
- [x] Register one new evaluation suite id for worker execution and operator-facing defaults.
- [x] Add focused regression tests for default fixture resolution and multimodal sample execution.
- [x] Update operator docs with the new suite and data provenance.

## Probes And Success Metrics

- [x] Reuse existing evaluation metrics:
  - `eval.imagenette.accuracy`
  - `eval.imagenette.correct_count`
  - `eval.imagenette.incorrect_count`
  - `eval.imagenette.duration_seconds`
- [x] Verify sample-level evidence persists:
  - `task_kind`
  - `input_modalities`
  - `media_references`
  - `parse_status`

## Metrics Report

- Python coverage for `services/mlx-worker-python/worker/engine/evaluation_core.py`: `96%`
- Live MLX image evaluation probe:
  - target: `mlx-community/paligemma2-3b-ft-docci-448-8bit`
  - suite: `imagenette`
  - sample size: `10`
  - `eval.imagenette.accuracy`: `0.0`
  - `eval.imagenette.correct_count`: `0`
  - `eval.imagenette.incorrect_count`: `10`
  - `eval.imagenette.duration_seconds`: `45.826193`
  - evidence path: `.runtime/live-image-eval/jobs/model-ops/evaluation/runs/eval-0001/`

## Verification

- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- [x] `git diff --check`
