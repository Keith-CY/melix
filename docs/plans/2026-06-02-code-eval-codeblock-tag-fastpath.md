# Code Evaluation Code Block Tag Fast Path

## Scope

This Python-only performance slice narrows the code-evaluation response parser in
`worker.engine.code_eval_runner`.

The parser already scans from the final fenced code block and strips a leading
`python` language tag. Lowercase `python` is the common case and is handled by
`str.startswith()`, but mixed-case tags currently allocate a six-character slice
and lowercase copy before comparison.

## Optimization Hypothesis

Replace the mixed-case fallback allocation in `_code_block_content_start()` with
a small ASCII-only character comparison helper for the literal `python` tag.
This preserves support for `python`, `PYTHON`, and mixed-case `PyThOn` tags while
avoiding `.lower()` allocation on mixed-case code fences.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe:

- `code-eval-code-block-last-match-streaming`

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries in `infra/perf/pr_scoped_probes.json`. This slice also
points `probe_command` at the maintained probe script instead of the older inline
lowercase-only fallback. The script builds 2,500 fenced code blocks with
alternating lowercase and mixed-case `python` tags, then validates the final
block extraction and records elapsed time and peak bytes.

## Verification Plan

Run focused Linux verification from the PR worktree:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_code_eval_runner.py::test_extract_candidate_code_handles_empty_plaintext_and_code_blocks \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_code_eval_stdio_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_code_eval_code_block_extract_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/engine/code_eval_runner.py \
  services/mlx-worker-python/tests/test_code_eval_runner.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/code_eval_code_block_extract_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id code-eval-code-block-last-match-streaming \
  --base-repo /root/.hermes/profiles/coder/workspace/melix \
  --head-repo "$PWD" \
  --output /tmp/code_eval_codeblock_tag_fastpath_probe.json
```

PR-scoped performance CI remains the final registered probe validation source
before merge.
