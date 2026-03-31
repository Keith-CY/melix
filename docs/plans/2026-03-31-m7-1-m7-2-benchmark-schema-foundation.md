# M7.1-M7.2 Benchmark And Evaluation Schema Foundation

## Goal

Land the first repository-owned benchmark and evaluation job or result schemas so M7 can stop depending on ad hoc bench markdown and loose metric maps.

## Scope

- add typed control-plane protocol messages for benchmark job identity and benchmark result shape
- add typed control-plane protocol messages for evaluation job identity and evaluation result shape
- add productization-side Python schema helpers that can serialize and persist benchmark and evaluation records
- thread the new benchmark schema through the existing `ops.run_bench` control-plane path without widening into queueing or UI overhaul yet

## Out Of Scope

- benchmark queueing and batch-factor selection
- offline dataset packaging
- evaluation runners
- VLM benchmark variants
- community submission

## Files

- update `packages/protocol/schema/controlplane/v1/control_plane.proto`
- regenerate `packages/protocol/swift/controlplane/v1/control_plane.pb.swift`
- regenerate `packages/protocol/python/controlplane/v1/control_plane_pb2.py`
- regenerate `packages/protocol/descriptors/melix.pb`
- create `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- update `services/mlx-worker-python/worker/productization/__init__.py`
- update `services/mlx-worker-python/worker/productization/release_gates.py`
- update `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
- update `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
- add Python tests for benchmark and evaluation schema helpers

## Measurement Points

- benchmark jobs expose stable `job_id`, `model_id`, `status`, `suite`, and parameter identity
- benchmark results expose machine-readable metrics rather than only markdown
- evaluation jobs and results have dedicated schema types even before runner execution exists

## Verification

- `make proto`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_release_gates.py`
- touched-scope Swift tests for `ControlPlaneServiceTests`

## Acceptance

- control-plane protocol exposes dedicated benchmark and evaluation schema messages
- Python productization code can build and persist those schema shapes without bespoke parsing
- the existing `ops.run_bench` path returns typed benchmark job and result payloads alongside legacy markdown fields
