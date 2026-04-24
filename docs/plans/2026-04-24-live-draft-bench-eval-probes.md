# Live Draft, Benchmark, and Evaluation Probes

## Summary

Melix needs explicit live-model evidence before draft-model serving is promoted beyond
deterministic test behavior. This slice adds probe coverage for the Swift text decode
path and the Python model-operations benchmark/evaluation path without making CI depend
on Hub downloads or local MLX model weights.

## Implementation Contract

- Phase 2 metrics must accept explicit served and draft model ids or paths through CLI
  flags and environment variables.
- When no draft is configured for a live Phase 2 run, Melix defaults the draft to
  `mlx-community/Qwen3-0.6B-4bit`. That model is small enough for local Apple Silicon
  probe runs and can be resolved from the Hugging Face cache, the Melix managed model
  root, or the Hub identifier for runtime download.
- Live-required runs must fail fast when the served model, draft model, or loaded runtime
  would fall back to deterministic development behavior or to a local path without
  recognized model weights.
- Swift speculative decode must record whether draft serving was requested, whether a
  draft model was configured, how many draft tokens were requested, and whether the
  backend fell back to baseline.
- Swift MLX live decode must execute a real draft proposal plus target verification
  path when a loaded draft model is available. The runtime may adaptively switch the
  remainder of a decode to target-only baseline when early speculative probes show
  low acceptance or an insufficient draft/target cost ratio.
- Product benchmark and evaluation jobs must persist runtime evidence in job parameters,
  including model handle, runtime kind, runtime name, model id, model path, source kind,
  and source repo.
- Control-plane direct Hub benchmark/evaluation requests must mark worker requests with
  `require_live_model=true`.
- Local live-stack startup must not auto-load an MLX Python wheel metallib whose
  `mlx_metal` version differs from the pinned Swift `mlx-swift` dependency. `dev_up`
  must prefer a matching local or global uv-cache `mlx_metal` metallib and fail fast
  with an actionable override when only incompatible candidates are present.

## Metrics and Evidence

- Swift decode rows record `speculative_acceptance_rate`,
  `speculative_rollback_rate`, `speculative_accepted_tokens`,
  `speculative_rejected_tokens`, `speculative_fallback_count`,
  `speculative_num_draft_tokens`, `speculative_draft_model_configured`,
  `speculative_draft_propose_ms`, and `speculative_target_verify_ms`.
- Phase 2 reports record served/draft model source resolution and runtime preflight
  class for both models.
- Benchmark summaries record live runtime evidence in `parameters` and include runtime
  lines in the Markdown report.
- Evaluation jobs record the same live runtime evidence in `parameters`.
- Local live benchmark evidence on April 24, 2026 used
  `mlx-community/Qwen3.5-0.8B-OptiQ-4bit` as the served model and
  `mlx-community/Qwen3-0.6B-4bit` as the draft model. The fixed metallib
  resolver allowed the stack to run with `mlx_metal` `0.29.1`, but Swift MLX
  speculative decode still reported `speculative_fallback_count=1`; direct
  `decode_speculative` measured `42.28 tok/s` versus baseline direct
  `44.04 tok/s`, so this slice proves instrumentation and live fallback only,
  not a draft-model speedup.
- After the Swift MLX live speculative path landed, the same local model pair
  executed real draft proposal and target verification. Without adaptive runtime
  fallback, the short direct probe measured `decode_speculative=3.59 tok/s`
  with `speculative_fallback_count=0`, `accepted=3`, `rejected=6`,
  `draft_propose_ms=456`, and `target_verify_ms=220`, which proved real
  execution but also showed this draft is not a profitable partner for the
  served 0.8B model. With adaptive runtime fallback enabled, the final direct
  probe measured baseline rows averaging `38.97 tok/s` wall and `36.33 tok/s`
  worker, while `decode_speculative` measured `39.20 tok/s` wall and `38 tok/s`
  worker after one rejected speculative probe and runtime fallback
  (`speculative_fallback_count=1`, `draft_propose_ms=16`).

## Acceptance Criteria

- Default deterministic tests and local workflows continue to work without live model
  files.
- `--require-live-model` accepts the default Hub draft when no explicit draft is
  configured, and rejects deterministic model ids, unavailable runtime names, and local
  model paths without recognized weights.
- Direct Hub benchmark/evaluation requests from the control plane set
  `require_live_model=true`.
- Targeted Python and Swift tests cover live-required rejection, runtime evidence, and
  speculative fallback metrics.
- Startup tests cover Swift MLX metallib version matching so live-model probes do not
  crash inside Metal pipeline specialization before metrics are emitted.
- Swift MLX tests cover the live speculative draft bridge and registry draft-model
  handoff so the backend cannot silently regress to deterministic-only speculative
  behavior.
