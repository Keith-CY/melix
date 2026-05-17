# Serving diagnostics default event JSONL streaming

## Scope

This Python-only performance slice targets serving diagnostics event JSONL output
in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The debug queue commonly retains events with the default empty attributes mapping,
and the registered queue probe serializes those retained events in each sample.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for the serving diagnostics
module, tests, and probe script.

## Optimization Plan

- Preserve the public JSONL key order, compact formatting, string escaping, and
  numeric coercion fallback behavior for non-default/non-exact event rows.
- Add a focused regression test proving default-attribute event JSONL rows can be
  streamed without materializing `ServingDiagnosticsEvent.to_dict()` payloads.
- Route `_write_jsonl()` through a narrow fast path for `ServingDiagnosticsEvent`
  instances with default empty attributes and exact `int`/`float` numeric fields;
  fall back to the existing stable encoder for all other rows.

## Validation

Run the registered probe locally on Linux with focused tests and changed-scope
coverage before opening the PR. CI PR-scoped performance remains the merge gate.
