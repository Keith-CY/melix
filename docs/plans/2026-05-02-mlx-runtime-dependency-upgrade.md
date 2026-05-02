# MLX Runtime Dependency Upgrade

## Goal

Upgrade Melix's Python and Swift MLX runtime stacks while keeping public HTTP,
protobuf, and OpenAI-compatible request or response shapes unchanged.

## Target Versions

| Component | Current state | Target |
| --- | --- | --- |
| Python `mlx` | locked to `0.31.1` | `>=0.31.2,<0.32` |
| Python `mlx-lm` | locked to `0.31.1` | `>=0.31.3,<0.32` |
| Python `mlx-vlm` | Git pin at `43b9b207...`, version `0.4.3` | PyPI `>=0.4.4,<0.5` |
| Python `mlx-audio` | `0.4.2` | unchanged |
| Swift `mlx-swift-lm` | vendored Melix-patched fork from upstream `2.29.3` | upstream `2.31.3` plus Melix patches |
| Swift `mlx-swift` | `0.29.1` | `0.31.3` |
| Swift `swift-transformers` | `1.1.x` | `1.2.x` |

`mlx-swift-lm` intentionally stays on the last 2.x tag. The 3.x release line is
a separate breaking API migration and is outside this change.

## Implementation Changes

- Update `services/mlx-worker-python/pyproject.toml` and `uv.lock` for the
  target Python MLX stack. Convert `mlx-vlm` from the Git source to a registry
  dependency.
- Keep the text/VLM `mlx` extra separate from the `mlx-audio 0.4.2` extras,
  because the current audio dependency line pins `mlx-lm 0.31.1`.
- Add lightweight runtime feature detection around Python `mlx-lm` and
  `mlx-vlm` calls so Melix only passes optional generation arguments when the
  installed runtime accepts them.
- Keep existing `SamplingConfig` as the source for `temperature`, `top_p`,
  `top_k`, `frequency_penalty`, `presence_penalty`, and `max_output_tokens`;
  do not add protocol fields.
- Resync `third_party/mlx-swift-lm` to upstream `2.31.3`, then reapply the
  Melix TurboQuant, fused q4 attention, Qwen3.5 hybrid-cache, and probe patches
  documented in `third_party/mlx-swift-lm/MELIX_PATCHES.md`.
- Update the Swift text worker package pins to `mlx-swift 0.31.3` and the
  matching 2.x `mlx-swift-lm` dependency surface.
- Update `scripts/dev_up.py` so automatic `mlx.metallib` discovery can map the
  Swift MLX package version to the compatible Python `mlx_metal` wheel version
  instead of requiring a literal tag match.

## Performance Probes And Success Metrics

- Swift decode and TurboQuant:
  - `swift_text.active_kv_kernel_path_code`
  - `swift_text.active_kv_runtime_route_code`
  - `swift_text.active_kv_fallback_count`
  - `swift_text.active_kv_decode_model_eval_sync_avg_us`
  - `worker_tps_overhead_pct` in Phase 2 metrics output
- Python VLM:
  - `image_feature_cache_hits`
  - `image_feature_cache_misses`
  - `multimodal_decode_mode`
  - `multimodal_fallback_reason`
  - `quantized_load_mode`
  - `quantized_load_fallback_reason`
- LoRA and model ops:
  - `mlx_lm_version` in existing LoRA evidence
  - training duration, tokens seen, tokens per second, and peak memory fields

The Qwen3.5 Swift TurboQuant smoke must keep the fused route non-fallback,
`active_kv_fallback_count = 0`, and a passing fused gate. Python VLM smokes
must show text-only VLM chat, single-image VLM, repeated-image cache evidence,
and explicit fallback reporting for unsupported video fast paths unless the
installed runtime exposes a compatible video generation surface.

## Verification

- `uv lock --upgrade-package mlx --upgrade-package mlx-lm --upgrade-package mlx-vlm`
- `uv sync --frozen --package melix-mlx-worker --extra mlx`
- `swift package resolve --package-path services/mlx-text-worker-swift`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_dev_up_script.py -q`
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests`
- `make proto`
- `make swift-test`
- `make py-test`
- `make integration-test`

Changed-scope coverage must be at least 95 percent where measurable. If a live
real-model probe cannot run in the local worktree, the handoff must include the
exact blocker and avoid making performance claims beyond the commands that ran.

## Known Risks

- `mlx-swift-lm` 2.31.3 uses Swift tools 6.1; local and CI builders must support
  that version or newer.
- Upstream `mlx-swift 0.31.3` currently reports MLX core `0.31.1` in its package
  metadata, so `dev_up` must accept the compatible `mlx_metal 0.31.1` metallib
  for that Swift package.
- Resyncing the vendored Swift runtime can conflict with Melix's local
  TurboQuant patches; those patches must be reapplied with focused tests before
  relying on real-model Phase 2 evidence.
