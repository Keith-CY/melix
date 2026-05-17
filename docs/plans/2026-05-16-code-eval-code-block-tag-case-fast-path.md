# Code Eval Code Block Tag Case Fast Path

## Scope

This Python-only performance slice narrows the code-evaluation response parser hot path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

The change keeps the existing behavior that treats any ASCII case spelling of the `python` code-fence language tag as a Python block, while avoiding a per-call six-character lowercase allocation when locating the candidate code content start.

## Registered probe

The affected path is already covered by the PR-scoped performance probe `code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`.

That registered probe provides:

- focused behavior tests for code-block extraction,
- changed-scope coverage for the parser, tests, probe registry, and probe script,
- a local/CI probe command that repeatedly extracts the final Python code block from a synthetic multi-block response and reports elapsed time and peak allocation.

## Success metrics

- `elapsed_ms_mean`: lower is better.
- `peak_bytes_mean`: lower is better.
- Behavior parity for lowercase, mixed-case, and non-Python language tags.

## Verification plan

Run the registered focused test command, coverage command, local probe command, and the PR-scoped base-vs-head runner for `code-eval-code-block-last-match-streaming` before opening the PR.
