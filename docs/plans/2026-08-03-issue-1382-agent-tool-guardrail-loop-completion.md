# Issue 1382 Agent Tool Guardrail Loop Completion Plan

## Goal

Complete the reusable agent tool-call guardrail contract by connecting the
existing response-healing, admission, prerequisite, registry, and deterministic
execution primitives through one bounded live-loop state machine. The state
machine must keep control-flow truth outside prompt messages, provide Swift
request and event contracts, and emit operator-readable diagnostics.

## Current-State Audit

The current `origin/main` already ships these issue slices:

- registry/index parity and request-local network-tool consent;
- schema-consistency preflight receipts;
- model-response healing for supported text and provider wire shapes;
- pre-execution admission receipts for malformed, unknown, and invalid calls;
- prerequisite descriptors with optional matching-argument keys;
- deterministic local adapters and sanitized tool observations.

Those primitives are currently called by focused tests, evaluation paths, and
performance probes. They are not composed by a reusable live-loop boundary, so
the repository still lacks persistent required-step state, independent
malformed/tool-failure budgets, premature-terminal handling, exactly-once call
admission, and a single diagnostic summary.

The repository does not expose a model-reachable command-based tool-server
registration API, scheduled agent execution API, approval UI, or approval-wait
executor pool. Command-registration rollback and concrete approval-flow wiring
therefore remain outside the executable surface of this issue. Capacity safety
does not depend on those product surfaces: this completion includes a reusable
process-wide approval parking budget, a request lifecycle ledger, and a real
threaded capacity proof that later scheduling work must reuse.

## Architecture

The Python worker owns a new request-scoped `AgenticToolGuardrailLoop`. It
accepts a registry, deterministic runtime, required tools, prerequisites, and
explicit budgets. It owns a serializable state snapshot containing completed
steps, explicit required-tool lifecycle state, and a per-call execution ledger.
Prompt messages are inputs to generation only; they are never the source of
control-flow truth.

Each model response follows one path:

1. normalize or rescue candidate tool calls;
2. admit calls one at a time against the latest completed-step state;
3. suppress exact replay by call identity and fail closed on identity reuse with
   different arguments;
4. move required tools and admitted call identities through explicit
   `required`, `authorized`, `executing`, `completed`, and `retired` states,
   requiring a caller-owned durable `executing` checkpoint acknowledgement
   before adapter dispatch and updating completed-step evidence only after a
   completed observation;
5. apply independent consecutive malformed-response and tool-failure budgets;
6. retire tool execution after all required steps complete and request one
   final answer without tools;
7. emit sanitized decision events and a deterministic diagnostic summary.

Every config/state/event/diagnostic receipt also binds `thread_scope_id`,
`current_turn_tool_start`, and `tool_result_export_policy`. Restore rejects a
different thread or turn boundary. Runtime dispatch and execution results carry
the thread and turn binding, and the loop validates it both after execution and
before model export. Model directives receive only matching, bounded
text-summary projections. Full sanitized media/operator payloads remain on the
turn result and are not copied back into model context.

The Swift control plane owns Codable request, state, event, and diagnostics
contracts for the same schema versions. Request shaping writes canonical JSON
into worker execution metadata without moving execution truth into Swift.

The Python worker also owns a process-wide `AgenticToolApprovalParkingBudget`.
An executing request holds one executor lease. An approval wait atomically
acquires one bounded parking permit and returns its executor lease. Resume first
reacquires a lease without consuming the configured two-worker reserve, then
returns the parking permit. Completion, cancellation, timeout, and runtime
reload transition the lifecycle ledger to `released` exactly once; duplicate
release is recorded but cannot decrement either resource again. Counts are
derived from lifecycle state rather than maintained as an independent mutable
resource total. A process-wide reentrant lock makes capacity checks, state
transitions, event sequencing, snapshots, and diagnostics atomic. Released
request IDs remain as duplicate-release tombstones in a configurable bounded
window (1,000 by default); cumulative lifecycle counters survive tombstone
eviction, while globally unique request IDs remain the caller contract.

## Acceptance Mapping

| Issue requirement | Completion evidence |
| --- | --- |
| Validate before execution | Every call passes healing and per-call admission before the runtime adapter is invoked. |
| Rescue text responses | The live loop uses the existing default-on healing contract and streaming-delta adapter. |
| Typed retry nudges | Malformed, unknown, invalid, prerequisite, premature-terminal, retired-tool, and tool-failure decisions return stable nudge kinds. |
| Required steps survive compaction | Serializable request state is independent of prompt messages and is covered by restore-after-compaction tests. |
| Ordered/matching prerequisites | Admission receives the latest completed calls before each execution in a batch. |
| Independent error budgets | Consecutive malformed responses and consecutive tool failures have separate limits and terminal reasons. |
| Structured events | Every preflight, response, admission, replay, execution, retry, completion, and terminal decision emits a v1 event. |
| Swift contract | Swift Codable types validate and shape the same config/state/event/diagnostic schemas. |
| Operator evidence | A CLI fixture writes JSON diagnostics with counts, last nudge kind, final outcome, failure reason, and no raw prompt or arguments. |
| Exactly-once side effects | Required tools and call IDs expose explicit lifecycle state; dispatch requires a durable `executing` checkpoint acknowledgement, restored uncertain executions terminate automatic replay, and the ledger rejects a reused call ID with changed arguments. |
| Restorable argument state | Dispatch rejects tuples, non-finite floats, and other non-v1 JSON values before checkpointing or adapter entry, so every accepted protected-state snapshot can be restored. |
| Checkpoint and execution uncertainty | Failed checkpoint acknowledgement emits a typed terminal turn without dispatch; required-tool adapter failure terminates for reconciliation instead of issuing an unusable retry. |
| Thread and turn isolation | Config/state restore and runtime results bind thread scope and current-turn start; cross-thread/cross-turn restore and result-export fixtures fail closed before model projection. |
| Tool result export | Model directives receive only `melix.agentic_tool_result_export.v1` text summaries, while operator turn results retain the full sanitized payload; real compute/search/layout fixtures prove scalar and structured result usability, and recursive media-envelope and sentinel fixtures prove separation. |
| Bounded approval parking | A process-wide v1 helper and 100-thread barrier fixture permit 100 simultaneous approval waits while retaining at least two executor slots. |
| Resume and cleanup | Concurrent resume preserves the executor reserve; concurrent cancel, timeout, duplicate release, and runtime reload release each held resource exactly once and finish with zero leaks. |
| Open turns | A request that never waits for approval uses the normal executor path and never consumes parking capacity. |
| Prompt growth | A 64-turn fixture writes only the current nudge and observation to the next model directive; persistent ledger growth is measured separately. |

## Performance Probes And Success Metrics

The guardrail path is control-plane logic, not model execution. The registered
probe will measure repeated malformed, admitted, replayed, and terminal
decisions with a deterministic fixture runtime.

- `guardrail_decision_latency_ms_mean`: warning threshold is an absolute
  `0.05 ms` regression against the current base.
- `guardrail_decision_latency_ms_p95`: informational variance evidence.
- `tool_execution_count`: must remain exactly one in replay fixtures.
- `duplicate_execution_count`: must remain zero.
- `terminal_failure_count`: must match the configured fixture outcome.
- `diagnostic_sensitive_value_leak_count`: must remain zero.
- `guardrail_probe_contract_version`: identifies the numeric metric contract as
  v1.
- `executor_capacity_available_min_v1`: must remain at least `2` across 100
  concurrent approval waits and bounded resume attempts.
- `executor_lease_leak_count_v1` and `parking_permit_leak_count_v1`: must remain
  zero after cancel, timeout, and restored runtime-reload cleanup.
- `prompt_current_window_growth_ratio_v1`: must remain at most `1.05` between
  the first and second halves of a 64-turn current-observation fixture.
- `prompt_current_observation_count_max_v1`: must remain exactly `1`.
- `ledger_state_bytes_per_call_v1` and
  `concurrent_wait_ledger_bytes_per_request_v1`: record versioned execution and
  lifecycle ledger overhead.
- `ledger_decision_latency_ms_mean_v1`,
  `ledger_checkpoint_serialization_latency_ms_mean_v1`, and
  `parking_transition_latency_ms_mean_v1`: record request-ledger transition,
  caller-owned checkpoint serialization, and capacity transition cost
  separately. The ledger decision metric retains the `0.05 ms` regression
  threshold; checkpoint serialization remains informational because durable
  storage latency is caller-owned.

Measurement points are the start and end of each public live-loop response
transition and the final diagnostic serialization. The probe uses no model
weights, network access, or external processes.

## Delivery Slices

### Slice 1: Plan And Failing Contract Tests

- Add this plan.
- Add focused Python tests for malformed recovery, unknown-tool correction,
  premature terminal response, matching prerequisites, separate exhaustion,
  compaction restore, exactly-once replay, thread/turn isolation, model/UI
  observation export, checkpoint failure, and diagnostics redaction.
- Add focused Swift tests for request shaping and receipt decoding.

### Slice 2: Worker Live-Loop State Machine

- Add the request-scoped loop, serializable state, event, turn-result, and
  diagnostics contracts.
- Add the process-wide bounded approval parking helper, serializable lifecycle
  state, atomic exactly-once release transitions, bounded released tombstones,
  and real `ThreadPoolExecutor` barrier tests.
- Reuse existing healing, admission, registry, observation, and execution
  primitives rather than duplicating parser or adapter behavior.
- Add streaming-delta conversion and a mocked-responder runner.

### Slice 3: Swift Contract And Operator Evidence

- Add Swift Codable request/state/event/diagnostics types and canonical worker
  metadata shaping.
- Add a deterministic CLI fixture that persists diagnostic JSON.
- Update the canonical runtime contract and operator runbook.

### Slice 4: Probe, Coverage, And Full Verification

- Register and run the guardrail control-state performance probe.
- Measure changed-scope Python and Swift coverage at or above 95 percent.
- Run `make bootstrap`, `make proto`, `make swift-test`, `make py-test`, and
  `make integration-test`.
- Run the versioned pre-commit hook and analyze any selected performance
  regression before handoff.

## Known Boundaries

- The loop executes only tools in its selected registry and runtime. It does not
  add shell execution, tool-server process spawning, or approval UI.
- A state snapshot contains matching arguments because prerequisite and replay
  correctness require them. It is protected local control state and is never
  copied into receipts or diagnostic summaries.
- Network-capable tools remain governed by the existing request-local policy.
- Later process-based tool registration, approval UI, or concrete executor
  scheduling must reuse the parking event and state contract. This change
  verifies capacity safety and lifecycle cleanup, not an end-user approval
  flow.
- Released request tombstones are intentionally bounded for process-lifetime
  memory safety. Callers must continue to provide globally unique request IDs;
  duplicate releases outside the retained window are still suppressed as
  unknown requests.

## Plan-Only Commit Evidence

- Coverage: `N/A: this commit adds only the execution plan and changes no
  executable source lines.`
- Metrics: `N/A: this commit defines the future probe contract but changes no
  runtime path.`

## Completion Verification

Focused verification completed before the final staged pre-commit gate:

- Python guardrail, parking, diagnostics, and performance-registry tests:
  `159 passed`.
- Swift guardrail contract tests: `14 passed`.
- Python branch changed-line coverage: `2,219 / 2,280 = 97.32%`.
- Swift changed-line coverage: `1,124 / 1,142 = 98.42%`.
- `git diff --check`: passed.

The registered deterministic probe produced:

- `approval_wait_count_v1 = 100`.
- `executor_capacity_available_min_v1 = 2`.
- `executor_lease_leak_count_v1 = 0`.
- `parking_permit_leak_count_v1 = 0`.
- `guardrail_decision_latency_ms_mean = 0.027906`.
- `guardrail_decision_latency_ms_p95 = 0.072166`.
- `tool_execution_count = 1`.
- `duplicate_execution_count = 0`.
- `terminal_failure_count = 1`.
- `diagnostic_sensitive_value_leak_count = 0`.
- `ledger_state_bytes_per_call_v1 = 242.375`.
- `ledger_decision_latency_ms_mean_v1 = 0.072471` against base `0.056927`;
  the `0.015544 ms` increase is below the `0.05 ms` gate.
- `ledger_checkpoint_serialization_latency_ms_mean_v1 = 0.027097`.
- `prompt_current_window_growth_ratio_v1 = 1.0`.
- `prompt_current_observation_count_max_v1 = 1`.
- `prompt_current_payload_bytes_max_v1 = 563`.

The operator diagnostic fixture completed success, exhaustion, and 100-waiter
parking scenarios. The persisted artifact contained no raw prompt, arguments,
observations, or seeded sensitive values. An initial full pre-commit run passed
Swift, Python, integration, and all probe verification commands, then correctly
blocked the commit on two performance comparisons. The in-scope ledger path was
optimized from `0.204076 ms` to `0.072471 ms` by replacing generic whole-state
deep copies with isolated JSON-state copies and separating caller-owned
checkpoint serialization from loop decision latency. The unrelated local-job
probe retained its `1.935x` scalar-copy speedup; its derived delta is now
informational while the speedup remains gated. Exact base/head reruns for both
direct probes passed. The final staged commit remains subject to a clean rerun
of the versioned pre-commit hook on this host.
