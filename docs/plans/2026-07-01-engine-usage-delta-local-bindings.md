# Engine Usage Delta Local Bindings

## Scope

This slice keeps the engine generate usage accounting behavior unchanged while
reducing per-request work in the `UsageDelta` construction path. It targets the
plain text and fallback usage probe path covered by the registered
`engine-generate-usage-token-elision` PR-scoped performance probe.

## Registered Probe

The affected path is already covered by `infra/perf/pr_scoped_probes.json`:

- `engine-generate-usage-token-elision`

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `worker/engine/engine_core.py`,
`test_generate_stream.py`, and `scripts/engine_generate_usage_token_probe.py`.

## Implementation Plan

1. Preserve `UsageDelta` field semantics for empty and media-usage calls.
2. Bind sanitized token counts once before constructing the protobuf message.
3. Fast-path empty media usage so the common text-only path avoids repeated
   dictionary lookup and zero sanitization for media counters.
4. Verify with focused engine tests, changed-scope coverage, and the registered
   probe on Linux.

## Validation

GitHub Actions PR-scoped performance remains the final registered probe gate.
Local Linux validation should include the focused command set from the registered
probe plus repeated probe samples before merge.
