# Event Response JavaScript Fence Fast Path

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/productization/event_extraction.py`, specifically the zero-offset generic fenced JSON response path used by `_parse_response_json(...)` for common ` ```javascript\n...\n``` ` model responses.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the event response parser, focused event-extraction tests, PR-scoped performance selection tests, and `scripts/event_extraction_response_json_probe.py`.

The existing probe reports `generic_fence_elapsed_ms_mean` and `generic_fence_peak_bytes_mean`, which exercise the ` ```javascript ` fenced response case.

## Change

Add a constant-offset fast path for zero-offset ` ```javascript\n ` fenced responses. This avoids scanning for the first newline via `str.find(...)` when the common JavaScript-tagged fence marker is already known, while preserving the generic fenced fallback for other labels and all existing JSON-object validation and closing-fence handling.

## Verification Plan

1. Add regression coverage that a zero-offset JavaScript fence does not call `str.find(...)` for the newline boundary.
2. Run the registered focused tests for `event-extraction-response-json-fence-trim`.
3. Run the registered changed-scope coverage command.
4. Run the registered probe locally on Linux against `origin/main` and this branch.
5. Use GitHub Actions PR-scoped performance as the final merge gate after opening the PR.
