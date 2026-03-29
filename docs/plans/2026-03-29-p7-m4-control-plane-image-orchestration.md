# P7-M4 Control-Plane Image Orchestration

**Goal:** Make Phase 7 image generation and image editing live through the control plane with `/v1/images/generations` and `/v1/images/edits`, routed Python image workers, image-job state visibility, and operator-safe artifact metadata.

**Scope:** This milestone covers control-plane HTTP handling, Python bridge transport for image RPCs, image-job read-model updates, local-stack preload wiring, and integration evidence. It does not add the native SwiftUI Image panel; that remains `P7-M5`.

**Performance probes for this slice**

- `images.request_latency_ms`
- `images.queue_wait_ms`
- `images.job_terminal_latency_ms`
- `images.artifact_publish_ms`
- `images.output_bytes`

## Task 1: Add transport and endpoint contract tests first

**Objective**

Pin the bridge, worker-client, and HTTP endpoint contracts before implementation.

**Files**

- Modify: `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py`
- Modify: `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
- Modify: `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`

**Implementation**

- Add bridge tests for `image-generate` and `image-edit` command forwarding.
- Add Swift worker-client tests for image unary decoding and preload behavior.
- Add handler tests for `/v1/images/generations` and `/v1/images/edits`, including job-state visibility and worker-unavailable paths.

**Verification**

- `swift test --package-path services/control-plane-swift --filter '(PythonBridgeWorkerClientTests|OpenAIHandlerTests)'`
- `make py-test`

**Acceptance**

- The new tests fail only because the image orchestration path is missing.

## Task 2: Implement bridge routing and control-plane image endpoints

**Objective**

Expose working image endpoints through the control plane and keep job metadata operator-visible.

**Files**

- Modify: `services/mlx-worker-python/worker/control_plane_bridge.py`
- Modify: `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`
- Modify: `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
- Modify: `services/control-plane-swift/Sources/Bootstrap/main.swift`

**Implementation**

- Add `image-generate` and `image-edit` bridge commands and decode them into worker protobuf responses.
- Extend the Swift-side Python bridge client with image generation and image edit unary calls.
- Add `/v1/images/generations` and `/v1/images/edits` request and response handling in the control plane.
- Record queued, running, terminal, and artifact-bearing image job summaries in the shared image-job read model.
- Preload the deterministic image model in the local stack so the Phase 7 routes are live in integration.

**Verification**

- `make proto`
- `swift test --package-path services/control-plane-swift --filter '(PythonBridgeWorkerClientTests|OpenAIHandlerTests)'`
- `make py-test`

**Acceptance**

- Both image endpoints route to the Python image worker and return explicit job metadata plus artifact references.

## Task 3: Add integration evidence and touched-scope coverage

**Objective**

Close the milestone with live local-stack verification and measurable coverage.

**Files**

- Modify: `tests/integration/helpers.py`
- Create: `tests/integration/test_image_endpoints.py`
- Modify: `docs/README.md`

**Implementation**

- Add helper URLs for the image endpoints.
- Add integration coverage for generation and edit flows through the live control plane.
- Add the milestone plan to the docs index.
- Run targeted Swift changed-line coverage and targeted Python worker coverage for the touched scope.

**Verification**

- `swift test --package-path services/control-plane-swift --filter '(PythonBridgeWorkerClientTests|OpenAIHandlerTests)'`
- `make py-test`
- `make integration-test`
- `/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift test --package-path services/control-plane-swift --scratch-path /tmp/melix-control-plane-p7m4-coverage --enable-code-coverage --filter '(PythonBridgeWorkerClientTests|OpenAIHandlerTests)'`
- `python3 scripts/swift_changed_line_coverage.py --binary /tmp/melix-control-plane-p7m4-coverage/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/melix-control-plane-p7m4-coverage/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests -q`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/control_plane_bridge.py`
- `git diff --check`

**Acceptance**

- Touched Swift and Python source stays at or above `95%` changed-scope coverage.
- The milestone has a non-`N/A` metrics report for image request latency, queue wait, artifact publication, and output bytes.
