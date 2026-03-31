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

## Command

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py --json
```

## Evidence To Inspect

### Active KV Quantization

Look in `swift_worker_direct.decode` for the row with:

- `label = "decode_active_kv_quantized"`

Expected evidence fields:

- `ttft_ms`
- `total_ms`
- `tokens_per_second`
- `worker_decode_tokens_per_second`
- `active_kv_quantization_ratio`

The active-KV row proves the acceleration mode can be requested, observed, and compared against the baseline and speculative decode rows in the same report.

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

- the report contains a `decode_active_kv_quantized` row with a non-`N/A` `active_kv_quantization_ratio`
- the report contains a `prefill_sparse` row with non-`N/A` sparse-prefill counters
- baseline, accelerated-prefill, sparse-prefill, speculative-decode, and active-KV rows are emitted from one repository-owned command
