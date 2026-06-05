# Issue 1570 Streaming Export Results

## Goal

Fix GitHub issue #1570 by making `ops.export_results` capable of delivering
large benchmark, evaluation, and LoRA comparison export bundles without placing
the whole bundle in a single gRPC response.

## Problem

`melix lora run` can complete LoRA training, adapter activation, and evaluation,
then fail during `export-results` because the worker currently returns the full
`export-bundle.json` content in `ExportResultsResponse.export_json`. Large
per-sample evaluation payloads can exceed the default gRPC 4 MiB receive limit.
The CLI then treats a successful training run as failed and downstream batch
automation loses the expected JSON receipt and summary artifacts.

## End State

`ExportResults` remains available as a backward-compatible unary RPC, but the
primary control-plane and CLI path uses a new streaming export RPC. The worker
writes the bundle through a same-directory temporary file and atomically replaces
`export-bundle.json`, emits a small metadata event, streams bounded byte chunks,
and emits a terminal completion event. Swift reconstructs the bundle from chunks
and decodes it exactly as today.

The fix must preserve these properties:

- `melix lora run --json` keeps returning a valid
  `melix.lora_run_receipt.v1` receipt when training, activation, and evaluation
  completed.
- Evaluation summary CSV and sample JSONL export continue to work for LoRA
  runs.
- No single streaming event should contain the whole export bundle.
- Existing unary `ExportResults` clients remain source-compatible.

## Protocol Design

Add `ExportResultsStream(ExportResultsRequest) returns (stream ExportResultsEvent)`
to `worker/v1/maintenance.proto`.

`ExportResultsEvent` has a `oneof` payload:

- `started`: path, total bytes, and chunk size.
- `chunk`: sequence number and raw bytes.
- `completed`: path, total bytes, chunk count, and SHA-256.
- `failed`: typed `ErrorStatus`.

The unary `ExportResultsResponse` remains unchanged for compatibility. New
Swift control-plane paths call the streaming RPC first. Test stubs and old
clients can continue using the unary RPC.

## Data Flow

1. Python worker receives `ExportResultsStream`.
2. Worker builds `export-bundle.json` using the same `write_export_bundle`
   function used by unary export, publishing through atomic replace so
   concurrent exports cannot corrupt active stream readers.
3. Worker streams metadata and chunks from the bundle file.
4. Swift `ModelOperationsWorkerClientProtocol` exposes a streaming-export
   method that returns either reconstructed JSON plus export metadata or a small
   value that can be decoded by existing CLI code.
5. `ControlPlaneService.handleExportResults` populates `exportBundleJson` from
   the reconstructed streamed bytes.
6. `MelixCLIRunner.fetchBenchmarkExportBundle` keeps decoding the same
   `ControlPlaneBenchmarkExportBundle` surface, so benchmark/eval/LoRA callers
   do not need separate parsing logic.

## Error Handling

- Stream `failed` events map to the same control-plane error response shape as
  unary failures.
- Missing `completed`, mismatched byte count, chunk-order gaps, or SHA mismatch
  are treated as export failures before decoding JSON.
- If a model-operations test double does not implement streaming export, the
  production client may fall back to unary export only for compatibility. The
  real Python bridge and gRPC runner must support streaming.

## Performance Probes And Metrics

The implementation and tests must record or assert:

- exported bundle byte count
- configured chunk size
- chunk count
- largest streamed event payload size remains below the simulated 4 MiB limit
- stream reconstruction SHA-256 matches the worker-computed SHA-256

## Verification

Focused verification for this issue:

```bash
make proto
swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|PythonBridgeWorkerClientTests'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py
swift test --filter MelixCLIRunnerTests
```

Before PR handoff, run the repository-relevant coverage and metrics gates
required by `AGENTS.md` for the touched Swift and Python scopes.
