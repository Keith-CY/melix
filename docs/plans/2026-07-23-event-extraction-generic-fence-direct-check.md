# Event extraction generic fence direct-check performance slice

## Scope

This Python-only performance slice is limited to generic fenced response parsing in `services/mlx-worker-python/worker/productization/event_extraction.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The probe entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and watches the event-extraction parser, focused tests, PR-scoped performance tests, and `scripts/event_extraction_response_json_probe.py`.

## Change

After the JSON-specific fence prefix check has failed, the generic markdown fence branch only needs to know whether the next three characters are backticks. This slice replaces the second `str.startswith("```", response_start)` call with direct character checks, preserving behavior while avoiding one bound-method call on generic fenced responses.

## Verification plan

1. Keep existing behavior coverage for JSON fences, generic fences, direct objects, leading whitespace, trailing fences, and invalid trailing text.
2. Add a regression test proving generic fenced responses now perform only the JSON-specific prefix check through `startswith` before the direct marker check.
3. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
4. Require the registered PR-scoped performance workflow to pass before merge.

## Linux boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime effect is claimed.