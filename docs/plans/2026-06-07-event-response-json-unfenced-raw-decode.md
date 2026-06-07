# Event response JSON unfenced raw decode

This Python-only performance slice is limited to `worker.productization.event_extraction._parse_response_json` for unfenced JSON responses with leading/trailing whitespace.

## Scope

- Replace the final unfenced `json.loads(response_text)` fallback with `JSONDecoder.raw_decode` starting at the already-discovered non-whitespace offset.
- Preserve strict unfenced semantics: only trailing whitespace is accepted after the decoded JSON object; markdown closing fences remain accepted only for fenced responses.
- Update the registered `event-extraction-response-json-fence-trim` probe coverage to include the new unfenced direct-JSON case.

## Verification

- Focused parser tests in `services/mlx-worker-python/tests/test_event_extraction.py`.
- Changed-scope coverage through the registered PR-scoped probe command.
- Local Linux command-json probe via `scripts/event_extraction_response_json_probe.py`.
- GitHub Actions PR-scoped performance report remains the merge gate for base-vs-head comparison.

## Metrics

The probe measures mean elapsed milliseconds and mean peak bytes while repeatedly parsing a synthetic event response payload. This slice updates the synthetic payload to exercise the unfenced direct-JSON response path with leading and trailing whitespace.
