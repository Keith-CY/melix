# Event extraction fenced JSON newline trailer fast path

## Scope

This Python-only performance slice targets fenced event-extraction response parsing in
`services/mlx-worker-python/worker/productization/event_extraction.py`.

The affected path is covered by the registered PR-scoped performance probe
`event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_response_json_probe.py`

## Optimization hypothesis

After `json.JSONDecoder.raw_decode(...)` parses a fenced JSON payload, the parser
only needs to validate that the remaining trailer is either whitespace or a
closing Markdown fence plus whitespace. The common emitted shape places the
closing fence on the next line (newline followed by three backticks). Adding a
narrow fast path for that newline-plus-fence trailer avoids the generic
whitespace/fence loop while
preserving the fallback for partial fences, leading whitespace, and rejected
trailing text.

## Verification plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_partial_fenced_json_without_line_list \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_trims_closing_fence_with_trailing_space \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_leading_whitespace_before_fence \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_accepts_unfenced_json_without_pretrim_copy \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_trailing_text_after_fenced_json \
  services/mlx-worker-python/tests/test_event_extraction.py::test_parse_response_json_rejects_fenced_non_object_payload \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_response_json_probe_script_emits_metrics
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && \
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && \
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/event_extraction.py \
  services/mlx-worker-python/tests/test_event_extraction.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/event_extraction_response_json_probe.py
```

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/event_extraction_response_json_probe.py
```

The PR-scoped performance workflow must select and complete
`event-extraction-response-json-fence-trim` in CI before merge.

## Success criteria

- Focused behavior tests pass.
- Changed-scope coverage for touched Python paths is at least 95%.
- The registered local probe shows lower `elapsed_ms_mean` on the fenced JSON
  parser hot path without a peak-memory regression.
