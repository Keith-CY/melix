# Task Plan

## Goal

Land the first executable `M9.6` slice by hardening chat-stream connection lifecycle behavior with a typed lifecycle policy, resumable disconnect grace handling, measurable keepalive gaps, and repository-owned recovery evidence.

## Scope

- add a repository-owned `ConnectionLifecyclePolicy` to centralize keepalive cadence, disconnect grace, retry, and resume eligibility rules
- refactor chat execution coordination so a disconnected stream can remain resume-eligible during a bounded grace window instead of being aborted immediately
- expose lifecycle state through the control-plane chat execution path and HTTP chat resume requests
- record `disconnect.keepalive_gap_ms`, `disconnect.recovery_latency_ms`, `disconnect.resume_success_rate`, and `disconnect.terminal_failure_count`
- add focused Swift tests, live integration coverage, a deterministic smoke script, and a runbook for connection lifecycle recovery

## Phases

1. Lifecycle policy and resumable request coordination
   - status: completed
   - evidence:
     - active plan: `docs/plans/2026-04-04-m9-6-connection-lifecycle-slice.md`
     - targets: `SSEStreamWriter`, `RequestCoordinator`, `ControlPlaneChatExecution`, and `OpenAIHandler` chat streaming path
     - TDD order: add failing Swift tests for keepalive-gap metrics, disconnect grace, resume success, and terminal disconnect failure before implementation
2. Integration, smoke, and operator evidence
   - status: completed
   - evidence:
     - add `tests/integration/test_connection_lifecycle.py`
     - add `scripts/m9_connection_smoke.py`
     - add `docs/runbooks/connection-lifecycle.md`
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - focused Swift and integration verification
     - changed-line coverage for touched executable scope at or above `95%`
     - metrics and roadmap status recorded in `progress.md` and the execution index

## Acceptance

- transient chat-stream disconnects enter a bounded resume window instead of aborting immediately
- a resumed chat execution preserves request identity and continues deterministically from the in-flight stream state
- keepalive cadence and disconnect outcomes are observable through repository-owned metrics
- terminal disconnect expiry yields an explicit failure path instead of silent cancellation

## Risks

- resumable stream hubs can easily leak continuations or worker requests if termination handling is not centralized
- replaying buffered events must avoid corrupting ordering guarantees for resumed consumers
- disconnect grace timers must not turn explicit operator cancellation into false-positive recovery attempts

## Outcome

- completed
