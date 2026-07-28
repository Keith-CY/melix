# Event Extraction JSON Closing-Fence Tail Fast Path

This Python performance slice is limited to `worker.productization.event_extraction._has_only_optional_closing_fence()`.

## Scope

LLM event-extraction responses commonly arrive as fenced JSON with an exact closing tail of either `\n```   ` or inline ```   `. The existing parser already validates those tails without allocating a trimmed copy, but still calls the generic JSON-whitespace scanner after matching the closing fence. This slice preserves response parsing behavior while returning immediately for those two common exact tails.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.

The probe watches:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

It includes focused `test_command`, `coverage_command`, and `probe_command` entries. Local Linux validation uses the registered commands before PR creation, and GitHub Actions PR-scoped performance remains the merge gate.

## Verification Plan

1. Add a regression guard proving exact common closing-fence tails avoid the generic whitespace scanner.
2. Implement only the exact-tail early return in `_has_only_optional_closing_fence()`.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Include old/new local probe metrics and CI PR-scoped performance evidence in the PR body.
