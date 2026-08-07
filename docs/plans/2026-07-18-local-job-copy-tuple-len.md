# Local Job Follow-up Tuple Copy Length Cache

## Context

The registered PR-scoped probe `local-job-followup-scan-scandir` covers
`worker.runtime.local_job_continuation` follow-up scanning, claim projection, and
JSON-like payload copy helpers used by local-job follow-up receipts.

The `_copy_json_like_value()` tuple fast path handles common two- and three-item
tuples separately, but it previously called `len(value)` once per length branch.
This slice keeps copy semantics unchanged while caching the tuple length once for
that exact-type tuple path.

## Scope

- Limit code changes to `_copy_json_like_value()` tuple handling in
  `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.
- Preserve exact behavior for JSON scalar reuse, dict/list copying, tuple copying,
  and container subclass fallback handling.
- Use the existing focused tests that cover tuple payload copying and container
  subclass preservation.

## Measurement

Registered probe: `local-job-followup-scan-scandir`

Required local Linux commands:

- Focused registry test command for `local-job-followup-scan-scandir`.
- Changed-scope coverage command for the same registry entry.
- Registered probe command from `infra/perf/pr_scoped_probes.json`.

Success is accepted only if behavior tests pass, changed-scope coverage remains
at or above 95%, and the local registered probe remains directionally
non-regressive for the local-job follow-up copy and scan metrics. GitHub Actions
PR-scoped performance remains the merge gate after push.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. CI remains
the source of truth for the registered PR-scoped performance report after the PR
is opened.
