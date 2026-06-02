# Event response JSON zero-offset fence fast path

This Python-only performance slice targets fenced event-extraction response parsing in `services/mlx-worker-python/worker/productization/event_extraction.py`.

## Scope

LLM event-extraction responses commonly start directly with the canonical JSON fence prefix string (three backticks, `json`, then a newline) and have no leading whitespace. The existing parser always entered the leading-whitespace scan before checking the canonical fence. This slice adds a zero-offset canonical-fence fast path while preserving the existing fallback for leading whitespace, generic fences, unfenced JSON, and trailing-fence validation.

## Registered Probe

Affected path coverage uses the existing registered PR-scoped probe `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `scripts/event_extraction_response_json_probe.py`
- PR-scoped performance registry tests

## Verification Plan

Run the registered probe's focused test command, changed-scope coverage command, and local Linux registered probe runner:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_generic_fence_after_fast_json_prefix services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_generic_fence_after_fast_json_prefix services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/event_extraction.py services/mlx-worker-python/tests/test_event_extraction.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/event_extraction_response_json_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id event-extraction-response-json-fence-trim --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/event_response_json_prefix_zero_probe.json
```

## Acceptance Criteria

- Focused behavior and registry tests pass.
- Changed-scope coverage remains at or above 95% for the touched Python scope.
- Registered local probe preserves checksum/event-count metrics and improves or stays within acceptable noise for `elapsed_ms_mean` and `peak_bytes_mean`.
- PR-scoped performance CI completes the registered probe successfully before merge.
