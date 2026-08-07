# Code eval sorted payload literal return

## Scope

This Python-only performance slice stays limited to the sorted code-evaluation
payload fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.
The behavior remains unchanged: successful compact sorted payloads still return
only the normalized code-evaluation result fields and still fall back to the
existing JSON parser for unsupported payload shapes.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
already has focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`

## Optimization

After every required sorted-payload field has been validated, return the final
payload mapping as a single dict literal instead of allocating an empty dict near
the start of the extractor and mutating it as fields are discovered. This avoids
intermediate dict writes on the hot success path while preserving the existing
failure behavior.

## Validation plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_uses_compact_field_offsets services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_skips_reserved_metadata_keys services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_uses_compact_field_offsets services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_skips_reserved_metadata_keys services/mlx-worker-python/tests/test_code_eval_runner.py::test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_payload_json_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id code-eval-payload-json-bytes --base-repo /root/.hermes/profiles/coder/workspace/melix --head-repo "$PWD" --output /tmp/code_eval_payload_literal_return_probe.json
```

GitHub Actions PR-scoped performance remains the final registered probe
validation source before merge.
