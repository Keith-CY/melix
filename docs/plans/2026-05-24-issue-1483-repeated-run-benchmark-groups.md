# Repeated-Run Benchmark Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeated-run benchmark group artifacts and report confidence intervals without changing the benchmark runner or CLI repetition loop.

**Architecture:** Keep existing per-repeat benchmark rows and `repeat_index` compatibility as the source data. Derive group rows from persisted context and batch rows, write them as a sidecar `bench-repeat-groups.jsonl`, include them in export bundles and CSV helpers, and let the comparison report classify overlapping confidence intervals as informational instead of overclaiming regressions or improvements.

**Tech Stack:** Python dataclasses and JSONL/CSV artifact writers under `services/mlx-worker-python/worker/productization`, pytest tests, and Markdown repository documentation.

---

### Task 1: Repeat Group Schema And Builder

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/benchmark_schemas.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_schemas.py`

- [x] **Step 1: Write the failing schema test**

Add a test that imports `build_serving_benchmark_repeat_group_row` and asserts it emits `schema_version: melix.serving_benchmark_repeat_group.v1`, stable identity fields, `group_id`, `repetition_index`, `sample_count`, `seed_strategy`, `methodology_version`, and mean/stdev/CI95 metric fields.

- [x] **Step 2: Run the schema test to verify it fails**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_schemas.py::test_build_serving_benchmark_repeat_group_row_includes_ci_fields
```

Expected: FAIL because the builder does not exist yet.

- [x] **Step 3: Implement the schema dataclass and builder**

Add a frozen dataclass for one repeat group row plus a builder that preserves caller-supplied values and defaults `methodology_version` to the current repeated-run aggregation method.

- [x] **Step 4: Run the schema test to verify it passes**

Run the same single-test command and expect PASS.

### Task 2: Store-Derived Group Artifact

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/benchmark_store.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_store.py`

- [x] **Step 1: Write the failing store test**

Persist a benchmark with multiple repeated context rows for the same suite/context/batch identity and assert `bench-repeat-groups.jsonl` exists, is returned in `persisted["repeat_groups_jsonl"]`, preserves `repeat_index` values as `repetition_index`, and computes mean, sample stdev, and 95 percent confidence interval fields.

- [x] **Step 2: Run the store test to verify it fails**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_store.py::test_persist_serving_benchmark_writes_repeat_group_artifact_from_existing_rows
```

Expected: FAIL because the sidecar artifact is not written yet.

- [x] **Step 3: Implement group derivation and persistence**

Group context and batch rows by benchmark identity excluding `repeat_index`; compute numeric aggregates for throughput, TTFT, request latency, peak memory, and optional energy fields when present. Write one JSONL row per source kind and group identity.

- [x] **Step 4: Run the store test to verify it passes**

Run the same single-test command and expect PASS.

### Task 3: Export Bundle And CSV Surface

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_export.py`

- [x] **Step 1: Write the failing export test**

Create a benchmark fixture containing `bench-repeat-groups.jsonl`, collect it with `collect_benchmark_artifacts` and `build_export_bundle`, and assert `benchmark_repeat_groups` is present while existing summary/context/batch/request outputs remain unchanged. Also assert `build_benchmark_repeat_groups_csv` exports group and CI fields.

- [x] **Step 2: Run the export test to verify it fails**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_export.py::test_export_bundle_collects_repeat_group_rows_and_csv
```

Expected: FAIL because the collector and CSV helper do not expose repeat groups.

- [x] **Step 3: Implement collection and CSV helper**

Collect `bench-repeat-groups.jsonl` from root and nested run directories, include `benchmark_repeat_groups` in bundles, and add canonical repeat-group CSV columns without changing existing CSV column lists.

- [x] **Step 4: Run the export test to verify it passes**

Run the same single-test command and expect PASS.

### Task 4: Report CI Classification

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- Test: `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

- [x] **Step 1: Write the failing report test**

Build baseline and candidate bundles with `benchmark_repeat_groups` for the same group. Assert the report metric row includes CI metadata and that overlapping CI deltas are `informational` with an inconclusive note, even when the raw delta exceeds the warning threshold.

- [x] **Step 2: Run the report test to verify it fails**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_evaluation_report.py::test_report_marks_overlapping_repeat_group_ci_as_informational
```

Expected: FAIL because repeat group metrics are not collected or classified.

- [x] **Step 3: Implement repeat group metric collection and CI-aware rows**

Collect repeat group mean metrics as structured metric values with CI bounds. Update metric row construction so overlapping baseline/candidate intervals mark the row informational and carry the comparison note; non-overlapping CI rows keep the normal direction and threshold logic.

- [x] **Step 4: Run the report test to verify it passes**

Run the same single-test command and expect PASS.

### Task 5: Contract Documentation And Verification

**Files:**
- Modify: `docs/benchmark-evaluation-contract.md`
- Modify: `docs/plans/2026-05-24-issue-1483-repeated-run-benchmark-groups.md`

- [x] **Step 1: Update the contract**

Document repeat group artifact identity, required fields, confidence interval semantics, and report interpretation rules. State that single-run groups must remain compatible but are informational because variance cannot be estimated.

- [x] **Step 2: Run focused and scoped verification**

Run the required four focused test files, changed-scope coverage if feasible, an existing report probe if feasible, and `git diff --check`.

- [x] **Step 3: Commit**

Commit the narrow implementation with one focused message after verification evidence is recorded.

### Review Follow-Up

- [x] Aggregate repeat groups by distinct `repeat_index` samples rather than raw case rows.
- [x] Omit optional energy fields when no source energy samples exist instead of synthesizing `0.0`.
- [x] Preserve CI95 bounds, sample counts, and inconclusive notes in Markdown, terminal, CSV, and pre-commit report outputs.
- [x] Include repeat-group identity fields in report metric labels so rows from distinct models, sources, groups, or methodology versions do not overwrite each other.

### Repeat Count Contract Follow-Up

- [x] Bound public repeated-run inputs to `1` through `20` repetitions at the CLI, batch config, environment, and control-plane request surfaces.
- [x] Preserve compatibility normalization for omitted or zero-valued programmatic request builders while rejecting over-limit direct control-plane commands.
- [x] Update the benchmark/evaluation contract with the repeat count range and boundary behavior.
