# Gemma 4 Multimodal Import And Any-To-Any Evaluation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Melix to import valid Gemma 4 multimodal Hugging Face targets for image evaluation, including selected `any-to-any` repos, without silently degrading image evaluation into text-only execution.

**Architecture:** Extend direct Hub target resolution in the Swift control plane so supported Gemma 4 `any-to-any` targets resolve into the existing `image-text-to-text` product contract. Move Gemma 4 execution-mode truth closer to the Python worker runtime and local catalog by detecting actual multimodal bundle markers instead of relying on missing processor sidecars as a proxy for text-backed exports.

**Tech Stack:** Swift control plane, Python worker runtime, MLX VLM runtime ingress, pytest, Swift Testing.

---

## Scope

- [x] Accept supported Gemma 4 `any-to-any` Hub repos as `image-text-to-text` benchmark and evaluation targets.
- [x] Stop pre-emptively marking Gemma 4 Hub imports as `text_backed` only because `processor_config.json` is missing.
- [x] Detect Gemma 4 text-backed versus multimodal execution from stronger local evidence in the worker catalog and runtime.
- [x] Reject invalid live image evaluation attempts when a loaded Gemma 4 package is still text-backed.
- [x] Add targeted Swift and Python regression tests that cover the new import and execution rules.

## Root Cause Summary

- [x] The control plane currently rejects `pipeline_tag=any-to-any` even when the repo is a valid Gemma 4 VLM target.
- [x] The control plane currently downgrades Gemma 4 Hub imports to `melix.vlm.execution_mode=text_backed` when processor sidecars are absent, which is too coarse for MLX Gemma 4 exports.
- [x] The Python local catalog currently treats missing `vision_config` and missing `processor_config.json` as sufficient evidence for `text_backed`, which misses Gemma 4 bundles that still advertise multimodal tokens or ship multimodal weights.
- [x] The evaluation path currently lacks a guard that prevents text-backed VLM packages from producing invalid image-evaluation runs.

## Probes And Success Metrics

- [x] Swift import probe:
  - `ControlPlaneService` resolves a supported Gemma 4 `any-to-any` card into `image-text-to-text`.
- [x] Python catalog probe:
  - Gemma 4 bundles with multimodal markers do not receive `melix.vlm.execution_mode=text_backed`.
- [x] Python runtime probe:
  - loaded Gemma 4 VLM metadata reflects multimodal execution when the loaded model exposes vision capability.
- [x] Evaluation guard probe:
  - text-backed Gemma 4 packages fail image evaluation instead of emitting `input_modalities=text` and empty `media_references`.
- [x] Live smoke probe:
  - a real MLX-backed Gemma 4 image evaluation reaches sample evidence with non-empty `media_references` and `input_modalities` including `image`.

## Implementation Tasks

### Task 1: Control-Plane Hub Target Resolution

**Files:**
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- Test: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`

- [x] Add a focused task-family resolver for direct Hub benchmark and evaluation imports.
- [x] Map supported Gemma 4 `any-to-any` cards into `image-text-to-text`.
- [x] Keep unrelated `any-to-any` or unsupported families rejected.
- [x] Relax Gemma 4 direct-import text-backed inference so runtime-level detection stays authoritative.

### Task 2: Worker Gemma 4 Execution-Mode Detection

**Files:**
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`
- Test: `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- Test: `services/mlx-worker-python/tests/test_mlx_vlm_runtime.py`

- [x] Add stronger Gemma 4 multimodal markers for local bundle inspection.
- [x] Distinguish multimodal and text-backed Gemma 4 exports using config markers and weight-map evidence where available.
- [x] Let the runtime override stale import metadata when the loaded model exposes multimodal capability.

### Task 3: Evaluation Safety And Evidence

**Files:**
- Modify: `services/mlx-worker-python/worker/engine/evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_evaluation_core.py`
- Test: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [x] Add a guard that rejects live image evaluation for text-backed Gemma 4 packages.
- [x] Keep sample evidence truthful by preventing text-only fallback from being scored as image evaluation.

## Verification

- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`
- [x] `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.gemma4.final" uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py -q`
- [x] `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/gemma4_python_changed_coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py services/mlx-worker-python/worker/engine/evaluation_core.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_maintenance_service.py`
- [x] `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`
- [x] `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- [x] `git diff --check`
- [x] Live MLX smoke test against one Gemma 4 image-capable repo after code changes.

## Metrics Report

- Python targeted regression suite: `129 passed in 33.14s`
- Swift targeted regression suite: `173 tests` in `ControlPlaneServiceTests` passed
- Python changed-line coverage: `100.00%` (`131/131`)
- Swift changed-line coverage: `100.00%` (`128/128`)
- Live MLX smoke:
  - Repo: `mlx-community/gemma-4-e2b-it-4bit`
  - Suite: `imagenette`
  - Sample size: `1`
  - Job task kind: `image-text-to-text`
  - Sample input modalities: `["text", "image"]`
  - Sample media references: non-empty and points to the Imagenette fixture image
  - Score: `0.0` accuracy (`predicted="dart"`, `expected="tench"`)
