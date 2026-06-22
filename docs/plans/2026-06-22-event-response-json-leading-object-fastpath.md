# Event response JSON leading-object fast path

## Slice

Optimize only `worker.productization.event_extraction._parse_response_json` for
unfenced JSON object responses that have leading whitespace. This keeps the
existing direct-object, fenced JSON, generic fenced JSON, and trailing-data
semantics unchanged.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`event-extraction-response-json-fence-trim` in
`infra/perf/pr_scoped_probes.json`.

- `test_command`: focused event extraction parser tests and PR-scoped probe
  registry tests. This slice adds an explicit regression proving the
  leading-whitespace object branch bypasses markdown-fence prefix checks.
- `coverage_command`: the same focused parser and registry tests with
  changed-scope coverage for the parser, tests, registry, and probe script.
- `probe_command`: `scripts/event_extraction_response_json_probe.py`, including
  `elapsed_ms_mean` for leading-whitespace unfenced JSON and
  `direct_elapsed_ms_mean` for direct JSON object responses.

## Implementation plan

1. Preserve the current leading whitespace scan so malformed non-whitespace
   prefixes still fail through `JSONDecoder.raw_decode` at the first
   non-whitespace character.
2. After the leading whitespace scan, add a `{` branch that calls the shared
   raw decoder immediately and validates only trailing whitespace. This avoids
   two markdown-fence prefix checks for the common unfenced object response.
3. Keep fenced and generic-fence handling below that branch unchanged.
4. Verify locally on Linux with focused tests, changed-scope coverage, and the
   registered command-json probe before opening the PR.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
