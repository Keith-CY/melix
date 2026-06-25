# Event response JSON fence-prefix fast path

## Slice

Optimize only `worker.productization.event_extraction._parse_response_json` for
direct markdown-fenced JSON responses that start with `` ```json\n ``. The
change keeps direct object, leading-whitespace object, leading-whitespace fence,
generic fence, non-object rejection, and trailing-data semantics unchanged.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe
`event-extraction-response-json-fence-trim` in
`infra/perf/pr_scoped_probes.json`.

- `test_command`: focused event extraction parser tests and PR-scoped probe
  registry tests.
- `coverage_command`: the same focused parser and registry tests with
  changed-scope coverage for the parser, tests, registry, and probe script.
- `probe_command`: `scripts/event_extraction_response_json_probe.py`, including
  `elapsed_ms_mean` for markdown-fenced JSON responses and
  `direct_elapsed_ms_mean` for direct JSON object responses.

## Implementation plan

1. Preserve the first-byte backtick guard for the common direct-fence path.
2. Replace the direct-fence `startswith()` call with a bounded prefix slice
   comparison after confirming the response is at least as long as the JSON
   fence prefix. This avoids an extra method dispatch on the hot fenced-response
   path while preserving exact prefix matching.
3. Leave the leading-whitespace and generic-fence branches unchanged.
4. Verify locally on Linux with focused tests, changed-scope coverage, and the
   registered probe before opening the PR.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.
