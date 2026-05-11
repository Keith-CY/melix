# Event Extraction Response JSON Fence Trim Slice

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/productization/event_extraction.py`, specifically
`_parse_response_json(...)` when an LLM response starts with a Markdown code fence.
It does not change event scoring, semantic matching, generated protocol artifacts,
or Swift/macOS runtime behavior.

## Registered Probe

Registered PR-scoped probe: `event-extraction-response-json-fence-trim` in
`infra/perf/pr_scoped_probes.json`.

The probe provides focused:

- `test_command` for the fenced JSON parser regression tests and probe dispatch tests.
- `coverage_command` for changed-scope coverage across the parser, tests, registry, and probe script.
- `probe_command` for a synthetic partially fenced JSON response that previously required
  `splitlines()` plus `"\n".join(...)` before JSON parsing.

Metrics:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `event_count` (informational)

## Implementation Plan

1. Preserve parser behavior for complete fenced JSON, partially fenced JSON, and plain JSON responses.
2. Replace the fallback `splitlines()`/join path with index-based trimming so large partially fenced
   responses avoid allocating a full line list.
3. Keep the slice local to the parser, regression tests, probe script, and PR-scoped probe registry.
4. Verify locally on Linux with the registered focused test command, coverage command, and registered probe.

## Acceptance Criteria

- Focused event-extraction parser tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe reports improved or directionally neutral elapsed time and no guard-rail failures.
- CI PR-scoped performance selects and passes `event-extraction-response-json-fence-trim`.
