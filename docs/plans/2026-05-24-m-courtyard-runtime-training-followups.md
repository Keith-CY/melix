# M-Courtyard Runtime and Training Follow-Ups

## Goal

Implement the remaining post-closure runtime compatibility and advanced
training follow-up issues from #1518 and #1519 as one locally integrated feature
branch with issue-scoped commits and verifiable evidence.

## Scope

This plan covers:

- #1522 request-local compatibility policy receipts.
- #1523 prompt-budget admission errors.
- #1524 parser declared wire-format and selector parity audit.
- #1525 shared stream and non-stream text finalization state.
- #1526 token-routed output assembly for reasoning, tools, and visible text.
- #1527 generation bounds and passthrough receipts.
- #1528 training admission validators and resolved-control receipts.
- #1529 LoRA artifact, resume, merge/export, and callback drift canaries.
- #1530 training runtime dependency preflights and failure cleanup guards.
- #1531 advanced training planner, backend, profiler, and numerical-policy
  receipts.

The feature branch intentionally keeps #1518 and #1519 closed; those parent
trackers already completed issue decomposition. This branch owns executable
follow-up implementation for the child issues above.

## Integration Strategy

Each child issue is implemented in its own worktree and branch first, then
merged into the local integration branch
`feat/m-courtyard-runtime-training-followups`.

| Issue | Branch | Primary Area | Merge Order |
|---|---|---|---|
| #1522 | `codex/issue-1522-compat-policy` | Swift request compatibility receipts plus worker evidence preservation | 1 |
| #1523 | `codex/issue-1523-prompt-budget` | Swift OpenAI admission and typed prompt-budget errors | 2 |
| #1524 | `codex/issue-1524-parser-audit` | Swift parser registry metadata and selector parity | 3 |
| #1527 | `codex/issue-1527-generation-bounds` | Swift request bounds normalizer and passthrough receipts | 4 |
| #1525 | `codex/issue-1525-finalizer-parity` | Python stream/non-stream finalization contract | 5 |
| #1526 | `codex/issue-1526-token-router` | Python channel-aware token routing, built after #1522/#1525 | 6 |
| #1528 | `codex/issue-1528-training-admission` | Python training admission validation receipts | 7 |
| #1529 | `codex/issue-1529-lora-canaries` | Python LoRA artifact and drift canaries | 8 |
| #1530 | `codex/issue-1530-runtime-preflight` | Python runtime dependency preflight and cleanup receipts | 9 |
| #1531 | `codex/issue-1531-training-planner` | Python planner/backend/profiler receipts | 10 |

The merge order keeps overlapping files from conflicting blindly:

- #1526 depends on the compatibility policy and finalizer surfaces from #1522
  and #1525.
- #1529, #1530, and #1531 all touch training manifest paths and should merge
  after #1528 establishes the admission and resolved-control receipt shape.
- Conflict resolution must preserve the stricter receipt contract when two
  branches add adjacent evidence fields.

## Runtime Compatibility Requirements

The runtime compatibility half must keep stream and non-stream behavior paired.
For every request-local receipt or typed admission error added to one route, the
paired route must either emit the same shape or record an explicit refusal or
exemption reason.

Minimum proof:

- Paired OpenAI stream and non-stream request-shaping tests.
- Worker evidence or completion-event tests that prove hidden reasoning content
  is not leaked.
- Parser registry audit tests that fail when metadata is missing.
- Finalizer fixtures for usage, finish reason, malformed channels, reasoning,
  and tool-call state.
- Token-router fixtures for auto, none, forced-valid, forced-missing tool,
  reasoning-only truncation, and alternate final terminator paths.

## Training Requirements

The training half must make admission, runtime preflight, artifact correctness,
and planner decisions visible as durable receipts before or alongside training
execution. Receipt fields should be stable JSON, deterministic in tests, and
written into existing run or adapter evidence artifacts rather than ad hoc logs.

Minimum proof:

- Invalid hyperparameter matrix tests with typed field-level details.
- Legal sentinel/default resolution tests.
- Adapter manifest tests for resolved controls, canaries, runtime preflight,
  planner, profiler, and backend decisions.
- Import-safe inspection tests for dependency-limited hosts.
- Focused cleanup test for nested-exception paths that emits bounded evidence.

## Verification Plan

Each issue branch must run:

```bash
git diff --check
```

plus its focused tests. The integration branch must then run the combined
touched-scope checks before a pull request:

```bash
make swift-test
make py-test
make integration-test
```

If a focused area is not measurable for runtime performance, the PR evidence
must state `N/A` with the reason. If the scoped performance gate selects probes,
the final PR body must include the generated metrics report and whether any
regression is direct, gated, or contextual.

## PR Evidence

The final pull request must use the repository template headings exactly and
include:

- This plan as the governing spec in `## Plan or Spec`.
- A per-issue command summary in `## Commands Run`.
- The full local gate and scoped metrics report in `## Coverage and Metrics`.
- Any intentionally deferred child issue or partial UI surface in `## Known
  Gaps`.

No child issue should be closed from local intent alone. Close or update each
issue only after the final PR has merged or after GitHub state proves the issue
was already satisfied by a merged PR.
