# OMLX And Melix Serving Benchmark Comparison

## Goal

Create a repeatable serving benchmark that compares the local OMLX checkout at
`~/Documents/github/omlx` with the current Melix worktree so Melix optimization
work can be routed from measured evidence instead of subjective latency checks.

## Scope

- Compare both systems through their OpenAI-compatible streaming
  `/v1/chat/completions` endpoint.
- Use the same prompt profile, generation length, temperature, repeat count, and
  concurrency level for both endpoints.
- Persist raw request observations, machine-readable summaries, CSV summaries,
  and a Markdown optimization brief.
- Stage artifacts in a worktree-local temporary directory before exporting the
  completed bundle to the operator-selected export directory.

This plan does not compare each product's internal admin benchmark workflow.
Those workflows use different metric schemas and cache assumptions, so they are
not a fair source for direct Melix optimization deltas.

## Runtime Inputs

- Melix base URL, normally `http://127.0.0.1:<melix-port>/v1`.
- Melix model id accepted by the Melix OpenAI-compatible endpoint.
- OMLX base URL, normally `http://127.0.0.1:8000/v1`.
- OMLX model id accepted by the OMLX OpenAI-compatible endpoint.
- Synthetic prompt token targets, generation length, repeat count, concurrency
  values, and cache profile.
- Optional endpoint-specific HTTP headers for local authentication.

## Measurement Points

- Endpoint preflight status from `GET /v1/models`.
- Per-request HTTP status, error payload, TTFT, total latency, streamed chunk
  count, completion character count, prompt token count when reported by the
  endpoint, completion token count when reported by the endpoint, and decode
  tokens per second.
- Per-scenario error rate, median and p95 latency, median decode throughput, and
  aggregate output throughput for concurrent groups.
- Comparison hints that route Melix regressions to likely optimization areas:
  gateway or queue overhead, prefill/runtime preparation, decode throughput,
  streaming assembly, and continuous batching behavior.

## Fairness Rules

- Use streaming requests for both systems; non-streaming requests are out of
  scope for this comparison.
- Run cold-unique prompts by default so prior cache state does not dominate the
  result. A repeated-prompt profile can be used later to study cache reuse.
- Treat endpoint-reported token usage as authoritative when present. If usage is
  absent, report estimated token counts separately and mark the estimate source.
- Do not present the comparison as a model-quality evaluation. The benchmark
  measures serving behavior only.

## Verification

- Unit tests for SSE parsing, request summarization, comparison hint generation,
  and artifact writing.
- Dry-run command that validates scenario construction without requiring either
  local server to be running.
- Preflight-only command against both real endpoints before any long benchmark
  run.

## Current Live Evidence

- An isolated OMLX environment was created under `.runtime/omlx-venv` and served
  the local Hugging Face cache on `http://127.0.0.1:18000/v1`.
- A named Melix development instance was started with
  `MELIX_SERVICE_INSTANCE_NAME=omlx-melix-compare`,
  `MELIX_HTTP_PORT=12438`, worktree-local `MELIX_RUNTIME_DIR`, and
  worktree-local `MELIX_HOME`.
- The first successful live comparison bundle was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-warm-comparison` and exported to
  `~/Downloads/live-gemma26b-warm-comparison`.
- That bundle used the same underlying Gemma 4 26B A4B 4-bit MLX snapshot
  through both OpenAI-compatible streaming endpoints. Both endpoints completed
  all 36 requests without errors.

## Initial Findings

- Melix completed every request but trailed OMLX on median TTFT in all measured
  scenarios. The largest measured gap was the 512-token prompt at concurrency 1:
  Melix median TTFT was 994.56 ms and OMLX median TTFT was 244.84 ms.
- Melix median decode throughput was lower in all measured scenarios. At
  concurrency 1, Melix measured about 70-72 tokens/s while OMLX measured about
  109-111 tokens/s.
- Melix aggregate output throughput under concurrency 2 was lower than OMLX:
  43.23 vs 98.96 tokens/s for the 128-token prompt, and 39.65 vs 85.06
  tokens/s for the 512-token prompt.
- The first optimization probes should focus on Melix prefill/TTFT accounting,
  worker decode loop settings, streaming cadence, and concurrency batching or
  admission behavior.

## Optimization Target

- Treat "at most 10% behind OMLX" as a per-scenario serving gate on the
  artifact summary: Melix median TTFT and median total latency must be no more
  than 1.10x the matching OMLX value, and Melix median decode throughput plus
  aggregate output throughput must be at least 0.90x the matching OMLX value.
- Keep the comparison scoped to successful streaming requests. Any non-zero
  error count in either endpoint invalidates that scenario for the completion
  audit until rerun.
- Re-run the same 128-token and 512-token prompt scenarios at concurrency 1 and
  2 after each material serving change so improvements are tied to artifacts,
  not local perception.

## First Optimization Slice

- Remove avoidable warm-request control-plane work from the text serving path:
  text requests for models already present in the catalog should not force a
  registry rescan, and requests for models with an existing dispatch handle
  should not build or execute an eviction plan before returning that handle.
- Preserve discovery behavior for newly activated or missing registry models by
  keeping the forced registry rescan when the requested model is absent from the
  catalog or when its runtime cache metadata is marked missing.
- Align Melix's VLM runtime dependency with the OMLX comparison environment by
  moving the `mlx-vlm` optional dependency from the 0.4 line to the 0.5 line,
  then validating with the lockfile and VLM runtime tests before live serving
  measurement.
- Treat VLM stream fragments from `mlx-vlm` as delta text at the runtime
  boundary and expose cumulative `raw_text` to the shared stream assembler. This
  keeps parser monotonicity metrics stable while preserving token metadata for
  usage and parser receipts.
- Keep the stream assembler's plain-text fast path active when token metadata
  is present and no structural marker is in the delta. Token/logprob metrics and
  parser observations are still recorded, but ordinary VLM text chunks avoid
  unnecessary structural scans.
- For text-only requests routed through the VLM runtime, bypass
  `mlx-vlm` `stream_generate` and drive `generate_step` directly when the loaded
  backend exposes it. The fast path keeps the shared cumulative `raw_text`
  stream contract, preserves token metadata, and uses the tokenizer stop
  criteria before detokenizing each accepted token.
- Keep VLM text-only per-token telemetry out of the token hot path where the
  metric is not token-specific. The `generate_step` fast path caches the MLX
  peak-memory probe once per response stream and reuses it on emitted token
  events.

## Clean Worktree Evidence

- The related changes were isolated in the clean worktree
  `.runtime/worktrees/omlx-melix-serving-optimization` on branch
  `codex/omlx-melix-serving-optimization`, based on `origin/main`.
- The clean Melix comparison instance used
  `MELIX_SERVICE_INSTANCE_NAME=omlx-clean-compare`,
  `MELIX_HTTP_PORT=12439`, worktree-local `MELIX_RUNTIME_DIR`, worktree-local
  `MELIX_HOME`, and short `/tmp` worker socket paths to stay within the macOS
  Unix socket path limit.
- `live-gemma26b-clean-vlm-raw-smoke` completed one 128-token scenario against
  Melix `http://127.0.0.1:12439/v1` and OMLX
  `http://127.0.0.1:18000/v1` with 0 errors and
  `http.parser.non_monotonic_stream_count=0`.
- `live-gemma26b-clean-stream-fastpath-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-clean-stream-fastpath-comparison`
  and exported to `~/Downloads/live-gemma26b-clean-stream-fastpath-comparison`.
  It completed all 36 requests with both endpoint preflights passing.

## Clean Worktree Findings

- The VLM raw-text fix resolved the stream assembler monotonicity failure:
  Melix control-plane metrics reported
  `http.parser.non_monotonic_stream_count=0` after the smoke and full
  comparison runs.
- Warm-path registry and loader work is now bounded during the comparison:
  `control_plane.model_eviction_last_plan_size=0` after serving, and the new
  focused Swift tests cover both the registry-rescan skip and ready-handle
  reuse path.
- The stream assembler fast path stayed observable after the final comparison:
  `http.parser.stream_prefix_hold_chars=0`,
  `http.parser.stream_short_reply_flush_count=0`, and
  `http.parser.stream_interval_delta_flush_count=0` for the final sampled
  request.
- The remaining measured gap is now dominated by TTFT, end-to-end latency, and
  missing concurrent VLM batching rather than parser correctness. In the final
  clean comparison, Melix still reported `scheduler.continuous_batch_size=1`,
  while the benchmark continued to flag aggregate throughput regressions at
  concurrency 2.
- Follow-up code inspection found this to be an intentional control-plane and
  worker boundary, not measurement noise: `RequestCoordinator` forces
  multimodal background routes to `continuousBatchEligible=false` and
  `batchMaxSize=1`, while the Python VLM runtime drives `mlx-vlm`
  `stream_generate` through the single-owner `MLXRuntimeExecutor`.
- The OMLX comparison source uses the same single-MLX-executor safety model,
  but puts VLM requests through an engine scheduler and `BatchGenerator` after
  preprocessing vision/text embeddings. That explains why OMLX's concurrency-2
  streams first tokens for both requests at nearly the same time while Melix's
  current path emits one request first and the second roughly one decode window
  later.
- New control-plane metrics make this explicit for future comparisons:
  `scheduler.multimodal_continuous_batch_enabled`,
  `scheduler.multimodal_continuous_batch_requested_capacity`,
  `scheduler.multimodal_continuous_batch_effective_capacity`,
  `scheduler.multimodal_continuous_batch_blocked_count`, and
  `scheduler.multimodal_continuous_batch_blocked_reason_code`.
- `live-gemma26b-text-step-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-text-step-comparison` and
  exported to `~/Downloads/live-gemma26b-text-step-comparison` after adding the
  text-only `generate_step` fast path. It completed all 36 requests with both
  endpoint preflights passing and no request errors.
- Relative to `live-gemma26b-clean-stream-fastpath-comparison`, the text-only
  `generate_step` path improved Melix median TTFT from 618.02 ms to 528.51 ms
  for 128-token prompts at concurrency 1, from 1193.90 ms to 1097.32 ms for
  128-token prompts at concurrency 2, from 734.51 ms to 620.00 ms for
  512-token prompts at concurrency 1, and from 1383.48 ms to 1267.32 ms for
  512-token prompts at concurrency 2.
- The same comparison showed Melix median total latency improving from
  1409.21 ms to 1336.34 ms, 1997.18 ms to 1905.90 ms, 1549.56 ms to
  1427.97 ms, and 2204.53 ms to 2093.65 ms across the same four scenarios.
- The text-only fast path is a positive local optimization, but it does not
  close the OMLX gap. The exported metrics still reported
  `scheduler.multimodal_continuous_batch_enabled=0`,
  `scheduler.multimodal_continuous_batch_effective_capacity=1`, and
  `scheduler.multimodal_continuous_batch_blocked_reason_code=2`.
- A follow-up probe tried routing text-backed Gemma 4 text-only requests through
  an `mlx-lm` token-step adapter. `live-gemma26b-mlx-lm-step-comparison` was
  exported to `~/Downloads/live-gemma26b-mlx-lm-step-comparison` with 36
  successful requests, but it was not kept: the 128-token scenarios improved
  modestly while the 512-token scenarios regressed in median total latency,
  decode throughput, and aggregate throughput. This did not satisfy the
  per-scenario optimization gate.
- A control-plane hot-path follow-up removed synchronous cache/runtime
  observability refresh before worker dispatch and added a short per-route
  worker dispatch readiness cache. The cache only stores successful readiness
  probes and clears the entry if dispatch later reports the worker unavailable.
- The first connect-cache live smoke,
  `~/Downloads/live-gemma26b-connect-cache-smoke`, is invalid performance
  evidence. It used a Melix instance whose Python routes were not dispatchable,
  and all Melix requests failed quickly with `worker_unavailable`. Manual bridge
  handshake to the Python worker still succeeded, so the failure was treated as
  an instance and process-environment readiness problem rather than a serving
  comparison.
- A fresh instance, `MELIX_SERVICE_INSTANCE_NAME=omlx-connect-cache`,
  `MELIX_HTTP_PORT=12440`, worktree-local runtime and home directories, short
  `/tmp` sockets, and an explicit `MELIX_PYTHON_BRIDGE_EXECUTABLE` pointing at
  the existing Python environment restored `/health` to `ok` and reset the
  target Gemma model from `failed` to `discovered`.
- `live-gemma26b-connect-cache-smoke2` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-connect-cache-smoke2` and
  exported to `~/Downloads/live-gemma26b-connect-cache-smoke2`. It completed
  all 12 smoke requests with both endpoint preflights passing and no request
  errors.
- The connect-cache smoke reported
  `control_plane.worker_connect_cache_hit_count=3`, confirming the new
  readiness cache was exercised. It did not close the OMLX gap: Melix median
  TTFT was 1743.98 ms vs OMLX 203.99 ms for 128-token prompts at concurrency 1,
  and 699.52 ms vs OMLX 300.54 ms at concurrency 2. The exported metrics still
  reported `scheduler.multimodal_continuous_batch_enabled=0`,
  `scheduler.multimodal_continuous_batch_effective_capacity=1`, and blocked
  reason code `2`.
- `scripts/dev_up.py` now propagates a fixed Python bridge executable to the
  control-plane process when `MELIX_PYTHON_BRIDGE_EXECUTABLE` is set or when
  `UV_PROJECT_ENVIRONMENT/bin/python` exists. This keeps control-plane bridge
  calls from depending on per-request `uv run --extra mlx` resolution during
  local multi-worktree comparisons.
- The comparison script now supports optional warmup requests through
  `--warmup-requests`, `--warmup-prompt-token-target`, and
  `--warmup-max-tokens`. Warmup observations are written to `warmups.jsonl`,
  recorded in `manifest.json` and `summary.json`, and intentionally excluded
  from scenario summaries so serving measurements can separate warm model
  behavior from first-request load or bridge setup cost.
- `live-gemma26b-warmup-smoke` was exported to
  `~/Downloads/live-gemma26b-warmup-smoke` as a tool-validation artifact, but it
  is invalid performance evidence. Melix returned `model_listed=false` during
  preflight and every measured Melix request failed with `model_not_ready`; the
  script was tightened afterward so a 200 `/v1/models` response only passes
  preflight when the requested model id is present.
- The comparison script now also supports `--preflight-wait-seconds` and
  `--preflight-retry-interval-seconds`. These options repeatedly check
  `/v1/models` until every endpoint lists the requested model or the wait
  budget expires. Expired preflight remains a failure unless the operator passes
  `--allow-failed-preflight`.
- `scripts/dev_up.py` now uses the configured `MELIX_PYTHON_BRIDGE_EXECUTABLE`
  or `UV_PROJECT_ENVIRONMENT/bin/python` for worker readiness probes and for
  the Python worker process itself. This avoids resolving the venv entrypoint to
  the underlying interpreter, which loses venv `site-packages`, and avoids
  triggering `uv run --extra mlx` dependency resolution that attempted to build
  `pyarrow==19.0.1` from source on Python 3.14 when `cmake` was unavailable.
- `preflight-wait-melix-fresh-home` was staged at
  `.runtime/omlx-melix-benchmark/preflight-wait-melix-fresh-home` as readiness
  evidence only. A fresh Melix home with `MELIX_HTTP_PORT=12442` listed the
  target Gemma model after 11 preflight attempts and 20.125 seconds; its
  registry snapshot discovered 11 Hugging Face cache models under
  `~/.cache/huggingface/hub`. No generation requests were run.
- `live-gemma26b-valid-warmup-smoke` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-valid-warmup-smoke` and exported
  to `~/Downloads/live-gemma26b-valid-warmup-smoke`. It used
  `--warmup-requests 1` and `--preflight-wait-seconds 30`; both endpoint
  preflights passed on the first attempt and all 6 measured requests completed
  without errors.
- In that valid warm smoke, warmup observations were isolated in
  `warmups.jsonl` and excluded from scenario summaries. The measured 128-token
  prompt / 32-token output sample still showed Melix behind OMLX: median TTFT
  was 276.56 ms vs 153.14 ms at concurrency 1 and 715.55 ms vs 303.19 ms at
  concurrency 2; median aggregate output throughput was 57.76 tok/s vs
  142.94 tok/s at concurrency 2.
- The same run's Melix metrics reported
  `registry.discovered_model_count=11`,
  `control_plane.worker_connect_cache_hit_count=1`,
  `scheduler.multimodal_queue_delay_ms=803.15`,
  `scheduler.multimodal_continuous_batch_enabled=0`,
  `scheduler.multimodal_continuous_batch_effective_capacity=1`, and blocked
  reason code `2`.
- A follow-up micro-optimization moved the VLM text-only `generate_step`
  fast-path MLX peak-memory probe from each streamed token event to a lazy
  once-per-stream cache. The unit coverage asserts that emitted token events
  still carry the peak-memory value while the runtime probe is called only once
  for the stream.
- The invalid `worker_unavailable` probe was narrowed to two local setup
  hazards rather than a serving comparison regression: the deep worktree default
  Unix socket path exceeded macOS gRPC's path-length limit, and the worktree
  `.venv` was missing the newly required `mlx-vlm` package. `scripts/dev_up.py`
  now defaults worker sockets to short `/tmp` paths keyed by service instance
  and repo hash while still honoring explicit socket overrides; `dev_down.sh`
  removes the same default sockets.
- `OnDemandModelLoader` now preserves thrown worker request failures as worker
  rejections instead of collapsing every load exception into generic
  `worker_unavailable`. This made the real live failure visible as
  `load_failed: mlx-vlm is not installed` and keeps future benchmark artifacts
  actionable when the worker returns a structured bridge or runtime error.
- After launching a fresh instance with automatic short sockets and a
  `MELIX_PYTHON_BRIDGE_EXECUTABLE` that already had `mlx-vlm` installed,
  `live-gemma26b-auto-socket-peak-smoke` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-auto-socket-peak-smoke` and
  exported to `~/Downloads/live-gemma26b-auto-socket-peak-smoke`. It completed
  all six measured requests with zero errors and confirmed the new default
  socket layout works without manual `MELIX_WORKER_SOCKET_PATH` overrides.
- `live-gemma26b-auto-socket-peak-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-auto-socket-peak-comparison`
  and exported to `~/Downloads/live-gemma26b-auto-socket-peak-comparison`.
  It completed the full 36-request comparison with both endpoint preflights
  passing and zero request errors.
- In that full comparison, Melix median TTFT / total latency / aggregate
  throughput remained behind OMLX in the main gates: 128-token c1 was
  271.62 ms / 1053.87 ms / 75.67 tok/s vs OMLX
  151.88 ms / 728.11 ms / 114.68 tok/s; 128-token c2 was
  871.09 ms / 1644.73 ms / 82.87 tok/s vs OMLX
  420.42 ms / 1185.35 ms / 141.52 tok/s; 512-token c1 was
  398.75 ms / 1196.08 ms / 67.86 tok/s vs OMLX
  245.71 ms / 832.09 ms / 96.49 tok/s; and 512-token c2 was
  1032.30 ms / 1829.81 ms / 71.83 tok/s vs OMLX
  616.55 ms / 1404.86 ms / 116.67 tok/s.
- The same metrics snapshot recorded
  `control_plane.worker_connect_cache_hit_count=13`,
  `scheduler.multimodal_continuous_batch_enabled=0`,
  `scheduler.multimodal_continuous_batch_effective_capacity=1`,
  `scheduler.multimodal_continuous_batch_blocked_count=23`, and blocked reason
  code `2`, so the remaining optimization target is still the Python VLM
  continuous-batching/runtime scheduling boundary rather than setup reliability.
- A follow-up experiment tried skipping the outer `prompt_token_count()` call on
  the text-only `generate_step` fast path and deriving prompt tokens only from
  `prepare_inputs()`. `live-gemma26b-skip-token-count-comparison` completed
  all 36 requests with zero errors, but the result was mixed rather than a
  clear improvement: 128-token c2 TTFT improved slightly while 128-token c1
  TTFT and 512-token c1 TTFT regressed, and aggregate throughput regressed in
  multiple scenarios. The code change was reverted and should not be treated as
  an accepted optimization.
- The next accepted control-plane optimization replaces the default Python
  worker process bridge in live serving with Swift gRPC-over-UDS calls. The old
  `ProcessWorkerBridgeRunner` remains available for compatibility fixtures and
  explicit repo-root initialization, but `Bootstrap` now constructs
  `PythonBridgeWorkerClient(socketPath:)`, which uses `GRPCPythonWorkerRunner`
  directly against the Python worker socket. This removes one Python subprocess
  launch per worker RPC from the hot OpenAI-compatible serving path while
  preserving bridge error normalization and the long image RPC timeout.
- Verification for this slice: `xcrun swift build --package-path
  services/control-plane-swift` passed. `xcrun swift test --no-parallel
  --package-path services/control-plane-swift --filter
  PythonBridgeWorkerClientTests/defaultInitializerBridgesWorkerRPCsOverUnixDomainSocket`
  still failed before executing the test because this local Swift toolchain
  cannot import the `Testing` module, matching the existing Swift test runner
  blocker seen earlier in this worktree.
- `live-gemma26b-direct-grpc-smoke` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-direct-grpc-smoke` and exported
  to `~/Downloads/live-gemma26b-direct-grpc-smoke`. It completed all six
  measured requests with zero errors. Relative to
  `live-gemma26b-auto-socket-peak-smoke`, Melix improved from
  274.09 ms / 740.37 ms / 96.51 tok/s to
  230.54 ms / 524.03 ms / 154.18 tok/s for 128-token c1 TTFT / total latency /
  decode throughput, and from 649.67 ms / 1119.10 ms / 94.95 tok/s to
  486.93 ms / 779.80 ms / 151.95 tok/s for 128-token c2.
- A smaller control-plane follow-up delivers the first `tokenDelta` to the
  resumable execution hub before awaiting scheduler progress publishing and
  metrics writes. The first-token timestamp is still captured before delivery
  and written afterward, preserving observability while keeping progress
  publisher latency out of external TTFT.
- `live-gemma26b-first-token-delivery-smoke` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-first-token-delivery-smoke` and
  exported to `~/Downloads/live-gemma26b-first-token-delivery-smoke`. It
  completed all six measured requests with zero errors. Relative to the direct
  gRPC smoke, Melix 128-token c1 TTFT improved from 230.54 ms to 207.99 ms, and
  c2 median TTFT improved from 486.93 ms to 474.88 ms.
- `live-gemma26b-first-token-delivery-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-first-token-delivery-comparison`
  and exported to `~/Downloads/live-gemma26b-first-token-delivery-comparison`.
  It completed the full 36-request comparison with both endpoint preflights
  passing and zero request errors.
- Relative to `live-gemma26b-auto-socket-peak-comparison`, the latest full
  comparison shows a large accepted serving improvement: Melix 128-token c1
  moved from 271.62 ms / 1053.87 ms / 107.31 tok/s to
  208.91 ms / 509.05 ms / 154.52 tok/s for TTFT / total latency / decode
  throughput; 128-token c2 moved from 871.09 ms / 1644.73 ms /
  114.86 tok/s to 476.19 ms / 778.82 ms / 147.18 tok/s; 512-token c1 moved
  from 398.75 ms / 1196.08 ms / 105.86 tok/s to 322.75 ms / 640.81 ms /
  138.89 tok/s; and 512-token c2 moved from 1032.30 ms / 1829.81 ms /
  108.67 tok/s to 655.24 ms / 972.44 ms / 139.45 tok/s.
- The latest full comparison still does not satisfy the 10% parity gate in all
  scenarios. The current Melix/OMLX ratios are: 128-token c1 TTFT 1.36x,
  total 1.16x, decode 0.96x, aggregate 0.87x; 128-token c2 TTFT 1.57x,
  total 1.14x, decode 1.22x, aggregate 0.65x; 512-token c1 TTFT 1.33x,
  total 1.20x, decode 0.84x, aggregate 0.75x; and 512-token c2 TTFT 1.30x,
  total 1.08x, decode 1.42x, aggregate 0.72x.
- The latest metrics snapshot still recorded
  `scheduler.multimodal_continuous_batch_enabled=0`,
  `scheduler.multimodal_continuous_batch_effective_capacity=1`,
  `scheduler.multimodal_continuous_batch_blocked_count=23`, and blocked reason
  code `2`. The remaining work therefore stays focused on Python VLM
  continuous batching or a backend token scheduler, not another control-plane
  admission-only change.

## Next Optimization Slice

- The next implementation probe adds a cooperative text-only token-step path
  before changing control-plane admission. `MLXRuntimeExecutor` now exposes an
  iterator mode that runs each generator `next()` on the owner thread and
  releases the owner between yielded tokens, while the VLM text-only
  `generate_step` fast path uses an isolated per-request streaming detokenizer
  so concurrent streams do not share reset/add-token state.
- The cooperative capability is explicit opt-in metadata, not a catalog default.
  The OpenAI gateway copies `melix.vlm.text_only_step_cooperative` onto worker
  requests only when the model metadata opts in and the normalized request is
  text-only. `RequestCoordinator` then allows multimodal continuous-batch
  admission only for Python VLM requests with that request capability and no
  non-text media parts; image/video VLM requests remain at batch size 1 with
  blocked reason code `2`.
- Live probe `/Users/chenyu/Downloads/live-gemma26b-cooperative-step-smoke`
  validated that opt-in cooperative admission functions
  (`scheduler.multimodal_continuous_batch_enabled=1`, effective capacity `2`),
  and improved concurrency-2 TTFT from `474.88 ms` to `325.13 ms` versus the
  previous first-token-delivery smoke. It regressed concurrency-2 total latency
  from `776.44 ms` to `1000.30 ms` and decode throughput from `147.57 tok/s` to
  `67.02 tok/s`, so it is retained only as negative evidence and an explicit
  experiment.
- This is still a constrained text-only scheduling probe, not the final OMLX-
  style VLM `BatchGenerator` architecture. It should not be enabled by default
  unless a later implementation demonstrates end-to-end concurrency throughput
  improvements under live OMLX/Melix comparison.
- If the cooperative probe does not close the concurrency-2 aggregate
  throughput gap, the next implementation should focus on a true Python VLM
  streaming batch scheduler that owns batched token steps rather than only
  interleaving independent request generators.
- A first experimental text-only `mlx_lm.BatchGenerator` path was added behind
  explicit `melix.vlm.text_only_batch_generator` model metadata. It is not a
  catalog default: the OpenAI gateway copies the request capability only for
  text-only Python VLM routes, the worker advertises the capability as
  experimental/default-disabled, and runtime stats expose
  `last_multimodal_decode_mode`, `last_multimodal_fallback_reason`, and
  `last_multimodal_decode_sync_mode` so live comparisons can prove whether the
  request used `text_only_step` or `text_only_batch_generator`.
- The Gemma4 VLM text-only comparison exposed a production admission bottleneck:
  imported Gemma4 `mlx_vlm` models advertise the experimental batch-generator as
  disabled, so safe text-only greedy requests stayed at effective multimodal
  capacity `1`. The accepted eligibility rule is automatic only for Python VLM
  routes with `vision_family_id=gemma4-v1`, `melix.vlm.backend_id=mlx_vlm`,
  text-only messages, explicit greedy sampling (`temperature=0` and either
  omitted `top_p` or `top_p=1`) with final worker `top_k=0`, and no structured
  output, tool parser, tool call, tool-choice, or explicit reasoning constraint.
  Media and constrained output requests must remain fallback-only unless
  explicitly opted in by later capability work.
- The first opt-in live probes showed an empty-stream regression caused by a
  missing fallback-reason variable in the text-only step path, then showed that
  model-level `generation_config.json` defaults could keep a
  `temperature=0` request non-greedy when `top_p` was omitted. The accepted
  gateway fix is narrow: for text-only VLM requests with batch-generator opt-in,
  an explicit request `temperature=0`, and no explicit request `top_p`, Melix
  normalizes worker sampling to `top_p=1` and `top_k=0` so the model package's
  `top_p=0.95` default does not silently disable the requested greedy batch
  path.
- `live-gemma26b-batch-generator-final2-smoke` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-batch-generator-final2-smoke`
  and exported to `~/Downloads/live-gemma26b-batch-generator-final2-smoke`.
  The original HTTP request shape (`temperature=0`, no explicit `top_p`) now
  records `vision.multimodal_decode_mode_code=7`,
  `vision.multimodal_decode_sync_mode_code=4`, and fallback reason code `0`,
  confirming the batch-generator path is active.
- The batch-generator path also filters tokenizer special stop ids before
  detokenization. A live short request returned `Hello there!` without leaking
  Gemma control tokens such as `<turn|>` or `<channel|>`, and the final smoke
  metrics kept parser leak counters at zero.
- Relative to the route-fix smoke that still used `text_only_step`, the
  batch-generator smoke kept 128-token concurrency-1 roughly flat
  (TTFT `207.23 ms` to `203.18 ms`, total `521.05 ms` to `503.12 ms`) and
  improved concurrency-2 materially (TTFT `327.29 ms` to `390.11 ms` regressed,
  but total `1008.85 ms` to `868.57 ms`, decode `66.08 tok/s` to
  `93.62 tok/s`, and aggregate `87.48 tok/s` to `100.93 tok/s`). It still
  trails the same OMLX smoke at concurrency 2 (`678.93 ms` total,
  `115.58 tok/s` decode, `128.40 tok/s` aggregate), so the parity gate remains
  open.
- A follow-up prefill-batch probe increased the internal `BatchGenerator`
  `prefill_batch_size` from `1` to the active batch capacity. Two exported
  smokes, `~/Downloads/live-gemma26b-batch-generator-prefill-batch-smoke` and
  `~/Downloads/live-gemma26b-batch-generator-prefill-cap2-smoke`, showed mixed
  evidence: concurrency-2 total latency and aggregate throughput improved
  slightly, but concurrency-1 decode or aggregate throughput regressed. The
  code change was reverted and should be treated as negative evidence, not an
  accepted optimization.
- A follow-up external-prefill probe was also reverted. That experiment
  prefilled text-only prompts outside `BatchGenerator` and inserted only the
  final token with a prompt cache, mirroring the OMLX scheduler shape. The
  exported `~/Downloads/live-gemma26b-batch-generator-external-prefill-smoke`
  bundle showed a concurrency-1 regression relative to the accepted
  `~/Downloads/live-gemma26b-batch-generator-final2-smoke` baseline: Melix TTFT
  moved from `203.18 ms` to `310.64 ms`, and total latency moved from
  `503.12 ms` to `609.24 ms`. Concurrency-2 total latency did not improve
  (`868.57 ms` baseline vs `873.09 ms` external prefill), so this patch remains
  negative evidence rather than an accepted optimization.
- Batch scheduler wait-window probes were likewise not accepted. Reducing the
  text-only batch-generator pending window from `2 ms` to `1 ms` kept
  concurrency-1 roughly flat and improved concurrency-2 total latency
  (`868.57 ms` to `797.21 ms`), but reduced concurrency-2 aggregate throughput
  (`100.93 tok/s` to `94.17 tok/s`) and still missed the OMLX gate. Removing
  the wait window entirely (`~/Downloads/live-gemma26b-batch-generator-wait0-smoke`)
  did not improve concurrency-2 total latency (`871.47 ms`) or aggregate
  throughput (`100.46 tok/s`), so the scheduler kept the accepted `2 ms`
  collection window.
- A direct-tokenizer prompt-id probe was also not accepted. It bypassed
  `mlx_vlm.utils.prepare_inputs()` for text-only `BatchGenerator` prompt ids
  when the processor tokenizer exposed direct tokenization, with fallback to the
  existing `prepare_inputs()` path. The exported
  `~/Downloads/live-gemma26b-batch-generator-direct-tokenizer-smoke-012941`
  bundle showed no actionable improvement over the accepted
  `~/Downloads/live-gemma26b-batch-generator-final2-smoke` baseline:
  concurrency-1 Melix TTFT / total latency moved from `203.18 ms` /
  `503.12 ms` to `205.96 ms` / `505.40 ms`, and concurrency-2 moved from
  `394.56 ms` / `868.57 ms` / `93.62 tok/s` to `390.84 ms` /
  `868.30 ms` / `92.94 tok/s`. The OMLX concurrency-2 result in the same
  probe remained materially ahead at `299.74 ms` TTFT, `677.82 ms` total, and
  `113.05 tok/s` decode throughput, so this code was reverted.
- An off-executor response-emission probe was also reverted. That experiment
  kept `BatchGenerator.next()` on the MLX executor but moved detokenization,
  stop-token filtering, and request queue emission back to the scheduler
  thread. The exported
  `~/Downloads/live-gemma26b-batch-generator-off-executor-emit-smoke` bundle
  improved Melix concurrency-2 total latency (`868.57 ms` to `802.59 ms`) but
  regressed concurrency-1 TTFT / total latency (`203.18 ms` / `503.12 ms` to
  `304.39 ms` / `602.45 ms`) and reduced concurrency-2 aggregate throughput
  (`100.93 tok/s` to `95.66 tok/s`). Because it did not improve the parity
  gate without collateral regressions, the code change was not kept.
- A `BatchGenerator.next_generated()` probe was also reverted. It mirrored
  OMLX's generated-response-only scheduler call instead of Melix's direct
  `next()` call, but the exported
  `~/Downloads/live-gemma26b-batch-generator-next-generated-smoke` bundle
  regressed Melix concurrency-1 TTFT / total latency from `203.18 ms` /
  `503.12 ms` to `307.03 ms` / `607.19 ms`, and regressed concurrency-2 total
  latency from `868.57 ms` to `886.52 ms`. Since it missed the parity gate and
  added c1/c2 regressions, the scheduler kept the accepted direct `next()`
  call.
- `live-gemma26b-batch-generator-final-full-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-batch-generator-final-full-comparison`
  and exported to
  `~/Downloads/live-gemma26b-batch-generator-final-full-comparison`. It ran the
  accepted BatchGenerator path across 128-token and 512-token prompt targets,
  concurrency 1 and 2, and 3 repeats per scenario. All 36 measured requests
  completed with zero errors, both endpoint preflights passed, and the metrics
  snapshot confirmed `vision.multimodal_decode_mode_code=7`,
  `vision.multimodal_decode_sync_mode_code=4`,
  `scheduler.multimodal_continuous_batch_enabled=1`, effective capacity `2`,
  and blocked reason code `0`.
- The full comparison shows the accepted BatchGenerator path still misses the
  10% OMLX parity gate. The Melix/OMLX ratios were: 128-token c1 TTFT `1.37x`,
  total `1.15x`, decode `0.92x`, aggregate `0.84x`; 128-token c2 TTFT `1.32x`,
  total `1.28x`, decode `0.79x`, aggregate `0.78x`; 512-token c1 TTFT `1.22x`,
  total `1.14x`, decode `0.99x`, aggregate `0.94x`; and 512-token c2 TTFT
  `1.19x`, total `1.21x`, decode `0.91x`, aggregate `0.94x`.
- Because batching is now active in the full comparison, the remaining gap is
  no longer an admission-disabled problem. The strongest uncovered gap is short
  prompt concurrency-2 decode and aggregate throughput, followed by short
  prompt TTFT. Future probes should profile Python scheduler cadence, per-token
  queue/stream overhead, and why the final metrics sample still reports
  `vision.vlm_first_token_ms=522.97` and `http.ttfd_ms=562.44` for the last
  sampled request despite median 128-token c1 TTFT around `209 ms`.
- The scheduler diagnostic probe added persistent
  `vision.text_batch_generator.*` control-plane metrics and exported
  `~/Downloads/live-gemma26b-batch-generator-scheduler-metrics-c2-probe`.
  The probe ran the 128-token, concurrency-2, `max_tokens=32` scenario with
  3 repeats and zero request errors. It reproduced the remaining gap:
  Melix median TTFT / total / decode / aggregate were `409.23 ms` /
  `937.64 ms` / `60.40 tok/s` / `68.22 tok/s`, while OMLX was
  `299.53 ms` / `678.48 ms` / `84.43 tok/s` / `93.47 tok/s`.
- The same metrics show the remaining issue is inside the MLX
  BatchGenerator step rather than queueing or stream emission. The final
  snapshot reported `scheduler.multimodal_continuous_batch_enabled=1`,
  `scheduler.continuous_batch_size=2`,
  `vision.text_batch_generator.peak_active_batch_size=2`,
  `queue_wait_ms_total=99.44` across 7 submitted requests, and
  `emit_ms_total=4.32 ms` across 200 generated responses. By contrast,
  `executor_step_ms_total=2245.14 ms` and `next_ms_total=2230.90 ms`, so
  nearly all measured scheduler time is spent in `BatchGenerator.next()`.
- A short OMLX source audit after the diagnostic run found one material
  architectural difference that was not isolated by earlier single-parameter
  probes: OMLX externally prefills prompt tokens into a cache, inserts only the
  final prompt token plus cache into `BatchGenerator`, and then drives decode
  with `next_generated()`. Melix's accepted path currently lets
  `BatchGenerator.next()` own both prompt processing and generated-response
  delivery. A quick combined experiment was started but reverted before live
  measurement because the direct implementation hung the scheduler unit test;
  the next implementation slice should build this OMLX-style prefill/cache
  handoff behind its own opt-in and unit-test it before running another live
  comparison.
- A follow-up OMLX-style external prefill plus cache-handoff experiment was
  implemented behind a temporary `.runtime` model alias and measured in
  `~/Downloads/live-gemma26b-batch-generator-external-prefill-next-generated-c2-probe`.
  The live 128-token concurrency-2 probe completed with zero errors and proved
  the path was active (`external_prefill_request_count=7`,
  `external_prefill_token_count=916`, `external_prefill_ms_total=877.96 ms`),
  but it did not improve the remaining parity gap: Melix median TTFT / total /
  decode / aggregate were `403.76 ms` / `938.97 ms` / `59.78 tok/s` /
  `67.52 tok/s` versus OMLX `298.82 ms` / `680.32 ms` / `84.06 tok/s` /
  `93.34 tok/s`. Compared with the scheduler-metrics baseline, the
  `BatchGenerator.next()` time moved into insert/external-prefill work instead
  of reducing end-to-end latency, so the external-prefill opt-in code was
  reverted and only the failure-observability guard was kept.
- Two more single-parameter probes were negative. Raising the internal
  `completion_batch_size` to `32` in
  `~/Downloads/live-gemma26b-completion-batch-size-32-c2-probe` left Melix
  near the same 128-token concurrency-2 result (`399.17 ms` TTFT,
  `928.20 ms` total, `67.95 tok/s` aggregate) versus OMLX
  (`300.15 ms`, `677.99 ms`, `93.75 tok/s`), so that code was reverted. Aligning
  the MLX executor with OMLX by using an executor-owned thread-local
  `generation_stream` was retained as a stream-ownership fix, but the live
  probe `~/Downloads/live-gemma26b-thread-local-generation-stream-c2-probe`
  showed only a small/noisy serving change: Melix `411.57 ms` TTFT,
  `924.91 ms` total, and `68.96 tok/s` aggregate versus OMLX
  `298.68 ms`, `675.10 ms`, and `93.93 tok/s`.
- A long-output probe initially exposed a measurement artifact: the default
  synthetic prompt asked for a concise answer, so 128-token runs could finish
  early and make total latency comparisons depend on output length. The
  benchmark script now supports `--prompt-style saturating`, which asks the
  model to continue until the server stops the response and records the prompt
  style in observations, summaries, and manifests. The first saturating
  long-output probe, exported to
  `~/Downloads/live-gemma26b-saturating-long-decode-c2-probe`, aligned both
  endpoints at 128 completion tokens and reproduced the gap before the metrics
  fix: Melix median TTFT / total / decode / aggregate were `470.24 ms` /
  `2469.45 ms` / `64.09 tok/s` / `102.04 tok/s`, while OMLX was
  `364.84 ms` / `1904.66 ms` / `83.13 tok/s` / `134.05 tok/s`.
- The decisive control-plane bottleneck was high-frequency metrics export, not
  MLX decode. `MetricsStore` previously wrote the full control-plane metrics
  JSON atomically on every `set`, `increment`, or `decrement`; the streaming
  token path updates scheduler and HTTP metrics for every event, so serving
  throughput was coupled to repeated JSON serialization and file writes. The
  accepted fix keeps in-memory metric updates synchronous for `snapshot()` but
  throttles disk export and adds `flushExport()` for tests and explicit
  snapshot durability.
- `live-gemma26b-metrics-throttled-saturating-c2-probe` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-metrics-throttled-saturating-c2-probe`
  and exported to
  `~/Downloads/live-gemma26b-metrics-throttled-saturating-c2-probe` after
  restarting the isolated Melix instance. It completed the 128-token
  concurrency-2 saturating scenario with zero errors and no generated
  optimization hints. Melix median TTFT / total / decode / aggregate improved
  to `340.94 ms` / `1855.49 ms` / `84.56 tok/s` / `137.15 tok/s`, matching the
  OMLX run at `311.60 ms` / `1847.48 ms` / `83.35 tok/s` / `138.08 tok/s`.
  The scenario now satisfies the 10% parity gate for TTFT, total latency,
  decode throughput, and aggregate throughput; it should still be rechecked in
  the full 128/512 c1/c2 matrix before declaring final parity.
- `live-gemma26b-metrics-throttled-saturating-full-comparison` was staged at
  `.runtime/omlx-melix-benchmark/live-gemma26b-metrics-throttled-saturating-full-comparison`
  and exported to
  `~/Downloads/live-gemma26b-metrics-throttled-saturating-full-comparison`. It
  ran the saturating 128-token output matrix across 128-token and 512-token
  prompt targets, concurrency 1 and 2, and 3 repeats per scenario. All 36
  measured requests completed with zero errors, both endpoint preflights
  passed, and the comparison generated no optimization hints. Metrics confirmed
  the accepted path was active with `scheduler.multimodal_continuous_batch_enabled=1`,
  effective capacity `2`, fallback reason code `0`, and
  `vision.multimodal_decode_mode_code=7`.
- In that full comparison, Melix matched OMLX on end-to-end total latency,
  decode throughput, and aggregate throughput in every measured scenario.
  Ratios were: 128-token c1 TTFT `1.14x`, total `1.00x`, decode `1.02x`,
  aggregate `1.00x`; 128-token c2 TTFT `1.09x`, total `1.00x`, decode
  `1.02x`, aggregate `1.00x`; 512-token c1 TTFT `1.10x`, total `1.00x`,
  decode `1.02x`, aggregate `1.00x`; and 512-token c2 TTFT `1.07x`, total
  `1.00x`, decode `1.02x`, aggregate `1.00x`.
- The only strict 10% parity miss left in the full matrix is the 128-token
  concurrency-1 TTFT row. A focused 7-repeat probe exported to
  `~/Downloads/live-gemma26b-metrics-throttled-saturating-c1-repeat-probe`
  confirmed it is stable but small in absolute terms: Melix median TTFT
  `182.29 ms` versus OMLX `159.19 ms`, while total latency (`1357.74 ms` vs
  `1359.38 ms`), decode throughput (`108.68 tok/s` vs `106.60 tok/s`), and
  aggregate throughput (`94.27 tok/s` vs `94.16 tok/s`) are at parity or
  slightly ahead for Melix. The final Melix metrics showed
  `vision.vlm_first_token_ms=177.30` and `http.ttfd_ms=179.32`, so the
  residual TTFT gap is before the first runtime text event rather than Swift
  SSE forwarding.
- A first-token breakdown probe then instrumented the text-only batch-generator
  path with prepare, first generated response, first visible response, first
  visible token index, and empty pre-visible segment counters. The initial
  `~/Downloads/live-gemma26b-first-token-breakdown-c1-probe` showed Melix
  median TTFT `181.82 ms` versus OMLX `158.63 ms`; Melix metrics averaged two
  empty generated segments before the first visible text and first visible text
  at generated token index 3.
- Preserving chat messages on text-only prepared requests and preferring
  tokenizer-side `apply_chat_template(..., tokenize=False,
  add_generation_prompt=True)` removed prompt-template drift but did not close
  the TTFT gap by itself. The probe exported to
  `~/Downloads/live-gemma26b-tokenizer-template-c1-probe` measured Melix median
  TTFT `180.79 ms` versus OMLX `158.97 ms`, a `1.137x` TTFT ratio.
- The accepted first-token fix aligns Gemma 4 text-only batch-generator
  streaming with OMLX by decoding token ids through a tokenizer-side streaming
  parser instead of the Gemma 4 processor detokenizer. The parser uses the
  tokenizer decode path, buffers partial Gemma control markers, maps thought
  markers to the OpenAI-compatible `<think>` text form, and drops turn and
  tool-response control markers. In
  `~/Downloads/live-gemma26b-gemma4-parser-c1-probe`, Melix median TTFT improved
  to `162.72 ms` versus OMLX `158.21 ms` (`1.028x`), while first empty segment
  count fell to `0` and first visible token index fell to `1`.
- The final full matrix,
  `~/Downloads/live-gemma26b-gemma4-parser-full-comparison`, reran the
  saturating 128-token output matrix across 128-token and 512-token prompt
  targets, concurrency 1 and 2, and 3 repeats per scenario with one warmup per
  endpoint. All 36 measured requests completed with zero errors, both endpoint
  preflights passed, and the report generated no optimization hints. The
  Melix/OMLX ratios are now: 128-token c1 TTFT `1.023x`, total `0.997x`,
  decode `1.007x`, aggregate `1.003x`; 128-token c2 TTFT `1.006x`, total
  `1.003x`, decode `0.997x`, aggregate `0.994x`; 512-token c1 TTFT `1.022x`,
  total `1.006x`, decode `0.999x`, aggregate `0.994x`; and 512-token c2 TTFT
  `0.998x`, total `0.999x`, decode `1.000x`, aggregate `0.998x`. The measured
  warm serving gates for TTFT, total latency, decode throughput, and aggregate
  throughput are therefore within the 10% parity threshold in every scenario in
  this matrix.
- A likely long-term shape is a Python VLM scheduler that performs VLM
  preprocessing once per request, injects precomputed embeddings for prefill,
  and lets a shared decode batcher own token steps. That is a separate runtime
  architecture slice, not a control-plane-only admission flag.
- Separately profile cold model-load cost and first-request memory pressure if
  future comparisons need cold-start parity. The current accepted evidence is
  warm serving latency after explicit warmup requests.
- Keep local dev stacks pinned to a venv Python for the Python worker process;
  `MELIX_PYTHON_BRIDGE_EXECUTABLE` is no longer on the default live serving
  hot path after the direct Swift gRPC client change, but remains supported for
  explicit process-bridge fixtures and fallback diagnostics.
- Use `--warmup-requests 1` or higher for future live comparisons whenever the
  target question is warm serving latency rather than cold first-request model
  load behavior. Keep the raw warmup observations in the bundle but exclude
  them from optimization gates.
- Use `--preflight-wait-seconds` for fresh Melix homes or restarted instances so
  registry discovery latency does not turn into measured `model_not_ready`
  request failures.
- Keep local dev stacks pinned to a venv Python through
  `UV_PROJECT_ENVIRONMENT` when running MLX comparisons. Otherwise
  `uv run --extra mlx` may select a newer interpreter and attempt incompatible
  source builds before the benchmark can start.
- Treat `model_listed=false` as an invalid comparison setup unless the operator
  explicitly requests `--allow-failed-preflight` to capture failure observations.

## Current Known Gaps

- The live comparison is a serving benchmark, not a quality benchmark. It does
  not validate semantic equivalence of generated text.
- The first live comparison is warm-state evidence. It does not isolate cold
  model-load cost, process startup cost, or memory pressure from other local
  Melix and OMLX instances.
- Existing Melix sidecar processes may be present but stale or unable to serve
  generation requests. Treat `GET /health`, `GET /v1/models`, and a minimal
  streaming `/v1/chat/completions` request as readiness signals, not process
  presence alone.
