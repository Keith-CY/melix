# Code Evaluation ASCII Boundary Set Performance Slice

## Scope

This slice optimizes the Python code-evaluation fallback test counter for large
ASCII test payloads. Behavior stays unchanged: small payloads still use
`splitlines()`, large non-ASCII payloads keep Python whitespace semantics, and
large ASCII payloads still treat the same Python split-line boundaries as line
breaks.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`code-eval-test-count-nonblank-streaming` in
`infra/perf/pr_scoped_probes.json`. The registered probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries for
`services/mlx-worker-python/worker/engine/code_eval_runner.py` and
`scripts/code_eval_test_count_probe.py`.

## Verification plan

- Focused pytest for code-evaluation fallback counting and the registered probe
  smoke tests.
- Changed-scope coverage command from the registered probe.
- Local Linux registered probe execution before push.
- GitHub Actions PR-scoped performance workflow after PR creation.

## Expected outcome

Reduce large ASCII nonblank-line scan overhead by using prebuilt frozensets for
ASCII split-boundary and non-line-whitespace membership checks. This keeps the
counter streaming and allocation-light while avoiding repeated short-string
membership scans in the hot loop.
