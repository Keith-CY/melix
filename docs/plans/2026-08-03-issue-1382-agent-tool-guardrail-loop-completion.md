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
registration API, scheduled agent execution API, or approval-wait executor
pool. Command-registration rollback and approval parking therefore remain
outside the executable surface of this issue. The completion must still fail
closed at the selected registry, preserve owner-scoped observation checks, and
leave typed extension points for later execution-policy and capacity work.

## Architecture

The Python worker owns a new request-scoped `AgenticToolGuardrailLoop`. It
accepts a registry, deterministic runtime, required tools, prerequisites, and
explicit budgets. It owns a serializable state snapshot containing completed
steps and an execution ledger. Prompt messages are inputs to generation only;
they are never the source of control-flow truth.

Each model response follows one path:

1. normalize or rescue candidate tool calls;
2. admit calls one at a time against the latest completed-step state;
3. suppress exact replay by call identity and fail closed on identity reuse with
   different arguments;
4. execute admitted calls and update the completed-step state only after a
   completed observation;
5. apply independent consecutive malformed-response and tool-failure budgets;
6. retire tool execution after all required steps complete and request one
   final answer without tools;
7. emit sanitized decision events and a deterministic diagnostic summary.

The Swift control plane owns Codable request, state, event, and diagnostics
contracts for the same schema versions. Request shaping writes canonical JSON
into worker execution metadata without moving execution truth into Swift.

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
| Exactly-once side effects | The execution ledger suppresses identical replay and rejects a reused call ID with changed arguments. |

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

Measurement points are the start and end of each public live-loop response
transition and the final diagnostic serialization. The probe uses no model
weights, network access, or external processes.

## Delivery Slices

### Slice 1: Plan And Failing Contract Tests

- Add this plan.
- Add focused Python tests for malformed recovery, unknown-tool correction,
  premature terminal response, matching prerequisites, separate exhaustion,
  compaction restore, exactly-once replay, and diagnostics redaction.
- Add focused Swift tests for request shaping and receipt decoding.

### Slice 2: Worker Live-Loop State Machine

- Add the request-scoped loop, serializable state, event, turn-result, and
  diagnostics contracts.
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
- Later process-based tool registration or approval-wait scheduling must reuse
  the event and state contract, but cannot be verified before those product
  surfaces exist.

## Plan-Only Commit Evidence

- Coverage: `N/A: this commit adds only the execution plan and changes no
  executable source lines.`
- Metrics: `N/A: this commit defines the future probe contract but changes no
  runtime path.`
