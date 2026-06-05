# Event response JSON raw-decode binding

## Scope

This Python-only performance slice targets fenced event-extraction response parsing in `services/mlx-worker-python/worker/productization/event_extraction.py`.

The affected path is covered by the registered PR-scoped performance probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the event response JSON parser.

## Optimization

Bind `json.JSONDecoder().raw_decode` once at module load time and reuse the bound callable inside `_parse_response_json()`. The parser is called repeatedly for fenced model responses; avoiding repeated descriptor/attribute lookup keeps behavior unchanged while shaving the hot fenced JSON path.

This slice does not alter response validation, closing-fence handling, or unfenced `json.loads()` behavior.

## Verification plan

- Run the registered focused pytest command for `event-extraction-response-json-fence-trim`.
- Run the registered changed-scope coverage command for the same probe.
- Run the registered probe locally on Linux against an `origin/main` baseline and this head branch.
- Use PR-scoped performance CI as the merge gate for the registered probe report.

## Environment boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior is changed.
