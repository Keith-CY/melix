# Issue 2188 Workspace Path-Confined Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block workspace ingest source discovery when `--input` resolves outside the manifest-declared workspace artifact roots, while keeping operator receipts path-redacted and machine-readable.

**Architecture:** `worker.productization.workspace_manifest` owns manifest root resolution and path policy evidence. `worker.productization.dataset_preparation` remains the ingest boundary: after workspace preflight succeeds and before any source-file traversal, it asks the workspace policy whether the input path is contained by a manifest-declared path-backed artifact root. A denied input returns a blocked dataset ingest receipt with typed operator failures and no `segments.jsonl`.

**Tech Stack:** Python 3.12 worker productization code, pytest, existing workspace preflight and dataset ingest JSON receipt contracts, Melix pre-commit and PR-scoped performance gates.

---

## Scope

- Add a reusable workspace path policy helper for manifest-declared path-backed artifact roots.
- Confine dataset ingest `input_path` to the resolved manifest artifact roots before `_iter_source_records(...)` can traverse or read files.
- Accept both directory and single-file inputs when they resolve within a declared root.
- Deny outside paths, parent traversal escapes, and symlink escapes with `DATASET_INGEST_WORKSPACE_PATH_DENIED`.
- Keep denied receipts free of absolute host paths and raw sensitive file names; use workspace-relative or basename-only evidence where possible.
- Preserve existing workspace preflight checks, privacy detector modes, PII masking, segmentation, and dataset version behavior for accepted inputs.
- Preserve the existing dataset ingest receipt schema version and top-level JSON keys.

## Non-Goals

- No protobuf schema change.
- No local proxy, CORS, network fetch, DNS rebinding, or redirect behavior change.
- No default-on privacy detector change.
- No diagnostics bundle content scanning.
- No broad rewrite of source traversal or structured source parsing.

## Files

- Modify `services/mlx-worker-python/worker/productization/workspace_manifest.py`
  - Add a small path policy helper that loads the manifest, reuses the existing safe-root resolution, and returns sanitized policy evidence for one candidate path.
- Modify `services/mlx-worker-python/worker/productization/dataset_preparation.py`
  - Call the path policy helper after successful workspace preflight and before source discovery.
  - Convert denied policy evidence into a typed operator failure and blocked receipt.
- Modify `services/mlx-worker-python/tests/test_workspace_manifest_contract.py`
  - Add focused tests for allowed paths, outside paths, parent traversal escapes, and symlink escapes without leaking absolute paths.
- Modify `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  - Add focused ingest tests proving denied inputs do not create `segments.jsonl` and allowed inputs still ingest normally.
- Modify `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`
  - Document `DATASET_INGEST_WORKSPACE_PATH_DENIED` and the input confinement rule.
- Update this plan with RED/GREEN and verification evidence before PR handoff.

## Task 1: RED Tests For Workspace Path Policy

- [x] Add `test_workspace_path_policy_allows_manifest_root_children` to `services/mlx-worker-python/tests/test_workspace_manifest_contract.py`.
  - Create a materialized workspace fixture.
  - Ask the helper to evaluate a file under `raw/dialogues.jsonl`.
  - Assert the decision is `allowed`, root id is `raw`, and no absolute path appears in serialized evidence.
- [x] Add `test_workspace_path_policy_denies_paths_outside_manifest_roots`.
  - Create `tmp_path / "outside" / "secret.txt"` outside the workspace.
  - Assert the decision is `denied`, reason is `outside_workspace_roots`, and serialized evidence does not contain the absolute outside directory.
- [x] Add `test_workspace_path_policy_denies_parent_traversal_escape`.
  - Pass a path shaped like `workspace/raw/../../outside/secret.txt`.
  - Assert the helper resolves the candidate before containment checks and denies it.
- [x] Add `test_workspace_path_policy_denies_symlink_escape`.
  - Create a symlink under a manifest root that points to a file outside the workspace.
  - Assert the helper denies the resolved symlink target and does not leak the target absolute path.
- [x] Run the new tests before implementation and confirm they fail because the helper does not exist yet:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_allows_manifest_root_children \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_paths_outside_manifest_roots \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_parent_traversal_escape \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_symlink_escape
```

## Task 2: Implement The Path Policy Helper

- [x] Add `workspace_path_policy_receipt(...)` to `services/mlx-worker-python/worker/productization/workspace_manifest.py`.
  - Signature:

```python
def workspace_path_policy_receipt(
    manifest_path: Path | str,
    candidate_path: Path | str,
) -> dict[str, Any]:
```

  - Return keys: `schema_version`, `decision`, `reason`, `candidate_path`, `root_id`, `root_path`, and `checks`.
  - Use schema version `melix.workspace_path_policy_receipt.v1`.
  - Use existing manifest validation and `_resolved_safe_roots(...)` so unsafe manifest roots are never trusted.
  - Use resolved paths for containment and sanitized display values for receipts.
- [x] Add internal helpers for containment and display paths.
  - Use `Path.resolve(strict=False)` for candidate and root paths.
  - Prefer `candidate.relative_to(root)` for allowed candidate display.
  - For denied candidates, use only `candidate.name` or a workspace-relative value if it can be expressed without escaping.
  - Do not include raw absolute host paths in the receipt.
- [x] Re-run Task 1 tests and confirm they pass.

## Task 3: RED Tests For Dataset Ingest Confinement

- [x] Add `test_dataset_ingest_blocks_input_outside_workspace_roots_before_discovery` to `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`.
  - Create a ready workspace manifest.
  - Create a source directory outside the workspace containing `secret.txt`.
  - Run `prepare_dataset_ingest(...)`.
  - Assert `status == "blocked"`, `operator_failures[0].code == "DATASET_INGEST_WORKSPACE_PATH_DENIED"`, `source_inventory == []`, no `segments.jsonl`, and serialized receipt omits the outside directory absolute path.
- [x] Add `test_dataset_ingest_allows_input_under_manifest_root`.
  - Use the ready workspace's `raw` root as the input path.
  - Assert ingest remains `ready` and writes `segments.jsonl`.
- [x] Add `test_dataset_ingest_blocks_symlink_escape_under_manifest_root`.
  - Put a symlink under the raw root pointing to an outside source file.
  - Run ingest against the symlink path.
  - Assert the same blocked failure and no segment output.
- [x] Run the new tests before dataset implementation and confirm the outside/symlink denial tests fail because ingest still reads the candidate path directly:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_blocks_input_outside_workspace_roots_before_discovery \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_allows_input_under_manifest_root \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_blocks_symlink_escape_under_manifest_root
```

## Task 4: Wire Dataset Ingest To The Policy

- [x] Import `workspace_path_policy_receipt(...)` in `dataset_preparation.py`.
- [x] After workspace preflight returns `ready`, evaluate `input_path`.
- [x] If the policy decision is `denied`, return a blocked ingest receipt using the existing blocked-receipt shape:
  - `source_inventory: []`
  - zero source, segment, and privacy counts
  - `workspace_preflight_receipt` attached as today
  - `workspace_path_policy_receipts` containing the path policy receipt
  - `operator_failures` containing `DATASET_INGEST_WORKSPACE_PATH_DENIED`
  - no `segments.jsonl`
- [x] If the policy decision is `allowed`, continue through the existing source discovery, privacy detector, cleaning, and segmentation flow unchanged.
- [x] Re-run Task 3 tests and confirm they pass.

## Task 5: Docs, Coverage, And Verification

- [x] Update `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md` with the input confinement rule and failure code.
- [x] Run adjacent focused suites:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
```

- [x] Run syntax and diff checks:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile \
  services/mlx-worker-python/worker/productization/workspace_manifest.py \
  services/mlx-worker-python/worker/productization/dataset_preparation.py \
  services/mlx-worker-python/tests/test_workspace_manifest_contract.py \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
git diff --check
git diff --cached --check
```

- [x] Run changed-scope coverage and the full local pre-commit gate before commit/PR:

```bash
.githooks/pre-commit
```

- [x] Record focused test output, coverage percentage, performance report path, and any regression analysis in this plan before opening the PR.

## Metrics

- `workspace_path_policy_receipt` should add no source-file traversal; it resolves one candidate path and compares it against declared roots.
- The direct success metric is zero source files and zero segments for denied inputs.
- Changed-scope coverage must be at least 95 percent before commit.
- The pre-commit performance report must show no in-scope regression; any regression requires root-cause analysis before PR handoff.

## Verification Evidence

RED checks:

- `test_workspace_path_policy_allows_manifest_root_children`,
  `test_workspace_path_policy_denies_paths_outside_manifest_roots`,
  `test_workspace_path_policy_denies_parent_traversal_escape`, and
  `test_workspace_path_policy_denies_symlink_escape` initially failed with
  `AttributeError: module 'worker.productization.workspace_manifest' has no
  attribute 'workspace_path_policy_receipt'`.
- `test_dataset_ingest_blocks_input_outside_workspace_roots_before_discovery`,
  `test_dataset_ingest_allows_input_under_manifest_root`, and
  `test_dataset_ingest_blocks_symlink_escape_under_manifest_root` initially
  failed because ingest returned `ready` for outside/symlink inputs and did not
  emit `workspace_path_policy_receipts`.

Focused GREEN checks:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_allows_manifest_root_children services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_paths_outside_manifest_roots services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_parent_traversal_escape services/mlx-worker-python/tests/test_workspace_manifest_contract.py::test_workspace_path_policy_denies_symlink_escape` -> `4 passed in 0.07s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_blocks_input_outside_workspace_roots_before_discovery services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_allows_input_under_manifest_root services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_blocks_symlink_escape_under_manifest_root` -> `3 passed in 0.05s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_workspace_manifest_contract.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py` -> `72 passed in 0.39s`.
- After adding invalid-manifest and helper-fallback coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_workspace_manifest_contract.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py` -> `74 passed in 0.57s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile services/mlx-worker-python/worker/productization/workspace_manifest.py services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_workspace_manifest_contract.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py services/mlx-worker-python/tests/dataset_ingest_limit_contract.py` -> pass.
- `git diff --check` -> pass.

Coverage:

- `python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/workspace_manifest.py services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_workspace_manifest_contract.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py services/mlx-worker-python/tests/dataset_ingest_limit_contract.py` -> aggregate `TOTAL 264 5 98%`.
- Production changed-line coverage: `workspace_manifest.py` -> `100.00%`; `dataset_preparation.py` -> `100.00%`.

Final pre-commit gate:

- `.githooks/pre-commit` -> `__PRECOMMIT_EXIT__=0`.
- `make swift-test` completed with `rc=0` in `141.3s`.
- `make py-test` -> `4703 passed, 14 skipped, 2 warnings in 176.37s`.
- `make integration-test` -> `123 passed, 1 skipped in 426.36s`.
- Pre-commit performance report:
  `.runtime/pre-commit-performance/20260705-184030-7862756b/report/report.md`.
  Summary: `Status: ok`, `Changed files: 10`, `Selected probes: 141`,
  `Direct/gated probes: 4`, `Regressions: 0`, `Context regressions: 9`,
  `Verification failures: 0`.
- Direct changed-scope performance probes for this slice:
  `dataset-version-listing-scandir` coverage `98.0%`,
  `dataset-quality-lengths-chain` coverage `98.0%`, and
  `dataset-source-records-scandir` coverage `97.0%`; all three reported
  `Status: ok`, targeted tests passed, and no direct regression.
- The nine reported context regressions were outside the direct/gated scope for
  this workspace-ingest slice, and the generated report accepted them with
  overall `Status: ok` and `Regressions: 0`.
