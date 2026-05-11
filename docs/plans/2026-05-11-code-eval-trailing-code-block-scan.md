# Code Eval Trailing Code Block Scan

## Scope

This slice targets the Python code-evaluation response parser in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The registered PR-scoped performance probe is
`code-eval-code-block-last-match-streaming`, covering:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Optimization

When a model response contains text after the final fenced code block, the
parser only needs to know whether any trailing non-whitespace exists before it
falls back to the existing fence-counting path. Because the response is already
outer-trimmed, a final-fence end offset before the normalized string length
proves trailing non-whitespace without materializing `normalized[closing + 3:]`
or calling `strip()` on that substring.

The behavior remains unchanged: complete fenced code blocks, unterminated final
blocks, plain text, and trailing commentary after a complete block must resolve
to the same candidate code and parse status as before.

## Verification

Local Linux verification for this Python-only slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_extract_candidate_code_handles_empty_plaintext_and_code_blocks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_code_block_extract_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_code_eval_runner.py::test_extract_candidate_code_handles_empty_plaintext_and_code_blocks services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_code_block_extract_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/code_eval_runner.py services/mlx-worker-python/tests/test_code_eval_runner.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/code_eval_code_block_extract_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/code_eval_code_block_extract_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id code-eval-code-block-last-match-streaming --base-repo <baseline-worktree> --head-repo "$PWD" --output <output-json>
```

CI remains the merge gate for the registered PR-scoped performance report.
