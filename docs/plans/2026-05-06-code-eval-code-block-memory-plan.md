# Code Eval Code Block Extraction Memory Optimization

## Goal

Reduce transient allocation pressure in `extract_candidate_code(...)` when evaluator responses contain many fenced code blocks. The parser only needs the last complete code block, so it should avoid materializing regex capture groups for every earlier block.

## Touched Files

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`

## Linux-Only Constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Performance Probe

Registered probe: `code-eval-code-block-last-match-streaming`

The probe compares `origin/main` and the PR branch on a synthetic 2,500-code-block response and records:

- `peak_bytes_mean` — lower is better and is the gating optimization metric.
- `elapsed_ms_mean` — informational because this slice prioritizes allocation pressure.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe keeps behavior identical and lowers `peak_bytes_mean` relative to `origin/main`.
- `git diff --check` passes.

## 2026-05-07 Follow-up Slice

This follow-up keeps the same registered probe and replaces the earlier forward
fence scan with a reverse lookup of the last complete fenced block. The parser
falls back over a trailing unmatched fence, preserving the existing incomplete
final-block behavior while avoiding a Python-level scan over every earlier block
on long evaluator responses.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_extract_candidate_code_handles_empty_plaintext_and_code_blocks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_code_block_extract_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_extract_candidate_code_handles_empty_plaintext_and_code_blocks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_code_block_extract_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_code_block_extract_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id code-eval-code-block-last-match-streaming --base-repo /tmp/melix-cron-opt-base-20260506123836 --head-repo "$PWD" --output /tmp/code-eval-code-block-probe.json

git diff --check
```
