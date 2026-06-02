# Issue 1642 Current Acceptance Closure

## Scope

Issue #1642 tracks the release Gemma E4B serving gate against OMLX and SwiftLM.
The first current-main rerun at commit
`41774a247158d19d4a6f1675585bbcb2d631a8af` showed the remaining miss in
short-prompt concurrency-2. After the short-prompt batch-decode lookahead,
single-request greedy lookahead, asyncEval attribution, endpoint-order control,
and three-way run-key fix, the pairwise release gates now pass against OMLX and
SwiftLM independently. A simultaneous three-endpoint run is still not closure
evidence because OMLX becomes unstable under co-resident Metal pressure and
crashes during the run.

This slice closes the remaining blocker only when a fresh release rerun on a
current `origin/main` base proves every #1642 scenario is within the accepted
threshold or the issue accepts the lower-memory pairwise lifecycle as equivalent
acceptance evidence.

## Findings

- The remaining valid fresh-run failing scenarios before the single-request
  lazy-token path were `prompt_tokens=128, concurrency=1`,
  `prompt_tokens=1024, concurrency=1`, and `prompt_tokens=1024,
  concurrency=2`, all with `max_tokens=64`.
- Melix uses the Swift text route with batch decode enabled:
  `swift_text.decode_batch_size_max == 2` and
  `swift_text.model_eval_batch_size_max == 2`.
- The dominant local cost in the original short-prompt concurrency-2 failing
  run was synchronizing greedy token ids out of the Swift MLX batch decode loop,
  not HTTP/SSE output handling.
- Re-running the focused scenario with reversed endpoint order showed the fixed
  endpoint order in `scripts/three_way_serving_compare.py` can materially bias
  short-prompt warm measurements.
- The single-request greedy path needed the same lazy-token treatment as the
  batch path. Without it, `concurrency=1` scenarios could remain slower than
  the best peer even after batch decode improvements.
- The focused asyncEval probe shows the single-request decode loop is dominated
  by MLX `asyncEval` scheduling and graph execution time, not token-id
  materialization, detokenization, or SSE writes.
- With all three runtimes resident, OMLX can fail with
  `[METAL] Command buffer execution failed: Insufficient Memory`. Those runs
  are diagnostic environment evidence, not clean acceptance failures.

## Implementation Plan

1. Add a deterministic Swift MLX batch-decode lookahead path for homogeneous
   greedy cohorts. The path keeps the batched argmax token id row lazy, feeds it
   to the next model step before synchronizing the current token ids for
   streaming, and falls back to the existing per-request token path when a logit
   processor, abort, EOS, or cache rebuild changes the cohort shape.
2. Preserve the existing batch cache behavior and stream ordering. Unit tests
   must prove homogeneous batch cache reuse, no extra final model call, EOS
   stopping, and RPC batch admission behavior.
3. Add explicit endpoint-order control to the three-way comparison harness,
   matching the existing two-way benchmark behavior. The default remains fixed
   order; `alternate` rotates endpoint start position by repeat and records the
   setting in artifacts.
4. Re-run the focused `128/c2` release scenario and then the full #1642 release
   matrix with release Melix binaries, warm profile, usage token accounting,
   prompt targets `128` and `1024`, output `64`, concurrency `1` and `2`,
   repeats `3`, and explicit artifact evidence.
5. If the simultaneous three-endpoint lifecycle is unstable because of peer
   Metal memory pressure, collect pairwise release gates with the same scenario
   profile and record the lifecycle caveat explicitly before asking whether it
   satisfies the issue's peer-comparison intent.

## Success Metrics

- The release gate status is `ok` for all #1642 peer-delta rows.
- No scenario has Melix median total latency more than 25 percent slower than
  the best peer.
- No scenario has Melix median decode throughput more than 25 percent below the
  best peer.
- Artifacts include Melix binary paths, SHA-256 hashes, peer revisions, model
  snapshot path, endpoint-order mode, measurement profile, preflight status,
  raw observations, peer-delta rows, threshold status, and Melix metrics.

## Current Evidence

The branch was refreshed to `origin/main` at
`6d983542c69549450698d7c81f6fc96a67d64281` before the release reruns. Release
binaries used for the run-key-fix full run were:

- Text worker:
  `3f4662d164e53ac28e7d6081cbd07f6272ea2e988b9a7d907a4ac6fc1331644a`
- Control plane:
  `edbef32a4022b6bbdacff72f20c8fba15ebecb779778be9100f507171b2c498e`

The focused concurrency-2 rerun after short-prompt lookahead gating and
rotating endpoint order passed:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-short-lookahead-gated-focus-c2-rotateorder`
- Threshold status: `ok`
- Failure count: `0`
- Covered scenarios: `128/c2` and `1024/c2`

The full #1642 release matrix rerun did not pass and is not closure evidence:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-short-lookahead-gated-release-threeway-full-rotateorder-rerun2`
- Threshold status: `threshold_failed`
- Failure count: `5`
- Passing scenario: `128/c1`
- Failing scenarios:
  - `128/c2`: total latency `+53.18%`, decode throughput `-40.14%`
  - `1024/c1`: total latency `+33.32%`, decode throughput within threshold
  - `1024/c2`: total latency `+37.22%`, decode throughput `-34.89%`

This failed full rerun is also treated as diagnostic evidence rather than a
valid fresh `cold_unique` acceptance run. The three-way harness did not pass
`run_id` through to `run_group`, so `cold_unique` prompts were unique within a
single run but could be reused across repeated reruns of the same scenario id.
That made the run vulnerable to cross-run prompt-cache contamination after the
focused and discarded full reruns.

One earlier full rerun at
`.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-short-lookahead-gated-release-threeway-full-rotateorder`
was discarded as acceptance evidence because the SwiftLM listener disappeared
during the run.

This slice remains incomplete for #1642. The short-prompt c2 path has local
unit coverage and focused benchmark evidence, and the three-way harness now
uses the run id as the `cold_unique` prompt key. A fresh full current-main
release gate rerun is still required before this issue can be closed.

The fresh full release gate after the run-key fix also failed:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-short-lookahead-gated-release-threeway-full-runkeyfix`
- Threshold status: `threshold_failed`
- Failure count: `6`
- Passing scenario: `128/c2`
- Failing scenarios:
  - `128/c1`: total latency `+53.09%`, decode throughput `-34.19%`
  - `1024/c1`: total latency `+84.97%`, decode throughput `-48.97%`
  - `1024/c2`: total latency `+42.78%`, decode throughput `-33.61%`

This confirms the run-key issue was a harness correctness problem but not the
only remaining blocker. The full #1642 gate remains open on current main.

The latest release build under test adds single-request greedy lazy-token
lookahead and opt-in asyncEval attribution. Release binaries used for the
pairwise runs were:

- Text worker:
  `31a8c172e567cf69cb604d9c9a1b120f3b14824ce7b67cd493f995804a5a3e0c`
- Control plane:
  `edbef32a4022b6bbdacff72f20c8fba15ebecb779778be9100f507171b2c498e`

The focused asyncEval probe passed the `1024/c1` threshold and confirmed where
the remaining decode-loop time is spent:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-async-eval-probe-1024c1`
- Threshold status: `ok`
- `swift_text.decode_batch_loop_total_us`: `7436871`
- `swift_text.decode_batch_async_eval_total_us`: `7239920`
- `swift_text.decode_batch_async_eval_call_count`: `64`
- `swift_text.decode_batch_model_total_us`: `182047`
- `swift_text.decode_batch_token_id_total_us`: `5868`

The simultaneous three-endpoint full rerun after the single-request lookahead
and asyncEval probe is not clean closure evidence:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-single-lookahead-async-probe-full`
- Threshold status: `threshold_failed`
- Failure count: `2`
- Failing scenario: `128/c1` against SwiftLM
- Environment caveat: OMLX later crashed during the run with
  `[METAL] Command buffer execution failed: Insufficient Memory`, so the
  simultaneous three-endpoint lifecycle is treated as unstable diagnostic
  evidence.

The pairwise full release gate against OMLX passed with the same scenario
profile:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-pairwise-omlx-full`
- Threshold status: `ok`
- Failure count: `0`
- Observation count: `36`
- Peer-delta rows:
  - `128/c1`: total `+12.07%`, decode `+1.67%`
  - `128/c2`: total `+22.13%`, decode `-16.48%`
  - `1024/c1`: total `+6.49%`, decode `+1.24%`
  - `1024/c2`: total `+17.70%`, decode `-14.05%`

The pairwise full release gate against SwiftLM also passed with the same
scenario profile:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main6d98354-issue1642-lookahead/threeway/gemma-e4b-main6d98354-issue1642-pairwise-swiftlm-full`
- Threshold status: `ok`
- Failure count: `0`
- Observation count: `36`
- Peer-delta rows:
  - `128/c1`: total `+6.61%`, decode `-1.80%`
  - `128/c2`: total `-21.55%`, decode `+38.31%`
  - `1024/c1`: total `+5.69%`, decode `-1.76%`
  - `1024/c2`: total `-21.41%`, decode `+43.38%`

After refreshing the branch to `origin/main` at
`8ecd923f4516d95b8956537ecbb03f5be239ea3a`, the release-built development
stack path was corrected so `scripts/dev_up.sh --prefer-built
--build-configuration release` launches the existing `.build/release` Swift
executables. The runtime process table confirmed:

- Text worker:
  `services/mlx-text-worker-swift/.build/release/melix-text-worker-swift`
- Control plane:
  `services/control-plane-swift/.build/release/melix-control-plane`

The current-base release binaries were:

- Text worker:
  `31a8c172e567cf69cb604d9c9a1b120f3b14824ce7b67cd493f995804a5a3e0c`
- Control plane:
  `edbef32a4022b6bbdacff72f20c8fba15ebecb779778be9100f507171b2c498e`

The current-base pairwise full release gate against OMLX passed with the same
scenario profile:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main8ecd923f-issue1642-release-built/threeway/gemma-e4b-main8ecd923f-issue1642-pairwise-omlx-full`
- Threshold status: `ok`
- Failure count: `0`
- Observation count: `36`
- Peer-delta rows:
  - `128/c1`: total `+10.96%`, decode `+1.37%`
  - `128/c2`: total `+18.68%`, decode `-14.57%`
  - `1024/c1`: total `+11.51%`, decode `+1.01%`
  - `1024/c2`: total `+17.44%`, decode `-13.83%`

The current-base pairwise full release gate against SwiftLM also passed with
the same scenario profile:

- Artifact:
  `.runtime/serving-comparison/gemma-e4b-20260602-main8ecd923f-issue1642-release-built/threeway/gemma-e4b-main8ecd923f-issue1642-pairwise-swiftlm-full`
- Threshold status: `ok`
- Failure count: `0`
- Observation count: `36`
- Peer-delta rows:
  - `128/c1`: total `+6.61%`, decode `-2.54%`
  - `128/c2`: total `-19.42%`, decode `+33.37%`
  - `1024/c1`: total `+7.82%`, decode `-3.48%`
  - `1024/c2`: total `-18.46%`, decode `+36.72%`

Current-base focused verification:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project
  services/mlx-worker-python pytest -q
  services/mlx-worker-python/tests/test_dev_up_script.py
  tests/test_three_way_serving_compare.py
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs`:
  `106 passed`
- Focused `WorkerScaffoldTests` for baseline decode probe, max-token terminal
  behavior, live bridge decode, short-prompt batch cache reuse, and long-prompt
  synchronous-token fallback: `5 passed`
- Same-cohort registry Swift focused tests:
  - `swift test --package-path services/control-plane-swift --filter
    'RequestCoordinatorTests/sameCohortBatchingProbeEmitsLinkedAdmissionAndWorkerEvidence()'`:
    `1 test passed`
  - `swift test --package-path services/mlx-text-worker-swift --filter
    'WorkerScaffoldTests/testDecodeStreamingRpcStreamsTokensAndCleansUpStoredContext()'`:
    `1 test passed`
- PR-scoped performance scope:
  `.runtime/issue-1642-pr-scope.json`
  - `force_all`: `false`
  - Selected probes: `dev-up-mlx-metal-dist-info-scandir` and
    `same-cohort-batching-probe-evidence`
- PR-scoped performance report:
  `.runtime/issue-1642-pr-perf-report/report.md`
  - Status: `ok`
  - Regressions: `0`
  - Verification failures: `0`
  - `dev-up-mlx-metal-dist-info-scandir`: coverage `100.0%`;
    `elapsed_ms_mean` base `0.186 ms`, head `0.182 ms`
  - `same-cohort-batching-probe-evidence`: coverage `100.0%`;
    `failure_count=0`, `status_warning=1`, `status_passed=0`
- Default repository gates:
  - `make bootstrap`: passed
  - `make proto`: passed
  - `make swift-test`: passed, including protocol, text-worker,
    control-plane, and macOS menu bar suites
  - `make py-test`: `3416 passed, 14 skipped, 2 warnings in 156.63s`
  - `make integration-test`: `117 passed, 1 skipped in 720.53s (0:12:00)`
- Changed-scope coverage:
  - Python touched scope: `100.00%` (`133/133`) across `scripts/dev_up.py`,
    `scripts/three_way_serving_compare.py`,
    `services/mlx-worker-python/tests/test_dev_up_script.py`, and
    `tests/test_three_way_serving_compare.py`. The coverage tests passed with
    `104 passed`; the changed-line summary used `python3.11` because this host's
    `python3` is 3.9 and cannot parse the repository coverage script's
    `Path | None` type syntax.
  - Swift text-worker touched scope: `95.79%` (`500/522`) across
    `TextDecodeEngine.swift`, `MetricsStore.swift`, `SwiftMLXBackend.swift`,
    `TextRuntime.swift`, and `WorkerScaffoldTests.swift`, measured after
    `swift test --package-path services/mlx-text-worker-swift
    --enable-code-coverage --disable-automatic-resolution` passed
    `237 tests`.
- Staged pre-commit gate:
  - `.githooks/pre-commit`: passed on a 256 GiB macOS host.
  - Full gate inside the hook:
    - `make swift-test`: passed, elapsed `262.1s`
    - `make py-test`: `3416 passed, 14 skipped, 2 warnings in 145.39s`
    - `make integration-test`: `117 passed, 1 skipped in 451.61s (0:07:31)`
  - Pre-commit performance report:
    `.runtime/pre-commit-performance/20260602-072146-8ecd923f/report/report.md`
    - Status: `ok`
    - Changed files: `10`
    - Selected probes: `2`
    - Regressions: `0`
    - Context regressions: `0`
    - Verification failures: `0`
    - `dev-up-mlx-metal-dist-info-scandir`: coverage `100.0%`;
      `elapsed_ms_mean` base `0.198 ms`, head `0.171 ms`, improvement
      `-13.66%`
    - `same-cohort-batching-probe-evidence`: coverage `100.0%`;
      `status_warning` remained `1`, `status_passed` remained `0`,
      `scheduler_admission_cohort_size=2`, and
      `worker_model_eval_batch_size=1`
- `git diff --check`: passed

This is strong current-base progress evidence but not yet a complete #1642
closeout. The default repository test gate passed on this branch, but the branch
still needs a PR evidence body and a decision on whether pairwise peer lifecycle
evidence satisfies the acceptance criteria when simultaneous peer co-residency
makes OMLX unstable. The same-cohort batching probe also remains in warning
state because the scheduler admits a cohort of 2 but the observed worker model
eval batch size is still 1; that warning did not regress in this slice, but it
should not be presented as resolved #1642 closure evidence.
