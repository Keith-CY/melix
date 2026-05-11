# Code Evaluation Payload Fast-Path Plan

## Goal

Reduce avoidable JSON materialization when the Python code-evaluation parent process
loads the sandbox runner result payload. The parent only needs the small fixed
status field set emitted by the runner, while probe-sized payloads can contain
large diagnostic metadata that should not be materialized on the hot path.

## Scope

This slice is intentionally limited to the Python code-evaluation payload loader
and its direct regression coverage. It does not change sandbox execution,
candidate compilation, test instrumentation, stdio truncation, or generated
protocol artifacts.

## Registered Probe

Primary PR-scoped probe:

- `code-eval-payload-json-bytes`
  - `elapsed_ms_mean`: informational.
  - `peak_bytes_mean`: lower is better, with the registered 5 percent warning
    threshold.

The affected path is already registered in `infra/perf/pr_scoped_probes.json`
with focused `test_command`, `coverage_command`, and `probe_command` entries.

## Implementation Notes

- Keep the byte-oriented payload read path so callers do not perform a separate
  text decode before JSON handling.
- Add a narrow fixed-field extractor for runner-shaped payloads containing the
  result fields consumed by `run_python_code_evaluation`.
- Fall back to full JSON decoding for non-runner payloads or escaped string
  fields so the existing private helper semantics remain available to tests and
  diagnostic callers.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_runner_fields_without_metadata_parse \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_escaped_fields \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_runner_fields_without_metadata_parse \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_escaped_fields \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/code_eval_runner.py \
  services/mlx-worker-python/tests/test_code_eval_runner.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/code_eval_payload_json_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_payload_json_probe.py
```
