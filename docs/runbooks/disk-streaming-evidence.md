# Disk Streaming Evidence

## Purpose

Run the repository-owned smoke workflow for the current M11.4 disk-streaming surface without
claiming SSD-backed execution support that does not yet exist.

Today Melix can measure truthfully:

- a RAM-resident benchmark baseline
- typed unsupported-path evidence for `prefer_disk`
- typed unsupported-path evidence for `require_disk`

Today Melix cannot measure truthfully:

- SSD restore latency
- SSD footprint
- disk-streaming throughput deltas under live execution

Those future metrics remain placeholders until the runtime implements real disk-backed execution.

## Preconditions

- `make bootstrap` has completed successfully
- Swift toolchain is available locally
- both worker sockets are reachable, either through the repository integration helper or a local
  development stack

## Smoke Command

The canonical smoke command is:

```bash
swift run --package-path "$(pwd)" melix-disk-streaming-smoke --json
```

Optional model selection:

```bash
swift run --package-path "$(pwd)" melix-disk-streaming-smoke \
  --model-id melix-dev-text \
  --json
```

The command talks directly to the local control-plane client surface. It does not shell out to
`melix bench run`.

## Local Stack Setup

For repository-owned verification, the simplest path is the integration helper stack:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx pytest \
  tests/integration/test_disk_streaming_smoke.py -q
```

For manual runs against a local development stack, provide the worker socket paths:

```bash
export MELIX_REPO_ROOT="$(pwd)"
export MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH=/tmp/melix-swift.sock
export MELIX_WORKER_SOCKET_PATH=/tmp/melix-python.sock
export HOME="$(pwd)/.swift-home"
export CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex"

swift run --package-path "$(pwd)" melix-disk-streaming-smoke --json
```

## Output Contract

The JSON report contains:

- `baseline`
  - RAM-resident benchmark report path
  - benchmark metrics such as `bench.smoke.ttft_ms` and `bench.smoke.tokens_per_second`
- `streamingPreferDisk`
  - requested mode, effective mode, typed error code, transition reason, and cache compatibility
- `streamingRequireDisk`
  - same fields for the stricter disk requirement path
- `capability`
  - whether the runtime actually supports disk streaming
- `futureMetrics`
  - explicit placeholders for blocked SSD-backed metrics

Expected interpretation today:

- `baseline` should contain usable benchmark metrics
- `streamingPreferDisk.errorCode` should be `disk_streaming_unsupported`
- `streamingRequireDisk.errorCode` should be `disk_streaming_unsupported`
- `capability.runtimeSupportsDiskStreaming` should be `false`
- every `futureMetrics` value should be `unavailable_until_runtime_support`

## Operator Guidance

Use this smoke command when you need to answer:

- does the current runtime still produce a valid RAM baseline?
- do disk-streaming requests fail explicitly and typefully?
- what cache compatibility state is visible to operators for unsupported disk modes?

Do not use this smoke command to claim:

- SSD-backed execution is working
- SSD restore latency is below a threshold
- disk-backed throughput is better or worse than RAM

If the smoke command stops returning typed `disk_streaming_unsupported`, that is a meaningful
runtime change and should trigger a review of the runbook, release gates, and M11.4 acceptance
criteria.
