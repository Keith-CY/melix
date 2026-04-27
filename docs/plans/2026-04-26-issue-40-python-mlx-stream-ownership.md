# Issue 40 Python MLX Stream Ownership Plan

## Goal

Make Python MLX text compatibility and MLX VLM execution run on an executor-owned MLX context so model load, warmup, generation, and VLM streaming do not depend on arbitrary gRPC worker threads.

## Architecture

Add a single-thread Python runtime executor for MLX-backed text and VLM work. The executor initializes optional MLX stream state on its owned thread, exposes ownership metrics, and provides blocking and streaming adapters for the existing runtime methods. The Swift text worker and active-KV release gate remain unchanged.

## Scope

- Add `worker/runtime/mlx_executor.py` with an owned-thread execution boundary, optional MLX stream initialization, streaming iteration support, shutdown support, and metrics.
- Route default `MLXTextRuntime` and `MLXVLMRuntime` load/generation work through the executor while preserving injected runtime test hooks.
- Implement `WarmupModel` and `LoadModel.warmup_after_load` for loaded text and VLM models using the same executor-owned path.
- Extend worker runtime stats with `generation_stream_owner_mode`, `worker_thread_init_latency_ms`, and `stream_sync_fallback_count`, then regenerate protobuf outputs.
- Publish the new metrics through control-plane observability where runtime stats are already refreshed.

## Tests

- Python executor tests prove all submitted and streamed work runs on one owned thread, exceptions propagate, shutdown rejects new work, and fake MLX stream hooks initialize on that thread.
- Text runtime tests prove backend `load_model` and `generate_tokens` run on the executor thread even when the runtime was constructed on the main thread.
- VLM runtime tests prove `load_model`, chat-template formatting, and `stream_generate` run on the same executor thread while temp-media cleanup still completes.
- Runtime service tests prove `WarmupModel` succeeds for loaded text/VLM handles, rejects unknown handles, and reports runtime stats fields.
- Swift worker-client/control-plane tests prove generated runtime stats decode and new metrics are propagated.

## Verification

- `make proto`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_executor.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_runtime_edges.py -q`
- Python changed-line coverage for touched worker files must be at least 95 percent.
- Targeted Swift tests for `PythonBridgeWorkerClientTests`, `WorkerClientTests`, and any control-plane metrics propagation tests touched by the proto addition.
- `make py-test`
- `make swift-test`
- `make integration-test` if local prerequisites are available.

## Metrics

- Success metric: `generation_stream_owner_mode` reports executor-owned mode for Python MLX-backed text/VLM paths.
- Stability metric: `stream_sync_fallback_count` remains zero in deterministic tests and is observable when cleanup must use fallback synchronization.
- Startup metric: `worker_thread_init_latency_ms` is non-negative and exported through `RuntimeStats`.
- Performance guard: issue #40 repeated-request TTFT targets are not claimed by this slice; the executor change must avoid obvious local TTFT regressions in targeted runtime probes before handoff.

## Implementation Result

Status: completed for the Python MLX text compatibility and MLX VLM stream ownership slice.

Implemented a shared `MLXRuntimeExecutor` in the Python worker, routed MLX text
load/generation and MLX VLM load/template/stream generation through it, and
implemented warmup for loaded generation runtimes. Runtime stats now publish the
stream owner mode, worker-thread initialization latency, and synchronization
fallback count. Swift control-plane observability projects those fields into
`python_worker.*` metrics from both OpenAI gateway and coordinator refresh paths.

The executor changes intentionally do not claim the full repeated-request TTFT
target from issue 40. This slice removes arbitrary gRPC-thread execution from
the Python MLX paths and adds the probes needed to validate any later TTFT
measurement work.

## Verification Results

- `make proto` passed.
- Focused Python worker tests passed: `100 passed in 0.64s`.
- Python changed-line coverage for touched worker source files: `98.70% (76/77)`.
- New executor file coverage: `98% (120/123)`.
- Focused Swift tests for OpenAIHandler, RequestCoordinator, and PythonBridge runtime stats passed.
- `make py-test` passed: `948 passed, 5 skipped, 2 warnings`.
- `make swift-test` passed on rerun. The first run hit one timing-sensitive RequestCoordinator disconnect-grace test; the same test passed standalone and the full command passed on rerun.
- `make integration-test` passed: `86 passed, 1 skipped in 1477.94s`.
