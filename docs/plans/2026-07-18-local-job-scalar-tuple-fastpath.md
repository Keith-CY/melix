# Local Job Follow-up Scalar Tuple Fast Path

## Context

The registered PR-scoped probe `local-job-followup-scan-scandir` covers
`worker.runtime.local_job_continuation` follow-up scanning, projection, and the
JSON-like copy helpers used by local-job follow-up payloads.

The `_copy_json_like_value()` exact-type tuple path already has dedicated two-
and three-item tuple branches. Those branches still recursively dispatched for
each scalar item, even though exact JSON scalar leaves are immutable and can be
copied directly without changing behavior.

## Scope

- Limit code changes to exact `tuple` handling in
  `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.
- Add a regression test proving exact scalar three-tuples avoid recursive helper
  dispatch.
- Preserve recursive copying for nested dictionaries/lists/tuples and subclass
  fallback behavior.

## Measurement

Registered probe: `local-job-followup-scan-scandir`

Required local Linux commands:

- Focused test command from the registered probe, including the new tuple scalar
  regression test.
- Changed-scope coverage command from the registered probe.
- Registered probe command from `infra/perf/pr_scoped_probes.json`.

Success is accepted only if behavior tests pass, changed-scope coverage remains
at or above 95%, and the local registered probe shows a directionally improved
or non-regressive scalar-copy delta/speedup path. The scalar-copy absolute head
elapsed metric remains informational because the stable acceptance signal is the
same-run optimized-vs-baseline delta, not cross-run absolute noise. Existing
claim-copy and candidate-receipt comparison metrics also remain informational for
this tuple-scalar slice because they are retained as historical context but are
not the changed helper path. GitHub Actions PR-scoped performance remains the
merge gate after push.

## Linux Boundary

This is a Python worker path and is locally verifiable on Linux. CI remains the
source of truth for the registered PR-scoped performance report after the PR is
opened.
