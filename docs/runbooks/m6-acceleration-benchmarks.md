# M6 Acceleration Benchmarks

## Purpose

Capture repository-owned benchmark evidence for the remaining M6 acceleration slices:

- active KV quantization acceleration (`M6.7`)
- sparse-prefill acceleration (`M6.8`)

Generated metrics JSON files are not meant to remain checked into the
repository. Write raw reports to a local or temporary output path, summarize the
important values in the relevant plan or architecture note, and archive raw JSON
that must remain reviewable in a GitHub issue. The historical TurboQuant Phase 2
JSON artifacts are archived in
[#46](https://github.com/Keith-CY/melix/issues/46), with former
`docs/metrics/...` paths preserved in the issue comments and in
`docs/metrics/README.md`.

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
- expected version for this baseline: `mlx_metal` `0.29.1` `mlx.metallib`
  matching `mlx-swift` `0.29.1`

`scripts/dev_up.py` auto-discovers a matching `mlx_metal` `mlx.metallib` from
the configured repo uv cache, nearby local environments, or the user's global uv
cache. During discovery it scans candidate `*.dist-info` directories with a
direct `mlx_metal-... .dist-info` prefix/suffix parse instead of a regex fallback,
so large Python environments avoid extra per-entry regex work while preserving
the directory-name fallback when `METADATA` lacks a `Version:` header. It rejects
incompatible auto-discovered candidates before startup. Use
`MELIX_SWIFT_MLX_METALLIB_PATH` only when the matching metallib lives outside
those caches.

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
export MELIX_SWIFT_MLX_METALLIB_PATH="/path/to/mlx_metal-0.29.1/mlx.metallib"
export MELIX_METRICS_DIR="${MELIX_METRICS_DIR:-/tmp/melix-phase2-metrics}"

mkdir -p "$MELIX_METRICS_DIR"

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
  --output "$MELIX_METRICS_DIR/phase2-affine-q4-preopt.json"
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
  --output "$MELIX_METRICS_DIR/phase2-active-kv-decode-guard-postopt.json"
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
  --output "$MELIX_METRICS_DIR/phase2-active-kv-fused-turboquant-candidate.json"
```

To backfill the fused-candidate probe block from an already captured real-model
post-run, use `--input-json`. This mode does not require a running stack and
writes the output before applying `--require-fused-turboquant`, so the current
fallback evidence is still preserved even though the command exits non-zero.

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py \
  --input-json "$MELIX_METRICS_DIR/phase2-active-kv-decode-guard-postopt.json" \
  --json \
  --require-fused-turboquant \
  --output "$MELIX_METRICS_DIR/phase2-active-kv-fused-turboquant-candidate.json"
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
- `active_kv_decode_model_eval_sync_avg_us`
- `active_kv_decode_sample_avg_us`
- `active_kv_decode_token_id_avg_us`
- `active_kv_decode_detokenize_avg_us`
- `active_kv_decode_stream_yield_avg_us`
- `active_kv_decode_summary_avg_us`
- `active_kv_turboquant_candidate_avg_us`
- `active_kv_decode_quantize_avg_us`
- `active_kv_fused_attention_avg_us`
- `active_kv_cache_update_avg_us`
- `active_kv_estimated_fp16_bytes`
- `active_kv_estimated_quantized_bytes`
- `active_kv_estimated_memory_savings_pct`

The active-KV row proves the acceleration mode can be requested and observed. Before any TurboQuant optimization work, preserve this affine q4 row as the pre-optimization baseline.

Look in `swift_worker_direct.active_kv_release_gates` for:

- `turboquant_fused_decode`

Expected gate fields:

- `status`
- `observed_kernel_paths`
- `observed_runtime_routes`
- `observed_runtime_block_reasons`
- `fallback_count`
- `candidate_dispatch_count`
- `candidate_eligibility_check_count`
- `decode_sample_total_us`
- `decode_token_id_total_us`
- `decode_detokenize_total_us`
- `decode_stream_yield_total_us`
- `decode_summary_total_us`
- `turboquant_candidate_total_us`
- `fused_attention_total_us`
- `cache_update_total_us`
- `decode_quantize_total_us`
- `estimated_memory_savings_pct`
- `worker_tps_overhead_pct`
- `failures`

The gate is the automation hook for preventing a fallback TurboQuant probe from
being presented as a fused-kernel optimization. It also requires
`worker_tps_overhead_pct <= 15` for the first fused milestone, so a non-fallback
candidate path is still blocked until it shows measured throughput improvement.

Look in `swift_worker_direct.active_kv_fused_candidate_probes` for:

- `turboquant_q4`

Expected fused-candidate fields:

- `status`
- `profile_label`
- `capability_evidence.status`
- `capability_evidence.runtime_path`
- `capability_evidence.smoke_tests`
- `runtime_evidence.release_gate_status`
- `runtime_evidence.observed_runtime_routes`
- `runtime_evidence.observed_runtime_block_reasons`
- `runtime_evidence.failures`
- `next_required_evidence`

This block separates smoke-proven custom Metal capability from runtime decode
evidence. `runtime_blocked` is expected while `decode_turboquant_q4` still
reports `active_kv_kernel_path = "fallback"` or the release gate fails. A
runtime candidate that dispatches the fused Metal kernel but misses the
throughput gate must also remain `runtime_blocked`.

Look in `swift_worker_direct.comparisons` for:

- `affine_q4_vs_baseline`

Expected comparison fields:

- `worker_tps_overhead_pct`
- `wall_tps_overhead_pct`
- `ttft_delta_ms`
- `total_ms_delta`
- `active_kv_decode_sample_avg_us`
- `active_kv_decode_token_id_avg_us`
- `active_kv_decode_detokenize_avg_us`
- `active_kv_decode_stream_yield_avg_us`
- `active_kv_decode_summary_avg_us`
- `active_kv_turboquant_candidate_avg_us`
- `active_kv_fused_attention_avg_us`
- `active_kv_cache_update_avg_us`
- `active_kv_decode_quantize_share_pct`
- `active_kv_estimated_memory_savings_pct`

The comparison block is the release-gate evidence for before/after active-KV optimization.

For the current decode hot-path probe run, `decode_affine_q4` and
`decode_turboquant_q4` both report `active_kv_decode_quantize_total_us = 0`
across all five repeats. The fused TurboQuant runtime route is connected
(`active_kv_kernel_path = "tq_mse_single"`, `active_kv_runtime_route = "routed"`,
and `active_kv_fallback_count = 0`), but the release gate can still fail on
throughput overhead. Inspect the per-bucket fields before selecting the next
optimization; in the 2026-05-01 local probe the largest buckets were model
completion/eval-sync, fused attention, and cache update, while detokenization and
stream yield were not material bottlenecks.

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
- the speculative-decode row records draft acceptance, rejection, fallback,
  `speculative_draft_propose_ms`, and `speculative_target_verify_ms` so live
  draft execution can be distinguished from baseline fallback
- TurboQuant optimization must not proceed until this pre-optimization report has been captured and attached to the implementation handoff
- fused TurboQuant optimization must not be released while
  `--require-fused-turboquant` fails
