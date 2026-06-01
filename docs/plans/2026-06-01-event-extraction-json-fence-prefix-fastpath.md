# Event extraction JSON fence prefix fast path

## Scope

This Python-only performance slice targets fenced JSON response parsing in
`services/mlx-worker-python/worker/productization/event_extraction.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`event-extraction-response-json-fence-trim` in
`infra/perf/pr_scoped_probes.json`. The probe provides focused
`test_command`, `coverage_command`, and `probe_command` entries and measures
mean elapsed time, peak bytes, event count, sample count, iteration count, and a
checksum for the parsed event payload.

## Change

Most event-extraction model responses that include Markdown fences use the exact
` ```json\n` prefix. The existing parser already avoids building a stripped copy by using
`JSONDecoder.raw_decode`, but it still scans for the first newline before
parsing every fenced response. This slice adds an exact-prefix branch for the
common `json` fence and jumps directly to the JSON payload offset.

The generic fenced-response path remains in place for non-`json` fence labels,
so behavior for broader Markdown fences is preserved.

## Validation plan

1. Run the focused event-extraction response parsing tests and the registered
   PR-scoped performance registry tests for this probe.
2. Run changed-scope coverage for the changed implementation, test, registry,
   and probe files.
3. Run the registered probe locally on Linux against `origin/main` and this
   branch before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.
