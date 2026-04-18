# M6 Acceleration Benchmarks

## Purpose

Capture repository-owned benchmark evidence for the remaining M6 acceleration slices:

- active KV quantization acceleration (`M6.7`)
- sparse-prefill acceleration (`M6.8`)

## Prerequisites

- a running local Melix stack with exported runtime environment
- reachable Swift text worker and control-plane sockets
- writable metrics export paths from the active stack

Start the local stack before running this benchmark sequence.

The repository shared real small text model convention remains:

- model id: `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
- preferred local path env: `MELIX_PHASE8_REAL_SMALL_MODEL_PATH`
- fallback local sources: existing `MELIX_MANAGED_MODEL_ROOT` import, then the local Hugging Face cache

That convention is used by the Phase 8 real-model E2E path. The current Swift
MLXLLM dependency does not support `model_type = qwen3_5`, so the Swift
active-KV pre-optimization baseline uses this Swift-supported real model:

- model id: `mlx-community/Qwen3-0.6B-4bit`
- revision: `main`

When the Python worker environment contains a newer MLX wheel, start the Swift
text worker with a metallib matching the pinned Swift MLX runtime:

- env: `MELIX_SWIFT_MLX_METALLIB_PATH`
- expected version for this baseline: MLX `0.24.2` `mlx.metallib`

Swift custom Metal smoke tests use the same runtime requirement. The
`WorkerScaffoldTests/testTurboQuantMetalCapabilityRuns...` tests create a
temporary `default.metallib` symlink from a discoverable local MLX
`mlx.metallib`; they skip when no local metallib is available and dispatch the
custom `MLXFast.metalKernel(...)` identity, packed-q4 value decode, and
packed-q4 score plus softmax plus value kernels when one is present.

## Command

```bash
export MELIX_RUNTIME_DIR="${MELIX_RUNTIME_DIR:-/tmp/melix-phase2-qwen3-preopt}"
export MELIX_HTTP_PORT="${MELIX_HTTP_PORT:-11438}"
export MELIX_DEV_TEXT_MODEL_PATH="/path/to/mlx-community/Qwen3-0.6B-4bit"
export MELIX_SWIFT_MLX_METALLIB_PATH="/path/to/mlx-0.24.2/mlx.metallib"

bash scripts/dev_up.sh --prefer-built

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py \
  --json \
  --runtime-dir "$MELIX_RUNTIME_DIR" \
  --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" \
  --model-path "$MELIX_DEV_TEXT_MODEL_PATH" \
  --model-revision main \
  --decode-repeats 5 \
  --active-kv-profiles q4 \
  --skip-abort \
  --output docs/metrics/phase2-affine-q4-preopt.json
```

After a decode-path optimization, run the same command family with both affine q4
and the TurboQuant probe profile:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py \
  --json \
  --runtime-dir "$MELIX_RUNTIME_DIR" \
  --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" \
  --model-path "$MELIX_DEV_TEXT_MODEL_PATH" \
  --model-revision main \
  --decode-repeats 5 \
  --active-kv-profiles q4,turboquant-q4 \
  --skip-abort \
  --output docs/metrics/phase2-active-kv-decode-guard-postopt.json
```

After a fused TurboQuant candidate exists, run the same report with the explicit
release gate enabled. The current fallback implementation is expected to fail
this command.

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py \
  --json \
  --runtime-dir "$MELIX_RUNTIME_DIR" \
  --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" \
  --model-path "$MELIX_DEV_TEXT_MODEL_PATH" \
  --model-revision main \
  --decode-repeats 5 \
  --active-kv-profiles q4,turboquant-q4 \
  --skip-abort \
  --require-fused-turboquant \
  --output docs/metrics/phase2-active-kv-fused-turboquant-candidate.json
```

To backfill the fused-candidate probe block from an already captured real-model
post-run, use `--input-json`. This mode does not require a running stack and
writes the output before applying `--require-fused-turboquant`, so the current
fallback evidence is still preserved even though the command exits non-zero.

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py \
  --input-json docs/metrics/phase2-active-kv-decode-guard-postopt.json \
  --json \
  --require-fused-turboquant \
  --output docs/metrics/phase2-active-kv-fused-turboquant-candidate.json
```

## Evidence To Inspect

### Active KV Quantization

Look in `swift_worker_direct.decode` for the row with:

- `label = "decode_affine_q4"`

Expected evidence fields:

- `ttft_ms`
- `total_ms`
- `tokens_per_second`
- `worker_decode_tokens_per_second`
- `active_kv_quantization_ratio`
- `active_kv_backend`
- `active_kv_kernel_path`
- `active_kv_prefill_quantize_us`
- `active_kv_decode_model_avg_us`
- `active_kv_decode_quantize_avg_us`
- `active_kv_estimated_fp16_bytes`
- `active_kv_estimated_quantized_bytes`
- `active_kv_estimated_memory_savings_pct`

The active-KV row proves the acceleration mode can be requested and observed. Before any TurboQuant optimization work, preserve this affine q4 row as the pre-optimization baseline.

Look in `swift_worker_direct.active_kv_release_gates` for:

- `turboquant_fused_decode`

Expected gate fields:

- `status`
- `observed_kernel_paths`
- `fallback_count`
- `decode_quantize_total_us`
- `estimated_memory_savings_pct`
- `worker_tps_overhead_pct`
- `failures`

The gate is the automation hook for preventing a fallback TurboQuant probe from
being presented as a fused-kernel optimization.

Look in `swift_worker_direct.active_kv_fused_candidate_probes` for:

- `turboquant_q4`

Expected fused-candidate fields:

- `status`
- `profile_label`
- `capability_evidence.status`
- `capability_evidence.runtime_path`
- `capability_evidence.smoke_tests`
- `runtime_evidence.release_gate_status`
- `runtime_evidence.failures`
- `next_required_evidence`

This block separates smoke-proven custom Metal capability from runtime decode
evidence. `runtime_blocked` is expected while `decode_turboquant_q4` still
reports `active_kv_kernel_path = "fallback"` or the release gate fails.

Look in `swift_worker_direct.comparisons` for:

- `affine_q4_vs_baseline`

Expected comparison fields:

- `worker_tps_overhead_pct`
- `wall_tps_overhead_pct`
- `ttft_delta_ms`
- `total_ms_delta`
- `active_kv_decode_quantize_share_pct`
- `active_kv_estimated_memory_savings_pct`

The comparison block is the release-gate evidence for before/after active-KV optimization.

For the current decode-guard post-run, `decode_affine_q4` and
`decode_turboquant_q4` both report `active_kv_decode_quantize_total_us = 0`
across all five repeats. The end-to-end throughput overhead remains about 43
percent, so the remaining optimization target is the quantized attention model
call and fused kernel path, not decode-loop quantization maintenance.

For any future fused TurboQuant claim, `decode_turboquant_q4` must report:

- `active_kv_backend = "turboquant"`
- `active_kv_kernel_path != "fallback"`
- `active_kv_fallback_count = 0`
- `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode.status = "pass"`
- measured throughput overhead improvement against the frozen affine q4 pre-run

### Sparse Prefill

Look in `swift_worker_direct.prefill` for the row with:

- `label = "prefill_sparse"`

Expected evidence fields:

- `accelerated_prefill_gain_pct`
- `sparse_prefill_accepted_skip_count`
- `sparse_prefill_rejected_opportunity_count`
- `sparse_prefill_protected_region_count`
- `worker_prefill_ms`

The sparse-prefill row proves structured prompts can trigger sparse skipping while protected prompt regions remain observable in the same report.

## Acceptance

- the report contains a `decode_affine_q4` row with non-`N/A` active-KV probe fields
- the report contains an `affine_q4_vs_baseline` comparison with non-`N/A` throughput overhead and memory-savings fields
- the report contains a `prefill_sparse` row with non-`N/A` sparse-prefill counters
- baseline, accelerated-prefill, sparse-prefill, speculative-decode, and active-KV rows are emitted from one repository-owned command
- TurboQuant optimization must not proceed until this pre-optimization report has been captured and attached to the implementation handoff
- fused TurboQuant optimization must not be released while
  `--require-fused-turboquant` fails
