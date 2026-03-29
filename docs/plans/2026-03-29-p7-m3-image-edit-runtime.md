# P7-M3 Image Edit Runtime

**Goal:** Extend the Phase 7 worker path with deterministic image editing, mask-aware artifact lineage, and edit-specific validation while keeping control-plane orchestration deferred to `P7-M4`.

**Scope:** This milestone covers the Python image-edit worker path, local source and mask artifact persistence, generated edit output metadata, and worker-side validation. It does not add `/v1/images/*` control-plane endpoints or desktop Image panel behavior.

**Performance probes for this slice**

- `images.edit_job_latency_ms`
- `images.edit_artifact_publish_ms`
- `images.edit_output_bytes`
- `images.edit_peak_memory_bytes`

## Task 1: Add edit-path tests first

**Objective**

Define edit success and failure behavior before implementation.

**Files**

- Modify: `services/mlx-worker-python/tests/test_image_runtime.py`
- Modify: `services/mlx-worker-python/tests/test_runtime_edges.py`

**Implementation**

- Add a red test covering edit source, mask, generated artifact lineage, and completed job metadata.
- Add a red test covering missing edit source and invalid local mask references.
- Update the worker edge-case test so `ImageEdit` expects a model lookup failure once the edit path is implemented.

**Verification**

- `make py-test`

**Acceptance**

- The edit tests fail for missing runtime behavior rather than for malformed test setup.

## Task 2: Implement deterministic image edit runtime and worker core

**Objective**

Add a deterministic image-edit worker path that preserves source and mask lineage while returning generated output artifacts.

**Files**

- Modify: `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- Create: `services/mlx-worker-python/worker/engine/image_edit_core.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`

**Implementation**

- Extend the deterministic image runtime with source-image and optional mask loading for inline bytes and local file URIs.
- Persist edit-source, mask, and generated-output artifacts under the image job directory.
- Return a completed `ImageEditResponse` with explicit artifact roles and validation failures for missing or unreadable edit inputs.

**Verification**

- `make py-test`

**Acceptance**

- `ImageEdit` succeeds for a loaded image model and returns explicit artifact lineage.

## Task 3: Re-run milestone verification and capture evidence

**Objective**

Finish the milestone with fresh worker verification and measurable coverage.

**Files**

- Modify: `docs/README.md`

**Implementation**

- Add the milestone plan to the docs index.
- Re-run Python tests, integration tests, and coverage after the edit path lands.
- Record deterministic edit metrics with explicit lineage and validation evidence.

**Verification**

- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- The touched worker scope remains at or above `95%` coverage.
- The milestone has a non-`N/A` metrics report for deterministic image edit latency and artifact publication.
