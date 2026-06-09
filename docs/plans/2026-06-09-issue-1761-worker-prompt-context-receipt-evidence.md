# Worker Prompt Context Receipt Evidence

## Goal

Preserve chat prompt-context boundary receipts in Python worker completion
evidence so the executed request proves which untrusted prompt segments crossed
from the Swift control plane into the worker runtime.

## Scope

This slice covers `worker.engine.engine_core.EngineCore.generate(...)` and its
completed `parser_metrics`.

In scope:

- forward `melix.prompt_context.receipt_schema` from `ExecutionMetadata.ext` as
  `prompt_context_receipt_schema`
- forward `melix.prompt_context.receipt_count` as
  `prompt_context_receipt_count`
- forward `melix.prompt_context.receipts_json` as
  `prompt_context_receipts_json`
- keep plain and structured generation paths consistent
- document the worker evidence handoff in the unified runtime contract

Out of scope:

- changing prompt text, template rendering, parser behavior, or message roles
- parsing or rewriting the receipt JSON in the worker
- adding new RAG store, skill, memory, or background-continuation admission
  logic
- adding protobuf fields for prompt-context receipts

## Architecture

The Swift control plane now records `melix.untrusted_context_receipt.v1` prompt
context receipts in `GenerateRequest.execution.ext`. The Python worker already
copies other request-local evidence, such as compatibility policy receipts and
allowed-tool receipts, into `Completed.parser_metrics`. This slice adds the same
handoff for prompt-context receipts.

The worker treats these values as opaque evidence strings. It only forwards
non-empty ext values into completion metrics and does not parse raw receipt JSON.
That keeps the worker from revalidating or mutating receipt contents and avoids
accidentally exposing prompt text, media URLs, media bytes, or tool arguments.

## Performance Probes

The path adds up to three map lookups and string assignments per completed
generate request. No registered PR-scoped probe targets this metadata handoff.
The PR-scoped performance workflow remains the merge gate and should report
`Status: ok`, `Regressions: 0`, `Context regressions: 0`, and
`Verification failures: 0`.

## Verification

- TDD red/green pytest for completed parser metrics on a request carrying
  `melix.prompt_context.*` ext fields
- focused receipt pytest file
- changed-line coverage for touched Python source and test lines, target at
  least 95 percent
- `git diff --check`
- `.githooks/pre-commit` full local gate before commit
- remote CI and PR-scoped performance report before merge

## Success Criteria

- Completed generate events expose the three prompt-context receipt metrics when
  the request ext contains the three Swift control-plane receipt keys.
- Requests without prompt-context receipt ext do not emit empty
  prompt-context metrics.
- Plain and structured generation paths preserve existing completion, token
  route, compatibility policy, and allowed-tool receipt behavior.
- The unified runtime contract identifies the Python worker completion evidence
  handoff and leaves RAG, skill, memory, and background admission boundaries for
  later #1761 slices.
