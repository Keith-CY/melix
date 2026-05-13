# Job Registry Restore Operation Match Fast Path

## Scope

- Affected path: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Supporting tests: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- Registered PR-scoped probe: `job-registry-restore-sort-elision` in `infra/perf/pr_scoped_probes.json`
- Probe support path: `scripts/job_registry_restore_probe.py`
- Constraint: Python-only slice; locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered probe.

## Goal

Reduce per-manifest cold-restore overhead in `ModelOpsJobRegistry._restore_manifest_jobs(...)` without changing accepted manifest payload semantics.

## Why this slice

The restore probe feeds thousands of manifests whose `operation` field already matches the target operation as an exact string. The previous hot loop normalized every manifest via `str(...).strip()` before comparing, even for the exact-string common case. That kept compatibility with whitespace-padded or non-string operation payloads, but paid conversion/strip overhead on every normal manifest.

## Implementation

1. Add `_manifest_operation_matches(...)` with an exact-string comparison first.
2. Fall back to the prior `str(raw).strip()` comparison only when the exact comparison does not match.
3. Use the helper inside `_restore_manifest_jobs(...)` so normal manifests skip redundant conversion while compatibility payloads remain accepted.
4. Add a focused regression test covering exact-string, whitespace-normalized, non-string `__str__`, and mismatch cases.

## Verification Plan

1. Focused job-registry and PR-scoped probe tests from the registered probe command.
2. Changed-scope coverage through the registered `coverage_command`.
3. Local registered probe comparison with `scripts/pr_scoped_performance_run.py --probe-id job-registry-restore-sort-elision` against `origin/main`.
4. `git diff --check` before commit.

## Success Criteria

- Focused tests pass.
- Changed executable scope coverage is at least 95%.
- Registered probe shows a clear non-regression or improvement in `restore_elapsed_ms_mean` / `per_manifest_ms_mean`.
- No change to restored job ordering, duplicate handling, or compatibility with normalized operation payloads.
