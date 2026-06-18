# Event response JSON direct-object fast path

## Slice

Optimize only the event extraction response parser for the common provider output shape where the response starts directly with a JSON object (`{...}`), without a markdown fence or leading whitespace.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. This slice also extends `scripts/event_extraction_response_json_probe.py` to emit a direct-object metric alongside the existing leading-whitespace unfenced metric, so the optimized branch is measured by the registered probe.

- `test_command`: focused event extraction parser tests and PR-scoped probe registry tests.
- `coverage_command`: same focused tests with changed-scope coverage for `event_extraction.py`, tests, registry, and probe script.
- `probe_command`: `scripts/event_extraction_response_json_probe.py`, including `direct_elapsed_ms_mean` for direct JSON object responses.

## Implementation plan

1. Preserve fenced JSON, leading-whitespace, generic-fence, and trailing-data semantics.
2. Add a direct-object branch before markdown-fence detection so unfenced direct JSON avoids the leading whitespace scan and repeated fence prefix checks.
3. Add a focused regression test for direct object parsing.
4. Run focused tests, changed-scope coverage, and the registered probe on Linux before opening the PR.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
