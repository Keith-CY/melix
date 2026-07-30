# Event extraction response JSON startswith binding

## Scope

This Python-only performance slice is limited to
`worker.productization.event_extraction._parse_response_json`.

The response parser checks the same response string for fenced and unfenced JSON
prefixes while parsing high-volume event extraction responses. The slice keeps
parsing behavior unchanged while preserving the direct-object fast path and then
binding the response `startswith` method plus JSON fence constants once before
the fenced/leading-whitespace branch checks.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`event-extraction-response-json-fence-trim` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields and watches:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

## Verification plan

1. Run the registered focused tests locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered response JSON probe locally on Linux and compare the
   pre-change baseline against the head sample.
4. Use GitHub Actions PR-scoped performance as the final registered probe report
   and merge gate.

## Expected metrics

Expected direction is lower `elapsed_ms_mean` for fenced JSON responses and
stable or lower `direct_elapsed_ms_mean` for direct JSON responses in
`scripts/event_extraction_response_json_probe.py`.
