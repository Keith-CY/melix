# Live Draft, Benchmark, and Evaluation Probes

## Summary

Melix needs explicit live-model evidence before draft-model serving is promoted beyond
deterministic test behavior. This slice adds probe coverage for the Swift text decode
path and the Python model-operations benchmark/evaluation path without making CI depend
on Hub downloads or local MLX model weights.

## Implementation Contract

- Phase 2 metrics must accept explicit served and draft model ids or paths through CLI
  flags and environment variables.
- The Melix CLI server-session commands must expose the same draft serving defaults
  that the App exposes: acceleration mode, draft model id, and draft proposal token
  count. CLI-created or CLI-updated sessions must persist those values in the shared
  operator-session state so `melix server start` applies them through the existing
  control-plane serving-defaults command.
- When the App is configured to start server sessions through the CLI workflow bridge,
  it must pass the selected draft serving defaults explicitly to `server session
  update` before invoking `server start`; the bridge must not depend solely on a prior
  operator-session state flush.
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
- Swift MLX live speculative decode must only start when the loaded target and draft
  model specs prove tokenizer compatibility through non-empty matching tokenizer
  hashes, and through matching explicit model kind or family metadata when those
  fields are present. Incompatible or incomplete pairs either fall back to baseline
  when the request allows fallback or return a structured `unimplemented` error.
- DFlash draft checkpoints are a distinct draft runtime family, not autoregressive
  `ModelContainer` draft models. Managed imports and registry snapshots must mark
  DFlash metadata, and the Swift MLX live backend must route DFlash checkpoints to
  the native DFlash draft runtime before the normal Qwen loader or tokenizer
  compatibility path.
- Swift MLX live speculative decode must support native DFlash proposal plus
  target-verification when a loaded DFlash draft runtime is paired with a target
  model that exposes DFlash hidden-state hooks. The supported validation pair for
  this slice is `mlx-community/Qwen3.5-27B-4bit` with
  `z-lab/Qwen3.5-27B-DFlash`.
- The Swift live backend owns an in-process native DFlash implementation rather than
  importing `dflash-mlx` into the serving path. The Python `dflash-mlx` runtime is the
  parity oracle for token-level debug traces until the Swift implementation matches
  its staged-first, hidden-context, cache, and rollback semantics.
- Swift native DFlash must avoid target-side work that does not change emitted text:
  all-accepted rounds should carry the verified target state into the next round
  instead of emitting a bonus token that requires an extra target advance, max-token
  termination must not rebuild the full target prefix, and rejection repair should
  restore the pre-verify target cache and advance only the committed round tokens.
- Until Melix implements probability-correct speculative sampling, Swift MLX live
  speculative decode is limited to greedy sampling (`temperature=0`, `top_p=1`,
  `top_k=0`). Non-greedy requests must use baseline fallback or receive a structured
  `unimplemented` error when fallback is disabled.
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
- Managed Hub downloads and registry snapshots record DFlash draft metadata under
  `melix.draft.runtime_kind=dflash`, `melix.draft.architecture=DFlashDraftModel`,
  and optional DFlash block/layer metadata when present in `config.json`.
- Swift decode rows additionally record `dflash_enabled`, `dflash_block_size`,
  `dflash_rollback_count`, and `dflash_target_hidden_layers` for native DFlash
  speculative decode.
- Native Swift DFlash debug probes are opt-in through `MELIX_SWIFT_DFLASH_PROBE=1`
  or `MELIX_SWIFT_DFLASH_PROBE_PATH=<path>`. They write JSONL events for preflight,
  prefill, draft request, draft result, target verification, commit, and summary
  boundaries so local runs can compare Swift token flow against `dflash-mlx` without
  changing normal benchmark output.
- DFlash probes include target repair and avoided-work counters:
  `target_repair_us`, `target_cache_restore_used`,
  `target_final_rebuild_skipped_count`, and
  `target_bonus_advance_skipped_count`. These counters separate target verification
  cost from rollback repair and prove when the Swift runtime avoids previously
  unmeasured rebuild/bonus overhead.
- Phase 2 direct Swift worker reports must read runtime stats after both target and
  draft model loads complete, and `resident_bytes` must be at least the sum of the
  target and draft `LoadModel.estimated_resident_bytes` values when a draft is loaded.
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
- Local direct Swift worker evidence on April 25, 2026 used
  `mlx-community/Qwen3.5-27B-4bit` as the served model and
  `z-lab/Qwen3.5-27B-DFlash` as the native DFlash draft. After target-state
  repair optimization, 64-token baseline measured `4.80s` and `14.81 tok/s`.
  Native DFlash block 4 improved from `13.14s` to `6.16s` (`53.1%` lower
  wall time, `12.05 tok/s`, `84%` acceptance), and block 16 improved from
  `19.08s` to `8.00s` (`58.1%` lower wall time, `9.37 tok/s`, `87%`
  acceptance). The optimized DFlash path still trails baseline because target
  verification and rejection repair remain dominant (`3.48s` target verify and
  `1.24s` repair for block 4; `3.98s` target verify and `2.59s` repair for
  block 16). Probe evidence recorded `14` cache-restore rejection repairs and
  avoided all-accepted bonus target advances.

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
- Swift MLX tests cover tokenizer incompatibility and non-greedy sampling rejection
  paths for live speculative decode.
- Swift MLX and Python model-registry tests cover DFlash checkpoint recognition,
  native DFlash draft loading, and registry handoff so DFlash checkpoints cannot
  silently enter the autoregressive speculative draft path.
- Phase 2 metrics tests cover configured draft model loading, tokenizer-hash continuity
  between served and draft specs, and double-model resident-memory accounting.
- CLI tests cover creating and updating server sessions with draft serving defaults,
  including the `melix server start` handoff that applies the persisted draft model to
  the control plane.
- App workflow tests cover the CLI subprocess bridge forwarding draft serving defaults
  during server start.
