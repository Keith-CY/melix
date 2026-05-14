# Event Response JSON Zero-Copy Prefix Slice

## Scope

This Python-only performance slice narrows `worker.productization.event_extraction._parse_response_json(...)` without changing the response contract. The parser still accepts plain JSON objects, markdown-fenced JSON objects, leading whitespace before a fence, missing closing fences, and closing fences with trailing whitespace.

## Optimization

The prior parser called `response_text.strip()` before every parse, copying large LLM response strings even when the response was already clean or only needed a fence-prefix check. This slice scans leading whitespace by index, parses fenced payloads from the original string with `JSONDecoder.raw_decode(...)`, and lets `json.loads(...)` handle whitespace for non-fenced JSON.

## Registered Probe

The affected path is covered by the existing `event-extraction-response-json-fence-trim` PR-scoped probe in `infra/perf/pr_scoped_probes.json`. The probe includes focused pytest, changed-scope coverage, and `scripts/event_extraction_response_json_probe.py`, which repeatedly parses a large partially fenced event-extraction response and reports elapsed time and peak traced memory.

## Verification Plan

Run locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/event_extraction.py services/mlx-worker-python/tests/test_event_extraction.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/event_extraction_response_json_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_EVENT_RESPONSE_JSON_PROBE_SAMPLES=7 uv run --project services/mlx-worker-python python3 scripts/event_extraction_response_json_probe.py
```

CI remains the merge gate for the registered PR-scoped performance workflow.
