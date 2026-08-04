# Issue 3229 Request Stream Registration Readiness

## Goal

Remove the request-recency test race in which a phase-aware worker fixture can
drop its only token and terminal events before the corresponding request stream
continuation is registered.

## Confirmed Failure

On `origin/main` at `0ca3784319d5d59c75a5c05bc76eb7f95efac0c3`, the focused
`admittedTextRequestsRefreshModelRecencyForSameFamilyEvictionPlanning()` test
timed out under a 10-second process deadline. `PhaseAwareWorkerClient` stores
continuations only when `generate` or `decode` constructs its
`AsyncThrowingStream`; every event emitter currently returns without evidence
when called before that registration.

## Scope

- Add an event-driven, request-ID-scoped readiness contract to the
  `PhaseAwareWorkerClient` test fixture.
- Bound readiness waits with a deadline so a missing registration becomes a
  normal test failure instead of an indefinite stream wait.
- Await readiness in the recency test before emitting its token and terminal
  events.
- Audit other `PhaseAwareWorkerClient` call sites and add the readiness barrier
  where no existing actor observation or decode-request wait already proves
  registration.
- Add deterministic fixture tests for registration success and deadline expiry.

## Non-Goals

- Change production `RequestCoordinator`, worker stream, admission, eviction,
  or scheduling behavior.
- Buffer fixture events emitted before registration.
- Add sleeps, polling retries, or production synchronization hooks.
- Change issue #2601 paged-KV behavior or interact with historical issue #1382
  processes.

## Design

`PhaseAwareWorkerClient` will retain readiness waiters by request ID. Registering
a `generate` or `decode` continuation will atomically store the continuation,
remove the matching readiness waiters, cancel their deadline tasks, and resume
them with success. A deadline task will remove and resume an unresolved waiter
with failure. Actor isolation provides the ordering guarantee, and waiter
removal ensures each checked continuation is resumed exactly once.

Tests that emit fixture events without another proven synchronization point will
call the readiness method first and require a successful result. Stream consumer
tasks will be cancelled during test cleanup so a readiness failure cannot leave
an unstructured consumer waiting.

## Verification

1. Run the readiness fixture tests, the recency regression, and the audited
   phase-aware request tests.
2. Build once, then execute the recency regression from the built artifact at
   least 100 consecutive times with an independent 10-second hard timeout per
   attempt.
3. Run `git diff --check` and inspect the final diff for production-code changes.

## Coverage And Metrics

- Production changed-scope coverage: `N/A`. This repair changes only a Swift
  test fixture, test call ordering, and this plan; no production executable line
  changes.
- Production performance probe: `N/A`. No production request path is modified.
- Stability metric: 100 or more consecutive built-artifact recency-test passes,
  zero hard timeouts, total elapsed time, and maximum per-attempt elapsed time.
- Readiness metric: a dedicated test proves an absent registration resolves as
  `false` within a bounded deadline, while a registered request resolves as
  `true` without polling.

## Acceptance

- Token and terminal events in the recency test cannot precede request-stream
  registration.
- Missing registration fails within the fixture deadline and cannot hang the
  suite.
- Existing synchronized phase-aware tests retain their behavior.
- At least 100 consecutive hard-timeout repetitions pass from one built test
  artifact.

## Verification Evidence

Validated on 2026-08-03 against `origin/main` commit
`6f31b55f6d4dec78c686499aecefb484cedbd837`:

- The unfixed recency regression exceeded its independent 10-second deadline.
- All 16 readiness and audited phase-aware tests passed.
- All 128 `RequestCoordinatorTests` passed in 3.215 seconds.
- The built recency test passed 100 consecutive executions with zero failures
  and zero 10-second timeouts. Total elapsed time was 76.066 seconds, the mean
  was 0.761 seconds, and the maximum was 4.229 seconds.
- Independent Spec review found no P1 or P2 issue. Its P3 test-coverage finding
  was addressed by deterministically observing waiter installation, proving an
  unrelated request registration does not wake it, and then proving the matching
  registration resumes it and removes the waiter.
- Independent Standards review found no P1. Its P2 CI-deadline finding was
  addressed by scaling both dedicated readiness-test deadlines through the
  repository helper. Its P3 findings were addressed by extracting the repeated
  readiness assertion and correcting the deadline-cancellation comment.
- Pull-request review identified the resumed disconnect-grace consumer as one
  remaining call site that relied on incidental elapsed time. It now requires
  the same request-scoped registration evidence before emitting fixture events.
- After the pull-request review fix, all 128 `RequestCoordinatorTests` passed
  again in 3.498 seconds on 2026-08-04.
- GitHub's `text-worker` shard twice lacked a default MLX metallib and aborted in
  two sampler tests that bypassed the suite's existing availability guard. Both
  tests now use `withTemporaryDefaultMetallib`: they execute when the resource is
  available and skip cleanly when it is absent. The focused pair passed 2/2
  locally.
- `git diff --check` passed.
- Production changed-scope coverage and performance metrics are `N/A` because
  the change is confined to a test fixture, test ordering, and this plan.
