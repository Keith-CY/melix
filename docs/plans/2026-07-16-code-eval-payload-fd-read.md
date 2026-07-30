# Code Eval Payload FD Read Slice

## Scope

This performance slice keeps the existing code-evaluation payload parsing behavior and narrows the file loading step for real filesystem paths. `_load_payload_file()` now reads payload bytes through an fd-based `os.open`/`os.fstat`/`os.read` path before the existing byte-level fast parser runs. Non-filesystem test doubles still fall back to their `read_bytes()` method.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The registry entry has focused commands for:

- `test_command`
- `coverage_command`
- `probe_command`

This slice extends the focused test and coverage command with `test_load_payload_file_uses_os_read_for_real_paths`, which proves real payload paths no longer route through `Path.read_bytes()`, and `test_read_payload_file_bytes_handles_fallback_and_fd_errors`, which covers the fallback and fd error paths.

## Expected impact

The expected local effect is lower elapsed time and lower traced peak allocation for repeated code-eval payload loads in `scripts/code_eval_payload_json_probe.py`, because the real-path byte loading avoids the higher-level `Path.read_bytes()` wrapper while preserving the existing fast JSON field extraction and full-JSON fallback behavior.

## Verification plan

Run on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_uses_os_read_for_real_paths \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_read_payload_file_bytes_handles_fallback_and_fd_errors \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_runner_script_loads_config_from_bytes \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_uses_compact_field_offsets \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_skips_reserved_metadata_keys \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_compact_field_offset_fallback_reuses_known_key_index \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_eval_payload_fast_path_decodes_known_status_values \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_eval_payload_missing_required_field_falls_back_to_json_parse \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_reuses_precomputed_key_tokens \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_unexpected_key_order \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_escaped_fields \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_payload_fast_path_field_extractors_cover_malformed_edges \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/code_eval_runner.py \
  services/mlx-worker-python/tests/test_code_eval_runner.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/code_eval_payload_json_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_payload_json_probe.py
```

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
