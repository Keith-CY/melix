# Code evaluation payload required-field gate elision

This Python-only performance slice is limited to the code-evaluation payload JSON
fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The fast path already walks the required code-eval payload fields in a fixed
order and returns `None` as soon as a required key or parseable value is missing.
A second required-field membership gate at the end repeated work on every
successful fast-path parse. This slice removes that redundant final gate and
makes malformed string extraction return `None` immediately so incomplete or
escaped payloads still fall back to the normal `json.loads` path.

Registered PR-scoped probe: `code-eval-payload-json-bytes` in
`infra/perf/pr_scoped_probes.json`. The entry declares focused `test_command`,
`coverage_command`, and `probe_command` values for this path and runs on
`ubuntu-latest`.

Verification scope:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_eval_payload_missing_required_field_falls_back_to_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_reuses_precomputed_key_tokens services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_unexpected_key_order services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_escaped_fields services/mlx-worker-python/tests/test_code_eval_runner.py::test_payload_fast_path_field_extractors_cover_malformed_edges services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_eval_payload_missing_required_field_falls_back_to_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_reuses_precomputed_key_tokens services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_unexpected_key_order services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_escaped_fields services/mlx-worker-python/tests/test_code_eval_runner.py::test_payload_fast_path_field_extractors_cover_malformed_edges services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_payload_json_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_payload_json_probe.py
```

Acceptance criteria:

- Focused code-eval payload tests pass.
- Changed-scope coverage for touched lines remains at least 95%.
- The registered probe preserves payload byte size and peak memory while showing
  a non-regressing or improved JSON payload parse mean.
- PR-scoped performance CI completes the registered probe before merge.
