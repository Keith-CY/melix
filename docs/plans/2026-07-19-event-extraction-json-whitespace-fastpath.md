# Event extraction JSON whitespace fast path

This Python-only performance slice is limited to the event-extraction response JSON parser in `worker.productization.event_extraction`.

## Scope

The parser already avoids pre-trimming response strings and uses `JSONDecoder.raw_decode` for direct-object and fenced-object responses. This slice keeps the same parse and validation behavior while binding the raw decoder and trailing-validation helpers once per call so repeated hot-path branches avoid global lookups.

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.

The probe has focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

## Verification plan

1. Run the registered focused tests from the probe.
2. Run the registered changed-scope coverage command.
3. Run the registered probe locally on Linux against `origin/main` and this branch with repeated samples.
4. Use GitHub Actions PR-scoped performance as the merge gate.

## Acceptance criteria

Accept this slice only if focused tests and coverage pass, the local registered probe does not regress the JSON parser metrics, and the PR-scoped performance CI probe completes successfully.
