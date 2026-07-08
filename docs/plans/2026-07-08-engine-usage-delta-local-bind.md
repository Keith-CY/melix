# Engine usage non-negative integer fast path

## Scope

This Python-only performance slice is limited to `_non_negative_int()` in
`services/mlx-worker-python/worker/engine/engine_core.py`.

`_non_negative_int()` normalizes usage counters while emitting streaming
`Generate` response usage. These counters are already plain Python integers in
the hot path. This slice keeps behavior equivalent while returning directly for
exact `int` inputs, avoiding the fallback `int(value or 0)` conversion and
`max()` call for the common case.

## Registered Probe

Registered PR-scoped probe: `engine-generate-usage-token-elision`.

The registry entry covers `engine_core.py` and provides focused `test_command`,
`coverage_command`, and `probe_command` values. The probe reports no-usage stream
latency and fallback usage latency through `elapsed_ms_mean` and
`fallback_elapsed_ms_mean`, plus token/counting guard metrics.

## Verification Plan

- Run the registered focused test command for the engine usage slice.
- Run the registered changed-scope coverage command.
- Run `scripts/engine_generate_usage_token_probe.py` locally on Linux and compare
  the relevant metrics before and after the change.
- Let the PR-scoped performance workflow validate the registered probe on CI
  before merge.

## Expected Behavior

Usage payloads remain unchanged. The direct path only handles exact `int` values;
`bool`, strings, `None`, and custom numeric-like objects continue through the
existing fallback conversion path.
