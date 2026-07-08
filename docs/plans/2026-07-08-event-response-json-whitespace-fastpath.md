# Event extraction response JSON whitespace fast path performance slice

## Scope

This Python-only performance slice is limited to `_skip_json_whitespace()` in `services/mlx-worker-python/worker/productization/event_extraction.py`.

The response JSON parser already avoids line-list materialization and uses direct JSON fast paths for unfenced and fenced model responses. This slice keeps behavior identical while separating the common ASCII JSON whitespace branch from the rarer Unicode whitespace fallback so hot parsing of model responses avoids the `str.isspace()` call for spaces, tabs, carriage returns, and newlines.

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

## Implementation plan

1. Preserve `_skip_json_whitespace()` behavior for ASCII and Unicode whitespace, with regression coverage for ASCII control-character boundaries and Unicode whitespace fallback.
2. Check ASCII JSON whitespace first and call `str.isspace()` only for non-ASCII/non-JSON-whitespace characters.
3. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Validation boundary

This slice changes Python worker code only. Linux local validation covers focused Python tests, changed-scope coverage, and the registered performance probe. No Swift/macOS runtime effect is claimed for this slice.
