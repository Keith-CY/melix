# Issue 63 Hugging Face Cache Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make managed Hugging Face imports reuse the standard Hugging Face cache for model bytes while keeping Melix managed root as the lightweight descriptor and registry metadata store.

**Architecture:** The Python worker remains the authority for model import materialization and registry scanning. Managed Hugging Face imports write descriptor manifests under `MELIX_MANAGED_MODEL_ROOT`, but `melix.model_path` points at the resolved Hugging Face snapshot directory used by HF and MLX tooling. The Swift control plane and CLI continue to consume the existing model operation and `/v1/models` surfaces without protocol changes.

**Tech Stack:** Python 3.12, `huggingface_hub`, pytest, Swift 6, Swift Testing, Melix worker/control-plane protobufs.

---

## Implementation Tasks

- [x] Update `DownloadPipeline` managed Hub import behavior so `snapshot_download` uses the default Hugging Face cache, explicit `source_path` snapshots remain supported, and descriptor manifests are written without copying weight files into the managed root.
- [x] Update `WorkerModelCatalog` registry scanning so a non-empty manifest-provided `melix.model_path` is preserved as the runtime path, descriptor-relative registry identity remains stable, and capability detection reads runtime files from the external snapshot path.
- [x] Update evidence helpers so managed-root lookup reads descriptor manifests and resolves their external runtime path, while preserving compatibility with old copied managed layouts that contain real weights.
- [x] Update official docs to describe the descriptor/cache split for managed Hugging Face imports.
- [x] Add focused tests for Python worker import, registry scanning, real-model source resolution, Swift/CLI receipts, and `/v1/models` metadata exposure.

## Public Interfaces

- No protobuf schema changes.
- CLI `ManagedModelReceipt.managed_model_path` remains the Melix descriptor path under `MELIX_MANAGED_MODEL_ROOT`.
- Registry and `/v1/models` metadata expose the runtime model path through `melix.model_path` and expose descriptor identity through `melix.registry_descriptor_path` plus existing `melix.registry_*` fields.

## Verification And Metrics

- Run targeted Python tests for `test_maintenance_service.py`, `test_model_registry_catalog.py`, and `tests/test_real_model_support.py`.
- Run targeted Swift tests for `MelixCLIRunnerTests`, `ModelCatalogTests`, `ControlPlaneServiceTests`, and `OpenAIHandlerTests`.
- Run `make py-test`, `make swift-test`, and a relevant integration smoke when feasible.
- Measure changed-line coverage for the touched Python scope and keep it at or above 95 percent.
- Capture a metrics report for the changed scope using existing probes: `phase8.cli.managed_materialize_ms`, `registry.reload_latency_ms`, and `registry.discovered_model_count`. For non-live verification, record `N/A` with reason.

## Verification Record

- Targeted Python tests: `143 passed` for `test_maintenance_service.py`, `test_model_registry_catalog.py`, and `tests/test_real_model_support.py`.
- Python integration smoke: `test_models_endpoint_exposes_structured_registry_identity_metadata` passed with descriptor/cache metadata in `/v1/models`.
- Python changed-line coverage: `100.00% (63/63)` across the touched worker, helper, focused test, and integration files.
- Targeted Swift tests passed for `MelixCLIRunnerTests`, `ModelCatalogTests`, `ControlPlaneServiceTests`, and `OpenAIHandlerTests`.
- Full Python suite: `908 passed, 5 skipped`.
- Full Swift suite: `make swift-test` passed for protocol, text worker, control plane, and macOS menu bar packages.
- Live Hugging Face import disk usage and generation metrics: `N/A` in this implementation pass because no network-backed real model download or long-lived Melix stack was started. Deterministic tests cover descriptor/cache separation, registry metadata, CLI receipt semantics, and `/v1/models` exposure.

## Acceptance Evidence

- A managed import of `mlx-community/Qwen3-0.6B-4bit` leaves only a lightweight descriptor/manifest under `MELIX_MANAGED_MODEL_ROOT`.
- The actual model bytes reside in the standard Hugging Face cache snapshot path.
- `/v1/models` reports both Melix registry identity and the actual runtime `melix.model_path`.
- Generation, benchmark, or eval can resolve the imported model by model ID without passing an explicit local path.

## Assumptions

- Scope is limited to managed Hugging Face imports; local import semantics remain unchanged.
- Existing old managed Hugging Face copies remain loadable unless that repo/revision is re-imported, at which point the descriptor is rewritten in the new lightweight format.
- No dependency or generated protobuf artifact changes are required.
