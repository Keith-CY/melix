# P7-M2 Image Generation Runtime

**Goal:** Land the first executable Phase 7 worker path by replacing the Phase 7 placeholder `ImageGenerate` response with a deterministic Python image-generation runtime that persists local artifacts, returns completed job metadata, and leaves image editing deferred to `P7-M3`.

**Scope:** This milestone is limited to the Python worker runtime, runtime registry wiring, worker-side artifact persistence, and worker tests. It does not add control-plane HTTP endpoints, desktop Image panel behavior, or image-edit execution.

**Performance probes for this slice**

- `images.job_latency_ms`
- `images.artifact_publish_ms`
- `images.output_bytes`
- `images.peak_memory_bytes`

## Task 1: Add worker-side image generation tests first

**Objective**

Define the first executable success path for image generation before writing runtime code.

**Files**

- Create: `services/mlx-worker-python/tests/test_image_runtime.py`
- Modify: `services/mlx-worker-python/tests/test_runtime_edges.py`

**Implementation**

- Add a red test covering image-model load, deterministic image generation, artifact persistence, and completed job metadata.
- Add a red test covering wrong-model validation for image generation.
- Update the worker edge-case test so `ImageGenerate` expects model lookup failure instead of the old placeholder `unimplemented` response.

**Verification**

- `make py-test`

**Acceptance**

- The new tests fail for the expected missing-runtime reasons before implementation begins.

## Task 2: Implement the deterministic image generation runtime and worker core

**Objective**

Create a minimal but production-shaped image-generation execution path that persists artifacts and returns coherent job metadata.

**Files**

- Create: `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- Create: `services/mlx-worker-python/worker/engine/image_generation_core.py`
- Modify: `services/mlx-worker-python/worker/model_registry/catalog.py`
- Modify: `services/mlx-worker-python/worker/registry.py`
- Modify: `services/mlx-worker-python/worker/grpc_server.py`

**Implementation**

- Add a deterministic image generation runtime with local artifact output, image-job IDs, artifact metadata, and probe snapshots.
- Add a worker engine core that validates loaded models, runs the runtime, and maps runtime results to `ImageGenerateResponse`.
- Add a `melix-dev-image` model to the worker catalog and route it through the registry as an image runtime kind.
- Leave `ImageEdit` unchanged and explicitly deferred to `P7-M3`.

**Verification**

- `make py-test`

**Acceptance**

- `ImageGenerate` succeeds for a loaded image model, persists artifacts, and returns a completed job descriptor.

## Task 3: Re-run verification and capture milestone evidence

**Objective**

Finish the milestone with fresh worker verification and measurable coverage.

**Files**

- Modify: `docs/README.md`

**Implementation**

- Add the milestone plan to the docs index.
- Run the repository Python and integration verification needed for a worker milestone handoff.
- Record a metrics report, using `N/A` only for control-plane and desktop paths that are still untouched in this slice.

**Verification**

- `make py-test`
- `make integration-test`
- `make coverage`

**Acceptance**

- The touched worker scope remains at or above `95%` coverage.
- The milestone has a concrete metrics report for image generation artifact persistence.
