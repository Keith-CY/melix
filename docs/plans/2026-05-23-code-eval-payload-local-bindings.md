# Code Eval Payload Local Bindings Performance Slice

## Goal

Reduce repeated global helper lookups in the code-evaluation payload byte fast path without changing payload parsing behavior.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `docs/plans/2026-05-23-code-eval-payload-local-bindings.md`

## Registered Probe

The affected path is already covered by the PR-scoped registered probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. That probe has focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `ubuntu-latest`.

## Implementation Plan

1. Keep the existing payload regression tests and registered probe unchanged.
2. Bind `_json_field_value_start_for_token`, `_extract_json_string_field_at`, and `_extract_json_int_field_value_and_end` to local variables inside `_extract_code_eval_payload_fields(...)` before the hot field loop.
3. Run the probe's focused tests, changed-scope coverage command, and probe command locally on Linux.
4. Use PR-scoped performance CI as the final registered probe validation before merge.

## Metrics

Primary metric: `code-eval-payload-json-bytes` `elapsed_ms_mean` (reported as informational by the registry). Secondary metric: `peak_bytes_mean` (lower is better).

## Validation Boundary

This is a Python-only parsing-path slice. Local Linux validation covers the behavior, changed-scope coverage, and registered probe. No Swift runtime behavior is changed.
