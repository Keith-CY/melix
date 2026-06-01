# Issue 1660 Token Output Cadence Plan

## Context

Issue #1660 follows the #1659 output-overhead counter slice. The current Swift
text decode path writes one worker gRPC `TokenDelta` for every visible decoded
fragment after Harmony filtering. For Gemma E4B serving, that per-token write
cadence can add avoidable worker, control-plane, and SSE overhead without
changing the generated text.

The governing root is #1642, which requires Gemma E4B release comparison
evidence against peer runtimes. This slice must therefore preserve externally
visible streaming semantics while giving the benchmark path a measurable
reduction in output write pressure.

## Goal

Reduce avoidable per-token output overhead for Gemma-family Swift text decode
requests by coalescing bounded runs of visible text deltas after the first
visible token. Preserve ordering, first-token behavior, reasoning-channel
events, usage, completion payloads, and non-Gemma streaming behavior.

## Scope

- Apply cadence optimization only to the Swift text decode worker path.
- Scope the default optimization to Gemma/Gemma 4 model identifiers or model
  metadata, with an execution metadata override for diagnosis.
- Keep the first visible token delta immediate so TTFT and first SSE delivery
  are not delayed.
- Never coalesce reasoning deltas. Flush any pending visible text before a
  reasoning delta to preserve stream order.
- Flush pending visible text before usage, snapshot, and completion events.
- Use existing #1659 counters and stream event counts as the primary evidence
  surface.

Out of scope:

- Scheduler batching, model-step batching, sampling, tokenization, and lower
  runtime decode-loop changes.
- Broad generate-path cadence changes.
- Protocol schema changes.

## Implementation Steps

1. Add red worker tests.
   - Gemma decode: multiple visible fragments produce fewer `TokenDelta`
     events than completion tokens while preserving the exact final assistant
     text and usage token count.
   - Non-Gemma decode: visible fragments remain one delta per fragment.
   - Gemma reasoning transition: pending visible text is flushed before a
     reasoning delta and reasoning deltas remain separate.
2. Add a bounded visible-output cadence helper.
   - Extend the filtered output writer state with pending visible text.
   - Add a policy that writes the first visible token immediately, buffers
     later visible fragments up to a small fragment/character limit, and
     flushes before reasoning or terminal events.
3. Wire the policy into `TextDecodeEngine`.
   - Derive the policy from the loaded model spec and execution metadata.
   - Keep non-Gemma and explicit disabled policy on immediate writes.
4. Update focused verification and metrics notes.
   - Use existing `swift_text.decode_grpc_write_call_count`,
     `swift_text.decode_stream_event_count`, and final usage/completion
     assertions as the functional and performance signal.
   - Rerun the Gemma E4B three-way comparison after the code is green to verify
     #1660 acceptance against real serving scenarios.

## Performance Probes And Success Metrics

Focused worker success metrics:

- Gemma fake decode with six visible fragments emits three token delta writes:
  first token immediately, one bounded coalesced chunk, and one final flush.
- `swift_text.decode_grpc_write_call_count` and
  `swift_text.decode_stream_event_count` are lower than the non-coalesced
  equivalent for the Gemma test case.
- Non-Gemma fake decode continues to emit one visible token delta per fragment.
- Reasoning deltas remain separate and ordered after any pending visible flush.

Release evidence metrics:

- A Gemma E4B three-way benchmark rerun must show either improved Melix decode
  tok/s or lower total latency for at least one scenario, without an in-scope
  regression beyond the PR-scoped threshold.
- The report must include the #1659 counters, especially
  `swift_text.decode_grpc_write_call_count`, `http.worker_event_handle_*`, and
  `http.sse_write_*`, so the output-cadence change is attributable.

Observability mode: minimal. This slice reuses existing metrics and does not
add per-token actor hops or debug artifacts.

## Verification

```bash
swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeCoalescesGemmaVisibleTokenDeltasAfterFirstToken|WorkerScaffoldTests/testDecodeDoesNotCoalesceNonGemmaVisibleTokenDeltas|WorkerScaffoldTests/testDecodeFlushesPendingVisibleDeltasBeforeReasoningDeltas'

swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests|WorkerScaffoldTests/testGenerateSuppressesHarmonyThoughtChannelForLoadedModel'

uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/Inference/FilteredTextOutputWriter.swift services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift

uv run --project services/mlx-worker-python --extra mlx python scripts/same_cohort_batching_probe.py --metrics

uv run --project services/mlx-worker-python --extra mlx python scripts/three_way_serving_compare.py --help

git diff --check
```

The final PR gate must also follow the repository default commands and the
pre-commit performance report rules before claiming PR readiness.

## Metrics Report

Verification was run on June 1, 2026 from the
`codex/issue-1660-token-output-cadence-20260601` worktree.

- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeCoalescesGemmaVisibleTokenDeltasAfterFirstToken|WorkerScaffoldTests/testDecodeDoesNotCoalesceNonGemmaVisibleTokenDeltas|WorkerScaffoldTests/testDecodeFlushesPendingVisibleDeltasBeforeReasoningDeltas'`
  - Initial red result: Gemma cadence test failed because the existing path
    emitted six token deltas and nine total events instead of three token
    deltas and six total events.
- `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeOutputCadencePolicyScopesDefaultToGemmaAndHonorsOverrides|WorkerScaffoldTests/testDecodeCoalescesGemmaVisibleTokenDeltasAfterFirstToken|WorkerScaffoldTests/testDecodeDoesNotCoalesceNonGemmaVisibleTokenDeltas|WorkerScaffoldTests/testDecodeFlushesPendingVisibleDeltasBeforeReasoningDeltas|WorkerScaffoldTests/testDecodeStreamingRpcBatchesHomogeneousDeterministicDecodeRequests|WorkerScaffoldTests/testGenerateSuppressesHarmonyThoughtChannelForLoadedModel'`
  - Result: passed, 6 tests, 0 failures.
- Code review follow-up after PR #1721 merged:
  - Added `WorkerScaffoldTests/testDecodeOutputCadencePolicyAllowsFragmentOnlyFlushLimit`
    for cadence policies that intentionally disable the character cap while
    keeping the fragment cap active. Initial red result on current `origin/main`:
    the policy did not buffer and flushed immediately when
    `maxBufferedVisibleCharacters` was `0`.
  - `swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter 'WorkerScaffoldTests/testDecodeOutputCadencePolicyAllowsFragmentOnlyFlushLimit|WorkerScaffoldTests/testDecodeOutputCadencePolicyScopesDefaultToGemmaAndHonorsOverrides|WorkerScaffoldTests/testDecodeCoalescesGemmaVisibleTokenDeltasAfterFirstToken|WorkerScaffoldTests/testDecodeDoesNotCoalesceNonGemmaVisibleTokenDeltas|WorkerScaffoldTests/testDecodeFlushesPendingVisibleDeltasBeforeReasoningDeltas'`
    - Result: passed, 5 tests, 0 failures after making disabled limits
      non-participating in the flush decision.
  - `uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/Inference/FilteredTextOutputWriter.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`
    - Result for the follow-up staged delta: `TOTAL 100.00% 17/17`.
- `uv run --project services/mlx-worker-python --extra mlx python scripts/swift_changed_line_coverage.py --binary services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/MelixTextWorkerSwiftPackageTests.xctest/Contents/MacOS/MelixTextWorkerSwiftPackageTests --profdata services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/mlx-text-worker-swift/Sources/Core/Inference/FilteredTextOutputWriter.swift services/mlx-text-worker-swift/Sources/Core/Inference/TextDecodeEngine.swift services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`
  - Result: `TOTAL 99.77% 433/434`.
- `uv run --project services/mlx-worker-python --extra mlx python scripts/same_cohort_batching_probe.py --metrics`
  - Result: completed with no failure count; current warning remains
    `scheduler_admission_cohort_size=2`, `worker_model_eval_batch_size=1`,
    `status_warning=1`.
- `uv run --project services/mlx-worker-python --extra mlx python scripts/three_way_serving_compare.py --help`
  - Result: passed; report CLI and Gemma comparison options remain available.
- `make bootstrap`
  - Result: passed; git hooks path configured and the locked Python
    environment checked through `uv sync --project services/mlx-worker-python
    --extra mlx`.
- `make proto && git diff --exit-code -- packages/protocol/descriptors packages/protocol/python packages/protocol/swift`
  - Result: passed; generated protocol artifacts had no drift.
- `make swift-test`
  - Result: passed. The macOS menu bar package shard completed with 779 tests
    in 25 suites and 0 failures; earlier Swift shards also completed with
    return code 0.
- `make py-test`
  - Result: passed, 3377 tests, 14 skipped, 2 warnings.
- `make integration-test`
  - Result: passed, 115 tests, 1 skipped.
- `.githooks/pre-commit`
  - Result: passed on a 256 GiB macOS host. The hook reran
    `make swift-test`, `make py-test`, and `make integration-test`, then wrote
    `.runtime/pre-commit-performance/20260601-052118-31a46494/report/report.md`
    after the branch was updated to the current `origin/main`.
    The scoped performance report status was `ok` with `Regressions: 0`,
    `Context regressions: 0`, and `Verification failures: 0`.
- Real Gemma E4B before/after benchmark:
  - Command: `uv run --project services/mlx-worker-python --extra mlx python scripts/three_way_serving_compare.py --endpoint base=http://127.0.0.1:12445/v1::unsloth/gemma-4-E4B-it-MLX-8bit --endpoint head=http://127.0.0.1:12444/v1::unsloth/gemma-4-E4B-it-MLX-8bit --target-endpoint head --prompt-token-targets 1024 --max-tokens 128 --repeats 2 --warmup-requests 1 --warmup-prompt-token-target 512 --warmup-max-tokens 16 --concurrency 1 --cache-profile cold_unique --prompt-style saturating --temperature 0 --top-p 1 --top-k 0 --include-usage --timeout-seconds 900 --preflight-wait-seconds 30 --measurement-profile warm --run-id issue1660-gemma-e4b-output-cadence-20260601-045908`.
  - Base endpoint: `origin/main` at `5f69a9c79f9d3bf5e0d98e8c3094210fd6ce88d5`, isolated runtime
    `issue1660-base`, port `12445`.
  - Head endpoint: `codex/issue-1660-token-output-cadence-20260601`, isolated
    runtime `issue1660-head`, port `12444`.
  - Note: `origin/main` later advanced to `31a46494`; the subsequent merge was
    outside the Swift output-cadence path, and the full local pre-commit gate
    above was rerun after updating the branch.
  - Model: `unsloth/gemma-4-E4B-it-MLX-8bit`, local snapshot
    `~/.cache/huggingface/hub/models--unsloth--gemma-4-E4B-it-MLX-8bit/snapshots/0b58ae760a389dcdda6d4e74eab1a41bede541d1`.
  - Result: threshold status `ok`; failures `0`; both endpoints preflighted
    with the target model listed and completed 2 measured requests with
    `error_count=0`.
  - Scenario: warm profile, prompt target `1024`, measured prompt tokens
    `634`, `max_tokens=128`, `repeats=2`, `concurrency=1`, `prompt_style=saturating`.
  - Median total latency improved from `32048.20 ms` to `31927.64 ms`
    (`-0.38%`), and median decode throughput improved from `4.29 tok/s` to
    `4.39 tok/s` (`+2.25%`).
  - Decode write pressure dropped from `281` to `80` gRPC writes and from
    `131` to `36` streamed decode events across the warmup plus measured run;
    `swift_text.decode_grpc_write_total_us` dropped from `28047` to `8190`.
  - Memory evidence: Swift text-worker peak resident bytes were
    `8320598016` for base and `8338587648` for head. Both loaded one model.
  - Artifacts:
    `.runtime/issue1660-token-output-cadence-benchmark/issue1660-gemma-e4b-output-cadence-20260601-045908/summary.md`,
    `summary.json`, `observations.jsonl`, `peer-delta-rows.json`,
    `threshold-status.json`, `run-evidence.json`, and paired base/head
    metrics and `ps` snapshots.
