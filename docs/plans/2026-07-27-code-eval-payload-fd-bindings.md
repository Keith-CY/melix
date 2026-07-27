# Code Eval Payload FD Helper Bindings

This Python-only performance slice is limited to code evaluation payload byte loading in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Scope

- Bind the fd-based payload helpers (`os.open`, `os.fstat`, `os.read`, `os.close`, and `os.O_RDONLY`) at module import time.
- Keep the existing fd-based payload load behavior and fallback behavior unchanged.
- Add regression coverage that the hot path uses the bound helpers while preserving error handling.

## Registered probe

Affected path coverage is provided by the registered PR-scoped performance probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused `test_command` for code-eval payload loading and PR-scoped selection tests;
- changed-scope `coverage_command` for the code eval runner, tests, registry test, and probe script;
- `probe_command` via `scripts/code_eval_payload_json_probe.py`.

## Local validation plan

Run on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_uses_os_read_for_real_paths services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_payload_file_bytes_handles_fallback_and_fd_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_payload_file_bytes_uses_bound_fd_helpers services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_uses_os_read_for_real_paths services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_payload_file_bytes_handles_fallback_and_fd_errors services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_payload_file_bytes_uses_bound_fd_helpers services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_payload_json_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_payload_json_probe.py
```

GitHub Actions PR-scoped performance remains the merge gate.
