# M6.7 KV-Cache Quantization Acceleration

## Goal

Add feature-flagged KV-cache quantization acceleration so memory pressure can be reduced on long-running decode paths with measurable trade-offs.

## Scope

- add runtime policy for KV-cache quantization acceleration
- preserve correctness-first behavior for the default path
- expose metrics for memory reduction and throughput impact

## Files

- update `services/mlx-text-worker-swift/Sources/Core/Inference/`
- update `services/mlx-text-worker-swift/Sources/Core/Runtime/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`

## Implementation Notes

- acceleration should remain opt-in and benchmarked
- runtime metrics must distinguish active-path acceleration from storage-boundary quantization
- keep the policy surface compatible with per-model acceleration settings
- probe coverage must land before any TurboQuant kernel or cache optimization work
- the pre-optimization affine q4 baseline must be captured from the same report command used for post-optimization comparison
- active-KV reports should include backend, kernel-path, model-call timing, quantization timing, estimated KV bytes, and memory-savings probes
- real-model helper code must reuse the repository's Phase 8 small-text-model convention instead of duplicating Qwen3.5 fixture resolution
- the shared real-model helper should keep deterministic test fixtures local, while allowing benchmark commands to resolve an existing local Hugging Face cache or managed model path before falling back to the Hub id
- Phase 8 real-model E2E uses `mlx-community/Qwen3.5-0.8B-OptiQ-4bit`; the Swift active-KV pre-optimization baseline currently uses `mlx-community/Qwen3-0.6B-4bit` because the pinned Swift MLXLLM registry does not support `model_type = qwen3_5`
- live Swift MLX model probes must run with a metallib matching the Swift MLX dependency; `MELIX_SWIFT_MLX_METALLIB_PATH` should point at an MLX 0.24.2 `mlx.metallib` when the Python worker environment carries a newer MLX wheel
- the first post-baseline optimization removes redundant decode-side quantization maintenance calls once the cache is already quantized; the post-run evidence is `docs/metrics/phase2-active-kv-decode-guard-postopt.json`
- `turboquant-q4` must be treated as a measured fallback profile until the kernel path is no longer `fallback`; true TurboQuant optimization requires a fused decode kernel path
- fallback `turboquant-q4` probes must fail the explicit fused release gate in `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode`
- the report CLI supports `--require-fused-turboquant`; use it for fused-kernel candidates, not for the current fallback post-run
- architecture notes for the fused-kernel route live in `docs/architecture/2026-04-18-turboquant-kv-cache-optimization.md`

## Verification

- `make swift-test`
- `make integration-test`
- `MELIX_SWIFT_MLX_METALLIB_PATH=/path/to/mlx-0.24.2/mlx.metallib MELIX_DEV_TEXT_MODEL_PATH=/path/to/mlx-community/Qwen3-0.6B-4bit bash scripts/dev_up.sh --prefer-built`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py --json --runtime-dir "$MELIX_RUNTIME_DIR" --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" --model-path /path/to/mlx-community/Qwen3-0.6B-4bit --model-revision main --decode-repeats 5 --active-kv-profiles q4 --skip-abort --output docs/metrics/phase2-affine-q4-preopt.json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py --json --runtime-dir "$MELIX_RUNTIME_DIR" --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" --model-path /path/to/mlx-community/Qwen3-0.6B-4bit --model-revision main --decode-repeats 5 --active-kv-profiles q4,turboquant-q4 --skip-abort --output docs/metrics/phase2-active-kv-decode-guard-postopt.json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py --json --runtime-dir "$MELIX_RUNTIME_DIR" --http-prompt "Continue this sentence with five short words: Melix measures cache speed by" --model-path /path/to/mlx-community/Qwen3-0.6B-4bit --model-revision main --decode-repeats 5 --active-kv-profiles q4,turboquant-q4 --skip-abort --require-fused-turboquant --output docs/metrics/phase2-active-kv-fused-turboquant-candidate.json`
- inspect `swift_worker_direct.decode[]` for `label = "decode_affine_q4"`
- inspect `swift_worker_direct.decode[]` for `label = "decode_turboquant_q4"` and require `active_kv_kernel_path != "fallback"` before claiming fused TurboQuant
- inspect `swift_worker_direct.active_kv_release_gates.turboquant_fused_decode`; current fallback probes should report `status = "fail"`, while fused candidates must report `status = "pass"`
- inspect `swift_worker_direct.comparisons.affine_q4_vs_baseline` for throughput overhead, TTFT delta, quantization share, and estimated memory savings
- preserve the emitted JSON as the affine q4 pre-optimization baseline before making TurboQuant kernel changes

## Acceptance

- KV-cache quantization acceleration can be enabled through explicit policy
- memory and throughput effects are measurable and benchmarked
- optimization work is blocked until the report contains non-`N/A` baseline and affine q4 decode rows plus an affine-vs-baseline comparison
- any later TurboQuant profile must be compared against both baseline and affine q4 using the same probe fields
- true TurboQuant remains incomplete until a post-run JSON shows the TurboQuant profile on a non-fallback fused kernel path with measured throughput overhead improvement
- true TurboQuant remains blocked until `--require-fused-turboquant` exits zero on the fused candidate report
