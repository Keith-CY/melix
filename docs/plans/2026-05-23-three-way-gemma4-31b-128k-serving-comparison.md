# Three-Way Gemma 4 31B 128K Serving Comparison And Optimization Plan

## Goal

Compare Melix, OMLX, and SwiftLM with the same Gemma 4 31B 8-bit model through OpenAI-compatible streaming chat completions at long context, identify Melix's serving bottleneck, and optimize Melix until its measured serving performance is better than both peer runtimes for the agreed scenarios.

## Scope

- Clone and pin SwiftLM under `~/Documents/github/SwiftLM`.
- Refresh and pin OMLX under `~/Documents/github/omlx`.
- Work from an isolated Melix worktree based on current `origin/main`.
- Use one Gemma 4 31B 8-bit MLX model family across all three runtimes. The primary candidate is `mlx-community/gemma-4-31b-it-8bit` because SwiftLM's repository benchmark scripts name it directly. `unsloth/gemma-4-31b-it-MLX-8bit` is checked as a compatible fallback only if the primary model is unavailable.
- Measure OpenAI-compatible streaming `/v1/chat/completions` behavior rather than product-specific benchmark UIs.
- Include long-context scenarios with a 128k prompt target. Smaller smoke scenarios are allowed only as startup validation and are not allowed to replace the final 128k comparison.
- Capture benchmark metrics, memory snapshots, runtime acceleration state, control-plane metrics, commands, versions, and artifact paths.
- Optimize only Melix. OMLX and SwiftLM remain benchmark baselines except for documented build or launch fixes needed to run current upstream.

## Non-Goals

- This is not a model-quality evaluation.
- This does not change formal Melix API semantics unless a measured bottleneck requires a behavior-preserving serving-path change.
- This does not claim a win from tiny prompt sizes or one-off manual curl timings.

## Runtime Matrix

| Runtime | Source Path | Port | Runtime Isolation |
|---|---|---:|---|
| Melix | this worktree | 12441 | `MELIX_SERVICE_INSTANCE_NAME=swiftlm31b128k-melix`, worktree-local `.runtime/sidecars/...`, worktree-local `MELIX_HOME` |
| OMLX | `/Users/chenyu/Documents/github/omlx` | 18061 | repo-local `.runtime/gemma31b128k`, persistent TTY session |
| SwiftLM | `/Users/chenyu/Documents/github/SwiftLM` | 18062 | repo build output, persistent TTY session |

## Benchmark Matrix

Final comparison scenarios:

- Prompt token targets: `8192`, `32768`, `131072`.
- Output tokens: `128` for baseline latency and decode throughput.
- Concurrency: `1` and `2`.
- Repeats: at least `2` for 128k after smoke succeeds; increase to `3` if run time remains practical.
- Prompt profile: deterministic synthetic prompt with unique cold prompts by default.
- Streaming: required for all runtimes.
- Temperature: `0.0`.
- Timeout: long enough for 128k prefill, initially `3600` seconds per request group.

Smoke scenarios:

- Prompt token target `1024`.
- Output tokens `16`.
- Concurrency `1`.
- Repeats `1`.

Smoke results only validate startup, endpoint compatibility, and model identity. They do not satisfy the user's long-context benchmark requirement.

## Measurement Points

- Per request: HTTP status, error payload, TTFT, total latency, decode latency, streamed chunk count, completion token count, decode tok/s, prompt token estimate or endpoint usage, group elapsed time.
- Per scenario: median and p95 TTFT, median and p95 total latency, median decode tok/s, median aggregate output tok/s, error count.
- Memory: baseline, after model load, during peak request, after benchmark, per-process RSS, and system memory pressure.
- Acceleration state:
  - Melix control-plane metrics including scheduler batching, VLM text batch generator, `http.ttfd_ms`, and runtime fallback or blocked reason codes.
  - OMLX `/health`, loaded-model memory, batching/concurrency settings where exposed.
  - SwiftLM `/health` and `/metrics` when available, with launch flags such as `--ctx-size`, `--prefill-size`, `--turbo-kv`, `--stream-experts`, and `--parallel`.
- Reproducibility: commits, build commands, launch commands, ports, model snapshot paths, artifact directory, environment notes.

## Bottleneck Diagnosis Flow

1. Verify the exact 8-bit model exists locally or download it into the Hugging Face cache.
2. Build each runtime and start exactly one service at a time if memory pressure requires isolation; otherwise keep three services on separate ports.
3. Run smoke preflight against `/v1/models`, `/health`, and one short streaming request for each runtime.
4. Run the three-way benchmark harness and preserve raw observations after every scenario.
5. Compare Melix against the faster peer per scenario. A peer win is meaningful only when both sides have zero request errors.
6. Attribute Melix gaps by mapping benchmark symptoms to Melix metrics:
   - TTFT gap: gateway overhead, request shaping, queue wait, model loading, prompt rendering, prefill chunking.
   - Decode tok/s gap: worker decode loop, stream assembly, MLX/VLM backend choice, quantized KV settings.
   - Concurrency aggregate gap: scheduler admission, continuous batching, Python VLM text-only batch path, executor serialization.
   - 128k-only gap: KV cache strategy, long-context prefill chunking, memory pressure, disk-backed cache behavior.
7. Implement one Melix optimization slice at a time with a failing focused test or reproducible benchmark assertion before production code.
8. Re-run the smallest scenario that proves the bottleneck moved, then re-run the 128k matrix before claiming improvement.

## Success Criteria

Melix is considered better than OMLX and SwiftLM for this task only if:

- Every final scenario completes with zero Melix request errors.
- Melix median total latency is lower than both OMLX and SwiftLM for each final scenario, or the comparison report explicitly records a user-approved tie-breaker metric.
- Melix median TTFT is no worse than the best peer by more than 3 percent for each final scenario.
- Melix median decode tok/s and aggregate tok/s are higher than both peers for each final scenario.
- The report includes memory and acceleration evidence, not only request timing tables.

## Verification Commands

Use focused commands as the touched scope becomes clear. Expected minimum verification before handoff:

```bash
git diff --check
python3 scripts/three_way_serving_compare.py --help
python3 scripts/three_way_serving_compare.py --dry-run --output .runtime/three-way-gemma31b128k/dry-run
make swift-test
make py-test
make integration-test
```

If the final change is benchmark-script-only, replace full gates only with explicit evidence that no runtime behavior changed plus focused script tests and `N/A` metrics rationale. If Melix runtime behavior changes, run the relevant Swift/Python focused tests, changed-line coverage for touched executable files, and the final benchmark matrix.

## Artifact Layout

All generated benchmark evidence should live under:

```text
.runtime/three-way-gemma31b128k/<run-id>/
```

Export the final stakeholder-readable report bundle to:

```text
~/Downloads/three-way-gemma31b128k-<timestamp>/
```

## Current Setup Evidence

- Melix worktree: `/Users/chenyu/Documents/github/melix/.runtime/worktrees/swiftlm-31b-128k-benchmark`
- Melix branch: `codex/swiftlm-31b-128k-benchmark`
- Melix base commit: `c38b8b81891b0d3c97b17a59911c02e7be5645a2`
- OMLX path: `/Users/chenyu/Documents/github/omlx`
- OMLX refreshed commit: `2f2f5087a9c9a6ef71fa165da4a299bd19d4d5b4`
- SwiftLM path: `/Users/chenyu/Documents/github/SwiftLM`
- SwiftLM cloned commit: `d5a9d11`
- Host: Apple M3 Ultra, 256 GiB unified memory, about 306 GiB available disk at plan time.
- Local cache currently has complete `unsloth/gemma-4-31b-it-UD-MLX-3bit`; the 31B 8-bit model must still be verified or downloaded before benchmark execution.

## 2026-05-23 Interim Findings

- SwiftLM was cloned under `/Users/chenyu/Documents/github/SwiftLM` and built at commit `d5a9d118910142ce092fc4357777884a61bb8137`.
- The shared 8-bit model used for live work was `mlx-community/gemma-4-31b-it-8bit` at snapshot `fe92291011fc698452920c0b558b52f790dff711`.
- Initial Melix behavior routed text-only Gemma 4 VLM requests through the Python VLM path and did not produce a first token within a practical 128k-window wait. Melix now registers a Swift text companion for Gemma 4 text-only VLM requests and keeps media requests on the Python VLM path.
- The first Swift text companion 128k attempt failed before serving because the companion inherited a conservative catalog context limit instead of the nested Hugging Face `text_config.max_position_embeddings`. `BootstrapWorkerPreparation` now raises generic VLM/text worker specs to the larger local `config.json` context value when available.
- After the context-limit fix, a direct Melix streaming probe using the 224k synthetic prompt target no longer returned `context_limit_exceeded`. It kept the HTTP stream alive past `580.983s` without a token delta and was then interrupted. This is already slower than the prior SwiftLM 128k-class peer run, which produced first token at `535569.69ms` for the same model family and long prompt profile.
- Client interruption did not stop the active Swift text worker prefill promptly. The worker continued consuming CPU after the benchmark/probe process was interrupted, requiring `scripts/dev_down.sh` to clear the abandoned work.
- Gemma 4 text full-attention layers used the default `StandardKVCache.step = 256`, while the already-supported Gemma 3 text implementation raises global/full-attention cache growth to `1024`. With the current 512-token Swift text prefill window, the Gemma 4 default can force full-attention KV storage growth on every prefill chunk at 128k context instead of amortizing realloc/copy work. Gemma 4 text now sets full-attention cache growth to `max(1024, sliding_window)` and keeps sliding layers on `RotatingKVCache(maxSize: sliding_window, keep: 0)`.
- Focused regression evidence: `WorkerScaffoldTests/testGemma4TextFullAttentionCacheUsesLongContextGrowthStep` first failed with both full-attention caches reporting `step = 256`, then passed after the Gemma 4 cache growth change.

Current bottleneck conclusion: Melix is no longer blocked by Gemma 4 loading, text-only routing, or context-limit rejection. The remaining blocker to beating SwiftLM/OMLX is the Swift Gemma 4 long-context prefill path, plus missing prompt-prefill cancellation. Melix must optimize that path before claiming success against the user's 128k requirement.
