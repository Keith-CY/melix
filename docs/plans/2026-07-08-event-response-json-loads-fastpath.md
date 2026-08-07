# Event extraction response JSON loads fast path

## Scope

This Python-only performance slice targets `services/mlx-worker-python/worker/productization/event_extraction.py`, specifically direct or leading-whitespace JSON object responses in `_parse_response_json`.

The common event-extraction response shape is a full JSON object with optional surrounding whitespace. The previous path used `JSONDecoder.raw_decode()` and then performed a Python-level trailing whitespace scan. This slice keeps fenced-response behavior unchanged while using the standard `json.loads` C-backed complete-document parser for unfenced JSON object responses.

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries, and its synthetic payload measures both leading-whitespace and direct unfenced JSON responses.

## Verification plan

Run locally on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_inline_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_generic_fence_after_fast_json_prefix services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_leading_whitespace_object_skips_fence_prefix_checks services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_leading_whitespace_object_rejects_trailing_text services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_leading_whitespace_rejects_non_object_payload services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_direct_object_fast_path services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_unfenced_closing_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics
```

Then run the registered coverage command and compare the registered probe against `origin/main` with `scripts/pr_scoped_performance_run.py`.

## Success criteria

- Focused parser and PR-scoped registry tests pass.
- Changed-scope coverage remains at or above the repository threshold.
- The registered local probe reports improved or stable `elapsed_ms_mean` and `direct_elapsed_ms_mean`; CI PR-scoped performance remains the merge gate.
