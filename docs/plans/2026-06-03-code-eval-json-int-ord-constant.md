# Code evaluation JSON integer ord constant

This Python-only performance slice is limited to the code-evaluation payload JSON
fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The payload parser repeatedly scans integer fields such as `tests_passed` and
`tests_total` from UTF-8 JSON bytes. The digit scanner previously called
`ord("0")` inside the per-byte loop. This slice hoists that constant to module
scope so the hot loop subtracts a precomputed byte value while preserving the
existing byte-oriented parsing behavior and malformed-payload fallbacks.

Registered PR-scoped probe: `code-eval-payload-json-bytes` in
`infra/perf/pr_scoped_probes.json`. The entry already declares focused
`test_command`, `coverage_command`, and `probe_command` values for this path and
runs on `ubuntu-latest`.

Verification scope:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode services/mlx-worker-python/tests/test_code_eval_runner.py::test_code_eval_payload_required_field_check_preserves_fast_path_gate services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_reuses_precomputed_key_tokens services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_falls_back_for_unexpected_key_order services/mlx-worker-python/tests/test_code_eval_runner.py::test_payload_fast_path_field_extractors_cover_malformed_edges services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id code-eval-payload-json-bytes --base-repo <origin-main-worktree> --head-repo "$PWD" --output /tmp/code-eval-json-int-ord-probe.json
```

Acceptance criteria:

- Focused code-eval payload tests pass.
- Changed-scope coverage for touched lines remains at least 95%.
- The registered probe preserves payload byte size and peak memory while showing
  no regression in the JSON payload parse loop.
- PR-scoped performance CI completes the registered probe before merge.
