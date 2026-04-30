# Swift Text Decode Hot Path Probe Optimization Plan

## Context

This slice targets the Swift text worker decode path. The existing Phase 2
metrics pipeline already exposes active-KV, TurboQuant, eval-sync, cache-update,
and throughput probes. Historical TurboQuant work showed that decode bottlenecks
can move between model evaluation sync, fused attention dispatch, token
sampling, cache maintenance, and stream emission, so this work must stay
probe-driven.

## Goal

Optimize the Swift text worker text decode hot path through repeated
measure-then-change loops while preserving request behavior, stream ordering,
active-KV route reporting, and existing fallback semantics.

## Initial Scope

- `services/mlx-text-worker-swift/Sources/Core/Runtime/SwiftMLXBackend.swift`
- `services/mlx-text-worker-swift/Sources/Core/Runtime/TextRuntime.swift`
- `services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift`
- `services/mlx-text-worker-swift/Sources/Core/MetricsStore.swift`
- `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`
- `scripts/phase2_metrics_report.py`
- `services/mlx-worker-python/tests/test_phase2_metrics_report.py`
- `docs/runbooks/m6-acceleration-benchmarks.md`

If baseline evidence points into vendored TurboQuant kernels, a later small
slice may touch `third_party/mlx-swift-lm/Libraries/MLXLMCommon/` after tests
covering the specific kernel behavior fail first.

## Probe Strategy

The first pass should preserve decode behavior and add only missing timing
fields around the existing `makePreparedDecodeEvents(...)` loop:

- token sampling and token-id extraction
- detokenizer append and chunk production
- stream chunk yield
- model invocation wall time
- optional model eval-sync probe time
- active-KV cache quantization maintenance
- TurboQuant candidate eligibility and dispatch
- summary construction

The Phase 2 report must preserve these fields in active-KV decode rows and
comparisons so each optimization has before/after evidence.

## Optimization Loop

1. Run a baseline Phase 2 decode probe with active-KV q4 and TurboQuant q4.
2. Inspect the largest measured hot-path bucket.
3. Add or adjust focused tests for the chosen behavior.
4. Implement one small optimization that targets that bucket only.
5. Re-run the focused tests and the same probe command.
6. Repeat only when the next bottleneck is visible in the new probe output.

## Candidate Optimizations

The first optimization will be selected from baseline evidence, not assumed in
advance. Likely candidates are:

- avoid redundant per-token route eligibility checks after the cache route state
  is known;
- avoid unnecessary quantized-cache maintenance work when the decode cache is
  already in the desired active-KV state;
- reduce token-loop overhead around detokenization or stream event emission if
  those probes are unexpectedly large;
- only touch TurboQuant fused attention kernel code if route timing, lane
  counters, and throughput evidence identify it as the active bottleneck.

## Success Metrics

- Focused Swift tests for changed decode/probe behavior pass.
- Focused Python tests for Phase 2 report field preservation pass.
- Touched executable changed-line coverage is at least 95 percent where
  measurable.
- Probe output includes non-`N/A` timing for the newly instrumented decode
  buckets.
- Each optimization reports concrete before/after numbers for:
  - `decode_tokens_per_second`
  - `active_kv_decode_loop_total_us`
  - `active_kv_decode_model_avg_us`
  - `active_kv_decode_model_eval_sync_avg_us`
  - active-KV route, kernel path, fallback count, and TurboQuant gate status

## Verification Commands

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
  swift test --package-path services/mlx-text-worker-swift --enable-code-coverage \
  --filter 'WorkerScaffoldTests'

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
  uv run --project services/mlx-worker-python coverage run -m pytest \
  services/mlx-worker-python/tests/test_phase2_metrics_report.py -q

PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" \
  uv run --project services/mlx-worker-python python scripts/phase2_metrics_report.py \
  --json \
  --runtime-dir "$MELIX_RUNTIME_DIR" \
  --model-path "$MELIX_DEV_TEXT_MODEL_PATH" \
  --model-revision main \
  --decode-repeats 5 \
  --active-kv-profiles q4,turboquant-q4 \
  --skip-abort \
  --output "$MELIX_METRICS_DIR/swift-text-decode-hot-path.json"

git diff --check
```

## Metrics Report

Record the final touched-scope coverage, probe command, model id/path, raw
artifact path, and before/after metric deltas in this plan before handoff. If a
live real-model probe cannot run in this worktree, record `N/A` with the exact
blocker and keep the deterministic tests as the only completion claim.

### 2026-05-01 Results

Raw local artifacts:

- Baseline before this slice:
  `.runtime/sidecars/swift-decode-hotpath/metrics/baseline-phase2.json`
- First probe pass with new decode bucket fields:
  `.runtime/sidecars/swift-decode-hotpath/metrics/probe-pass1-phase2.json`
- Rejected fused quantizer runtime experiment:
  `.runtime/sidecars/swift-decode-hotpath/metrics/probe-fusedquant-env-phase2.json`
- Rejected adaptive lane-width experiment:
  `.runtime/sidecars/swift-decode-hotpath/metrics/probe-adaptive-lanes-phase2.json`
- Final retained probe run:
  `.runtime/sidecars/swift-decode-hotpath/metrics/final-phase2.json`

Model evidence:

- model id: `mlx-community/Qwen3-0.6B-4bit`
- model path:
  `/Users/ChenYu/.cache/huggingface/hub/models--mlx-community--Qwen3-0.6B-4bit/snapshots/73e3e38d981303bc594367cd910ea6eb48349da8`
- revision: `main`

Retained changes:

- Added active-KV decode probes for sampling, token-id extraction,
  detokenization, stream yield, summary construction, and TurboQuant candidate
  dispatch timing.
- Preserved the new fields in Phase 2 active-KV rows, comparisons, release
  gates, and fused-candidate runtime evidence.
- Scoped these active-KV-only decode probes away from baseline decode so probe
  timestamp collection does not perturb the baseline hot path.
- Added a head-dimension 128 fused q4 attention correctness test to cover the
  Qwen3-0.6B decode shape.

Rejected experiments:

- `MELIX_SWIFT_TURBOQUANT_FUSED_QUANTIZE=1` increased cache update and decode
  loop time in the local real-model probe, so the fused decode quantizer remains
  opt-in.
- Adaptive TurboQuant fused-attention lane width eliminated inactive lanes but
  regressed fused-attention timing and active decode throughput, so the fixed
  32-lane launch plan remains in place.

Selected TurboQuant q4 comparison metrics:

| Run | active worker TPS | worker overhead % | loop total us | fused avg us | cache update avg us | token id avg us |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 33.0 | 45.00 | 1,951,970 | 198.0 | 165.0 | N/A |
| First probe pass | 31.0 | 42.59 | 2,057,214 | 205.0 | 171.0 | 1,190.0 |
| Final retained | 36.0 | 43.75 | 1,790,641 | 188.0 | 155.0 | 994.0 |

Final gate bucket shares for `decode_turboquant_q4`:

- model eval-sync probe: 52.44%
- fused attention: 18.62%
- cache update: 15.62%
- token-id extraction: 3.57%
- sampling: 0.22%
- detokenization: 0.39%
- stream yield: 0.04%

The remaining release-gate blocker is still throughput overhead
(`worker_tps_overhead_pct=43.75`) rather than route fallback. The next
optimization should target model completion synchronization, fused attention, or
cache update cost; detokenization and stream yield are not material bottlenecks.

Coverage and verification:

- Swift touched-scope changed-line coverage: `100.00% (267/267)` across
  `TextDecodeEngine.swift`, `MetricsStore.swift`, `SwiftMLXBackend.swift`,
  `TextRuntime.swift`, and `WorkerScaffoldTests.swift`.
- Python touched-scope changed-line coverage: `100.00% (48/48)` across
  `scripts/phase2_metrics_report.py` and
  `services/mlx-worker-python/tests/test_phase2_metrics_report.py`.
- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests'`
  -> passed, 184 tests.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" COVERAGE_FILE="$(pwd)/.coverage.phase2-report" uv run --project services/mlx-worker-python --extra mlx coverage run --source=scripts,services/mlx-worker-python/tests -m pytest services/mlx-worker-python/tests/test_phase2_metrics_report.py -q`
  -> passed, 40 tests.
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests -q`
  -> passed, 1166 tests, 5 skipped.
- `swift test --package-path services/mlx-text-worker-swift`
  -> passed, 184 tests.
- `git diff --check` -> passed.
