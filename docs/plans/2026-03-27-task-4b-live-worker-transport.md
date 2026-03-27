# Melix Task 4B Execution Plan: Real Worker Transport for the Live Path

## Scope

This plan extends Task 4 by replacing the `NullWorkerClient` live path with a real worker transport.

The slice remains narrow:

- preserve the current Swift HTTP gateway and request coordinator contracts
- add a real worker client path from the Swift control plane to the Python worker
- preload the development text model through the runtime service when the worker is reachable
- add one deterministic backend mode for local integration and smoke testing when MLX is unavailable
- verify that `POST /v1/chat/completions` can stream real worker events end-to-end

This slice does not add:

- native Swift gRPC code generation or a permanent transport decision for later phases
- multimodal runtime support
- scheduler or cache behavior beyond the current placeholders
- a claim that the deterministic backend is equivalent to the eventual MLX production runtime

## Architecture Boundaries

- The Swift control plane continues to own request identity, HTTP translation, admission, and SSE formatting.
- The Python worker continues to own model execution, runtime state, and request cancellation.
- The transport shim is an implementation detail inside the worker-client boundary for Phase 0 only.
- Protobuf request and response types remain the source of truth for worker RPC payloads.
- The deterministic backend is allowed only as a local-development and integration-testing path.

## Planned Changes

### Transport

- Add a Swift worker client implementation that shells out to a Python helper process for:
  - worker reachability checks
  - model preload
  - streaming `Generate`
  - `Abort`
- The helper will speak real worker gRPC over a Unix domain socket using the existing Python generated stubs.
- The helper protocol between Swift and Python will be newline-delimited JSON carrying base64 protobuf payloads.

### Bootstrap

- Update the Swift bootstrap path to:
  - resolve a worker socket path from environment
  - optionally launch a managed Python worker process for local runs
  - attempt a runtime handshake and preload `melix-dev-text`
  - update the in-memory model catalog with the actual model handle returned by the worker
- If the worker is unavailable, the control plane must still boot, but the model remains unavailable for dispatch.

### Worker-side support

- Add a Python bridge helper script used only by the Swift worker client boundary.
- Add a deterministic text backend mode for tests and local smoke runs.
- Keep the existing gRPC worker service definitions unchanged.

### Test-first work

- Add fail-first Swift tests for:
  - bridge-line parsing and protobuf event decoding
  - worker client health, generate streaming, and abort behavior using a scripted helper
  - bootstrap preload behavior when a runtime handle is returned
- Add fail-first Python integration tests for:
  - bridge helper `health`, `load-model`, `generate`, and `abort`
  - live HTTP path with a managed worker and deterministic backend

## Performance Probes and Success Metrics

Required probes for this slice:

- bridge process spawn latency
- worker health-check latency
- model preload latency during bootstrap
- worker dispatch latency from Swift client launch to first upstream event
- end-to-end HTTP time-to-first-delta
- abort latency from cancel request to terminal worker event

Initial success targets:

- bridge health checks remain under 100 ms in local test runs
- model preload remains under 500 ms in deterministic-backend tests
- end-to-end time-to-first-delta remains under 250 ms in deterministic-backend integration tests
- abort completes within one worker-stream round in tests
- the touched Swift and Python scopes remain at or above 95 percent automated coverage before commit

If MLX is unavailable, the metrics report must clearly separate deterministic-backend measurements from MLX-runtime measurements.

## Verification Plan

Targeted verification:

```bash
swift test --package-path services/control-plane-swift --filter WorkerClientTests
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_control_plane_bridge.py -q
```

Broader verification:

```bash
make swift-test
make py-test
make integration-test
make coverage
```

## Exit Conditions

Task 4B is complete when:

- the live control-plane bootstrap no longer depends on `NullWorkerClient`
- the Swift worker client can stream real worker events and forward abort requests
- the development text model is preloaded through the runtime service when the worker is available
- the integration test proves an end-to-end streamed `POST /v1/chat/completions` path using the deterministic backend
- the metrics report includes the new transport and live-path timing probes
