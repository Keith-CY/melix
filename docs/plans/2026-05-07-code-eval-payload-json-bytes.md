# Code Eval Payload JSON Byte Loading Optimization

## Goal

Reduce overhead in the code-evaluation payload hot path by loading sandbox payload JSON directly from bytes and binding the JSON decoder used by repeated payload loads.

## Linux-only constraint

This slice is Python-only and verifiable on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_payload_json_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe definition

Register `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`.

The probe repeatedly loads a representative UTF-8 JSON payload through `_load_payload_file(...)`, measures elapsed time and traced peak allocation, and emits:

- `elapsed_ms_mean` (informational)
- `peak_bytes_mean` (lower is better, 5% warning threshold)
- `payload_bytes` (structural)
- `sample_count` (structural)
- `iteration_count` (structural)

## Success metrics

- Preserve valid payload, invalid JSON, non-mapping, and missing-file behavior.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- The local base-vs-head PR-scoped probe should show no regression and should demonstrate reduced or flat peak allocation compared with `origin/main`.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_payload_json_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_rejects_invalid_and_non_mapping_json \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_load_payload_file_reads_payload_bytes_without_text_decode \
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
BASE=/tmp/melix-code-eval-payload-base
[ -d "$BASE/.git" ] || git worktree add --detach "$BASE" origin/main
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id code-eval-payload-json-bytes \
  --base-repo "$BASE" \
  --head-repo "$PWD" \
  --output /tmp/code-eval-payload-json-probe.json

git diff --check
```
