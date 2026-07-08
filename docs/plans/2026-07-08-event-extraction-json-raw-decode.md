# Event extraction response JSON raw-decode fast path

This Python-only performance slice is limited to `worker.productization.event_extraction._parse_response_json()`.
It keeps response parsing behavior unchanged while making direct object responses and leading-whitespace object responses use the shared `JSONDecoder.raw_decode` path instead of delegating to `json.loads`.

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe `Event extraction fenced JSON trim` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe script is `scripts/event_extraction_response_json_probe.py`. It reports:

- `elapsed_ms_mean` for leading-whitespace unfenced JSON object responses.
- `direct_elapsed_ms_mean` for direct unfenced JSON object responses.
- `peak_bytes_mean` and `direct_peak_bytes_mean` allocation measurements.

## Slice plan

1. Add a focused regression guard proving object fast paths no longer call the slower `_JSON_LOADS` helper.
2. Route both direct and leading-whitespace object responses through `_JSON_RAW_DECODE` and the existing trailing-whitespace validation helper.
3. Run focused event extraction tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Validation boundary

This slice changes Python worker code only. Local Linux validation covers the behavior tests, changed-scope coverage, and registered Python probe. No Swift/macOS runtime effect is claimed.
