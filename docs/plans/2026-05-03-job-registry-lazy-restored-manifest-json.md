# Job Registry Lazy Restored Manifest JSON Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Avoid redundant JSON re-serialization when restoring completed model-ops jobs from manifest files.

**Architecture:** Keep restored `ModelOpsJob` instances manifest-cache-first: preserve the parsed `manifest` dict and `manifest_cached=True`, but stop eagerly rebuilding `manifest_json` during `_restore_manifest_jobs`. Update manifest readers/snapshot builders so cached manifests remain visible even when `manifest_json` is empty. Reuse the existing `job-registry-restore-sort-elision` PR-scoped probe rather than introducing a new registry entry.

**Tech Stack:** Python 3.11, pytest, coverage.py, Melix PR-scoped performance probe `scripts/job_registry_restore_probe.py`.

---

### Task 1: Add a written plan for the restore optimization slice

**Objective:** Record the governing plan/spec and verification contract before code changes.

**Files:**
- Create: `docs/plans/2026-05-03-job-registry-lazy-restored-manifest-json.md`

**Verification:**
- Plan exists and names the touched files, probe, and success metric.

### Task 2: Make restored jobs lazy about `manifest_json`

**Objective:** Remove eager `json.dumps(payload)` work in `_restore_manifest_jobs` while preserving snapshot and derived-model behavior.

**Files:**
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`

**Implementation notes:**
- In `_restore_manifest_jobs`, keep `manifest=payload` and `manifest_cached=True`, but do not eagerly serialize `manifest_json`.
- Update `_job_manifest(...)` to prefer `manifest_cached` before checking `manifest_json`, so restored jobs still expose their cached manifest.
- Update `_snapshot_job(...)` similarly so snapshots include restored manifests even when `manifest_json` is empty.
- Do not change behavior for uncached jobs or `registry_snapshot` jobs.

**Success metric:**
- Existing restore probe reports lower `restore_elapsed_ms_mean` than the current baseline.

### Task 3: Add focused regression tests for lazy restored manifests

**Objective:** Prove restored jobs still expose manifests without requiring serialized `manifest_json`.

**Files:**
- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

**Test coverage goals:**
- Restored jobs preserve manifest ordering and keep `manifest_json == ""` while `manifest_cached is True`.
- `_job_manifest(...)` returns the cached manifest even when `manifest_json` is empty.
- `_snapshot_job(...)` emits the cached manifest for restored jobs with empty `manifest_json`.
- Existing restore-focused tests still pass.

### Task 4: Verify locally on Linux

**Objective:** Satisfy the Python-slice verification contract before commit.

**Files:**
- Verify only

**Commands:**
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_job_registry_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_job_registry_restore_probe_script_emits_metrics`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report -m services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_model_ops_job_registry.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/job_registry_restore_probe.py`
- `git diff --check`

**Acceptance:**
- Focused pytest passes.
- Changed-scope coverage is >=95% for touched executable lines.
- Probe prints concrete elapsed metrics and improves over baseline.
- `git diff --check` is clean.

### Task 5: Commit, push, PR, and CI wait

**Objective:** Publish the slice with evidence-complete PR metadata and wait for hosted scoped-performance validation.

**Files:**
- Modify: `/tmp/pr-body-*.md` (temporary only, outside repo)

**Requirements:**
- Commit message: `perf: lazy-serialize restored model-ops manifests`
- PR body must keep headings exactly:
  - `## Summary`
  - `## Plan or Spec`
  - `## Commands Run`
  - `## Coverage and Metrics`
  - `## Known Gaps`
  - `## Evidence Checklist`
- Wait for the relevant `pr-scoped-performance` run to complete before enabling auto-merge.
- Probe to cite in the PR: `job-registry-restore-sort-elision`.
