# Issue 2188 Workspace Ingest Input Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden workspace ingest against non-string structured `text` values by rejecting them with typed, redacted operator failures before they reach cleaning, privacy detection, segmentation, or dataset version artifacts.

**Architecture:** `worker.productization.dataset_preparation` remains the workspace ingest boundary. Structured source readers validate explicit `text` fields at row-construction time, emit a typed unsupported-input failure for non-string values, and skip those rows without stringifying raw objects, arrays, numbers, booleans, or nulls. The existing receipt and metrics pipeline carries the failure without introducing a new protobuf schema or a diagnostics content scan.

**Tech Stack:** Python 3.12 worker productization code, pytest, existing dataset ingest receipt JSON contracts, existing Melix pre-commit and PR-scoped performance gates.

---

## Scope

- Validate structured JSONL, JSON, CSV, and TSV rows that contain an explicit `text` field.
- Accept string `text` values unchanged, including empty strings that are already handled by existing empty-source behavior where applicable.
- Reject non-string explicit `text` values with `DATASET_INGEST_UNSUPPORTED_TEXT_VALUE`.
- Keep raw row values, raw structured payloads, object reprs, and raw sensitive fragments out of operator failures, receipts, CLI JSON, and diagnostics-ready metadata.
- Preserve the existing fallback behavior for structured rows without a `text` field: build text from sorted key/value summaries, because those rows are already non-explicit text records.
- Preserve existing privacy detector `off`, `redact`, and `block` behavior for accepted records.

## Non-Goals

- No model-backed privacy detector.
- No default-on policy change for privacy detection.
- No local proxy or Swift route behavior change.
- No protobuf schema change.
- No diagnostics bundle content scanning.
- No broad rewrite of structured CSV/JSON parsing.

## Files

- Modify `services/mlx-worker-python/worker/productization/dataset_preparation.py`
  - Add a small structured text extraction helper that can return a sanitized failure instead of coercing explicit non-string `text` values.
  - Thread `operator_failures` and row identity into `_structured_records(...)`.
  - Keep `_structured_text(...)` behavior for rows without explicit `text`.
- Modify `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  - Add focused tests for JSONL/JSON/CSV non-string explicit `text` rows.
  - Assert sanitized failure payloads and absence of raw row fragments.
  - Assert valid string rows still ingest, segment, and privacy-detect normally.
- Modify `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`
  - Add `DATASET_INGEST_UNSUPPORTED_TEXT_VALUE` to typed ingest failures.
  - Describe explicit structured `text` field validation.
- Modify this plan as implementation evidence when commands or metrics are finalized.

## Task 1: Add Failing Structured Input Guard Tests

**Files:**
- Test: `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`

- [x] **Step 1: Add JSONL coverage for non-string explicit `text` values**

Add the JSONL guard scenario to the existing
`test_dataset_ingest_privacy_detector_redacts_source_records_before_segments`
nodeid so the registered dataset preparation PR-scoped probes include the new
behavior in their targeted coverage command. The scenario includes one accepted
string row and two rejected rows with dict/list `text` values, and asserts the
receipt omits the raw secret, email, and Python repr fragments.

- [x] **Step 2: Add JSON array coverage for mixed valid and invalid rows**

In the same selected nodeid, add a JSON array source with one valid string
`text` row, one rejected dict `text` row, and one fallback row without explicit
`text`. Assert that the fallback row still segments as derived structured text
and that the invalid dict value is represented only by sanitized failure
metadata.

- [x] **Step 3: Add CSV coverage for a missing `text` cell**

In the same selected nodeid, add a CSV source with a `text` header and a row
that omits the cell. Assert the row is rejected as
`DATASET_INGEST_UNSUPPORTED_TEXT_VALUE` with `value_type: NoneType`, while the
valid CSV row still produces a segment.

- [x] **Step 4: Run RED tests before implementation**

Initial standalone RED tests for the JSONL and JSON scenarios failed with
`status == "ready"` instead of `blocked`, proving `_structured_text(...)` was
still stringifying explicit non-string `text` values. After the implementation
and pre-commit targeted coverage diagnosis, the scenarios were folded into the
existing selected privacy detector nodeid described above.

## Task 2: Implement The Guard

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/dataset_preparation.py`

- [x] **Step 1: Thread operator failures into structured record parsing**

Change the structured-data branch in `_iter_source_records(...)` from:

```python
if source_kind == "structured_data":
    yield from _structured_records(path, text)
else:
```

to:

```python
if source_kind == "structured_data":
    yield from _structured_records(path, text, operator_failures)
else:
```

- [x] **Step 2: Update `_structured_records(...)` to skip invalid explicit text**

Replace the current `_structured_records(...)` implementation with:

```python
def _structured_records(
    path: Path,
    text: str,
    operator_failures: list[dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for index, line in enumerate(text.splitlines(), start=1):
            if not line or line.isspace():
                continue
            payload = json.loads(line)
            row_text = _structured_text_or_failure(path, payload, index, operator_failures)
            if row_text is None:
                continue
            yield _record(
                path=path,
                source_kind="structured_data",
                text=row_text,
                metadata={"row_index": index},
            )
        return
    if suffix == ".json":
        payload = json.loads(text)
        rows = payload if isinstance(payload, list) else [payload]
        for index, row in enumerate(rows, start=1):
            row_text = _structured_text_or_failure(path, row, index, operator_failures)
            if row_text is None:
                continue
            yield _record(
                path=path,
                source_kind="structured_data",
                text=row_text,
                metadata={"row_index": index},
            )
        return
    dialect = "excel-tab" if suffix == ".tsv" else "excel"
    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    for index, row in enumerate(reader, start=1):
        row_text = _structured_text_or_failure(path, row, index, operator_failures)
        if row_text is None:
            continue
        yield _record(
            path=path,
            source_kind="structured_data",
            text=row_text,
            metadata={"row_index": index},
        )
```

- [x] **Step 3: Add a sanitized helper and failure builder**

Add these helpers near `_structured_text(...)`:

```python
def _structured_text_or_failure(
    path: Path,
    payload: Any,
    row_index: int,
    operator_failures: list[dict[str, Any]],
) -> str | None:
    if isinstance(payload, dict) and "text" in payload and not isinstance(payload["text"], str):
        operator_failures.append(
            _unsupported_structured_text_failure(
                path=path,
                row_index=row_index,
                value=payload["text"],
            )
        )
        return None
    return _structured_text(payload)


def _unsupported_structured_text_failure(
    *,
    path: Path,
    row_index: int,
    value: Any,
) -> dict[str, Any]:
    value_type = type(value).__name__
    return {
        "id": _failure_id("unsupported-text-value", f"{path.name}-{row_index}"),
        "code": "DATASET_INGEST_UNSUPPORTED_TEXT_VALUE",
        "path": path.name,
        "detail": (
            "Structured source rows with an explicit text field must provide a string "
            f"value; row {row_index} provided {value_type}."
        ),
        "recovery_hint": (
            "Convert the row text field to a string or remove it so Melix can derive "
            "structured fallback text from non-sensitive fields."
        ),
        "reason": "unsupported_text_value",
        "metadata": {
            "source_uri": path.name,
            "row_index": row_index,
            "value_type": value_type,
        },
    }
```

- [x] **Step 4: Preserve existing fallback behavior**

Keep `_structured_text(...)` as:

```python
def _structured_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if "text" in payload:
            return str(payload["text"])
        return " ".join(f"{key}: {value}" for key, value in sorted(payload.items()))
    return str(payload)
```

This is now only reached for explicit `text` strings, dicts without `text`, and non-dict rows.

- [x] **Step 5: Run the focused tests**

Run the command from Task 1 Step 4 again.

Expected: both tests pass.

## Task 3: Update The Canonical Dataset Plan

**Files:**
- Modify: `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`

- [x] **Step 1: Document explicit structured text validation**

In `U1.2.1 Ingest And Cleaning Controls`, add this paragraph after the supported source kinds table:

```markdown
Structured JSONL, JSON, CSV, and TSV rows with an explicit `text` field must
provide a string value. Non-string explicit `text` values are rejected at the
workspace ingest boundary with a typed operator failure before privacy
detection, PII masking, deduplication, segmentation, or dataset versioning can
stringify raw objects, arrays, numbers, booleans, or nulls into downstream
artifacts.
```

- [x] **Step 2: Add the failure code**

Add this item to the required operator failure code list:

```markdown
- `DATASET_INGEST_UNSUPPORTED_TEXT_VALUE`
```

## Task 4: Verification And Metrics

**Files:**
- Modify: `docs/plans/2026-07-05-issue-2188-workspace-input-guard.md`

- [x] **Step 1: Run focused test coverage for changed Python scope**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
```

Expected: all dataset preparation ingest tests pass.

- [x] **Step 2: Run changed-line coverage for the touched Python scope**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py \
  --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/dataset_preparation.py \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
```

Expected: touched scope reports at least 95 percent measured coverage.

- [x] **Step 3: Run syntax and whitespace checks**

Run:

```bash
python3 -m py_compile \
  services/mlx-worker-python/worker/productization/dataset_preparation.py \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
git diff --check
```

Expected: both commands exit successfully.

- [x] **Step 4: Run the repository pre-commit gate before committing**

Run:

```bash
.githooks/pre-commit
```

Expected:

- `make swift-test` passes.
- `make py-test` passes.
- `make integration-test` passes.
- The scoped performance report has `Status: ok`, `Regressions: 0`, and `Verification failures: 0`; any context regressions are reviewed and documented as out of scope before proceeding.

- [x] **Step 5: Record final evidence in this plan**

Append the exact local verification results and scoped performance report path to a `## Verification Results` section in this document before opening the pull request.

## PR And Issue Evidence

- PR body must use `.github/pull_request_template.md` headings exactly.
- `## Plan or Spec` must point to this plan and the dataset preparation quality/versioning plan.
- `## Commands Run` must include focused tests, changed-scope coverage, `git diff --check`, pre-commit gate, and any reruns.
- `## Coverage and Metrics` must include measured coverage and scoped performance report status.
- After merge, comment on #2188 with the required AI triage prefix and keep the umbrella issue open unless all remaining privacy-policy surfaces are complete.

## Self-Review

- Spec coverage: this plan covers the non-string workspace text input guard, typed failure, redacted receipt behavior, tests, docs, and verification.
- Placeholder scan: no placeholder tasks are present; each implementation step names exact files, commands, and expected outcomes.
- Type consistency: helper signatures use existing `Path`, `Any`, and `operator_failures` conventions from `dataset_preparation.py`.

## Verification Results

- Initial RED run for the standalone JSONL and JSON guard tests: both failed as expected with `status == "ready"` instead of `blocked`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_privacy_detector_redacts_source_records_before_segments`: `1 passed in 0.08s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`: `23 passed in 0.13s`.
- Pre-commit snapshot coverage rerun for `dataset-version-listing-scandir`, `dataset-quality-lengths-chain`, and `dataset-source-records-scandir`: all three registered `coverage_command` values passed with `TOTAL 58 0 100%`; `dataset_preparation.py` changed-line coverage `100.00%`; `test_dataset_preparation_ingest.py` changed-line coverage `100.00%`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`: passed.
- `git diff --check`: passed.
- `git diff --cached --check`: passed.
- First `.githooks/pre-commit` attempt before folding the guard scenarios into a selected PR-scoped nodeid: `make swift-test` passed, `make py-test` passed (`4681 passed, 14 skipped, 2 warnings`), `make integration-test` passed (`123 passed, 1 skipped`), and the scoped performance report failed with `Status: verification_failed`, `Regressions: 0`, `Verification failures: 3` because the probe targeted coverage commands did not execute the newly added standalone guard tests. The tests were then folded into the existing selected privacy detector nodeid and snapshot coverage was rerun as recorded above.
- Final `.githooks/pre-commit` before committing:
  - `make swift-test`: passed, elapsed `154.7s`.
  - `make py-test`: passed, `4678 passed, 14 skipped, 2 warnings in 158.88s`.
  - `make integration-test`: passed, `123 passed, 1 skipped in 418.74s`.
  - Scoped performance report: `/Users/chenyu/Documents/github/melix/.runtime/worktrees/issue-2188-workspace-input-guard-20260705/.runtime/pre-commit-performance/20260705-063848-0df2921f/report/report.md`.
  - Performance status: `Status: ok`, `Changed files: 4`, `Selected probes: 3`, `Direct/gated probes: 3`, `Regressions: 0`, `Context regressions: 0`, `Verification failures: 0`.
  - Probe coverage: `dataset-version-listing-scandir`, `dataset-quality-lengths-chain`, and `dataset-source-records-scandir` all had targeted tests pass and coverage pass at `100.0%`.
