# Event extraction JSON end fast path

## Scope

This Python performance slice is limited to the event-extraction response JSON parser helpers in `worker.productization.event_extraction`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

## Optimization plan

The parser already decodes direct JSON objects and fenced JSON responses with `JSONDecoder.raw_decode` and then validates that the remaining suffix is either empty, whitespace, or an optional closing fence.

This slice adds a constant-time end-of-string fast path to the trailing validation helpers so the common exact-end decode path avoids entering the generic whitespace/fence scanner.

## Verification

Local Linux validation must run:

1. The registered focused tests for `event-extraction-response-json-fence-trim`.
2. The registered changed-scope coverage command.
3. The registered local probe command.

GitHub Actions PR-scoped performance remains the final registered probe merge gate.

## Expected metrics

The primary expected direction is lower `elapsed_ms_mean` and `direct_elapsed_ms_mean` on the registered event-extraction response JSON probe. Peak memory should remain stable because this slice changes only branch flow and does not allocate new parser data structures.
