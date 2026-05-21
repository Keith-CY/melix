# Agentic Multimodal Sample Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the canonical sample-field contract for the repository-owned agentic multimodal evaluation fixtures in issue #717.

**Architecture:** The field contract is documented in `docs/benchmark-evaluation-contract.md` and encoded in a small Python validator under `worker.productization`. Existing fixture tests call the validator so the three checked-in fixture packages remain the executable examples of the contract without changing runner or scorer behavior.

**Tech Stack:** Python dataclasses/functions, JSON fixture samples, pytest, and the existing deterministic agentic tool runtime.

---

## Scope

This plan covers issue #717, the second executable unit under milestone #715 for direction #714.

In scope:

- Define the required sample fields for agentic multimodal evaluation samples:
  - `question`
  - `media_refs`
  - `expected_answer`
  - `evidence_ids`
  - `allowed_tools`
- Define cross-field constraints for those fields:
  - `question` must match `input.text`.
  - `expected_answer` must match `target`.
  - `media_refs` entries must have stable `id`, `kind`, and relative `uri` values.
  - `evidence_ids` must be non-empty strings and must map to package-local media ids or deterministic tool fixture evidence ids.
  - `allowed_tools` must be non-empty, subset manifest `allowed_tools`, and include every tool used by `tool_calls`.
- Keep the existing deterministic replay and local asset checks intact.
- Update the canonical benchmark/evaluation contract with the sample-field contract.

Out of scope:

- Changing evaluation runner dispatch.
- Changing final-result scoring.
- Adding trajectory report artifacts.
- Adding judge-backed metrics.

## Files

- Create: `services/mlx-worker-python/worker/productization/agentic_multimodal_evaluation_contract.py`
- Create: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py`
- Modify: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py`
- Modify: `docs/benchmark-evaluation-contract.md`

## Tasks

### Task 1: Add the failing sample-field validator tests

**Files:**

- Create: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py`

- [ ] **Step 1: Write the failing tests**

Create tests that import:

```python
from worker.productization.agentic_multimodal_evaluation_contract import (
    AGENTIC_MULTIMODAL_SAMPLE_FIELD_SCHEMA_VERSION,
    validate_agentic_multimodal_sample_fields,
)
```

Test a valid sample and at least these invalid cases:

- missing `question`
- `question` not matching `input.text`
- `expected_answer` not matching `target`
- invalid `media_refs`
- `evidence_ids` missing evidence from the fixture context
- `allowed_tools` outside the manifest allow-list
- `tool_calls` using a tool not listed in `allowed_tools`

- [ ] **Step 2: Run the tests and verify red**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py
```

Expected result: fail because the validator module does not exist.

### Task 2: Implement the validator and wire existing fixture tests

**Files:**

- Create: `services/mlx-worker-python/worker/productization/agentic_multimodal_evaluation_contract.py`
- Modify: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py`

- [ ] **Step 1: Implement the minimal validator**

Add:

```python
AGENTIC_MULTIMODAL_SAMPLE_FIELD_SCHEMA_VERSION = "melix.agentic_multimodal_sample_fields.v1"

def validate_agentic_multimodal_sample_fields(
    sample: dict[str, object],
    *,
    manifest_allowed_tools: object,
) -> list[str]:
    ...
```

The function returns a list of human-readable contract errors. It does not raise for ordinary field contract failures.

- [ ] **Step 2: Verify the validator tests pass**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py
```

Expected result: all tests pass.

- [ ] **Step 3: Wire the fixture test through the validator**

Update `test_agentic_multimodal_fixture_samples_reference_local_assets_and_tools` so each sample calls:

```python
errors = validate_agentic_multimodal_sample_fields(
    sample,
    manifest_allowed_tools=manifest["allowed_tools"],
)
assert errors == []
```

- [ ] **Step 4: Verify fixture tests pass**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
```

Expected result: all tests pass.

### Task 3: Update the canonical contract and evidence

**Files:**

- Modify: `docs/benchmark-evaluation-contract.md`

- [ ] **Step 1: Document the sample-field contract**

Add a subsection under `Evaluation Dataset Contract` or near the agentic multimodal fixture text that defines the required fields, their types, and their cross-field constraints.

- [ ] **Step 2: Run focused tests with coverage and metrics**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json -o .runtime/coverage-agentic-multimodal-sample-fields.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/python_changed_line_coverage.py --coverage-json .runtime/coverage-agentic-multimodal-sample-fields.json --diff-from origin/main services/mlx-worker-python/worker/productization/agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
```

Expected result: tests pass and changed-line coverage is at least 95%.

- [ ] **Step 3: Run PR scoped performance scope**

Run:

```bash
git diff --name-only origin/main...HEAD | python3 -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()], indent=2))' > .runtime/pr-scope-sample-fields/changed-files.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/pr_scoped_performance_scope.py --registry infra/perf/pr_scoped_probes.json --changed-files-json .runtime/pr-scope-sample-fields/changed-files.json --output .runtime/pr-scope-sample-fields/scope.json
```

Expected result: record selected probes. If selected_count is 0, runtime performance metrics are N/A because this change is a static contract validator and docs update.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/benchmark-evaluation-contract.md docs/plans/2026-05-21-agentic-multimodal-sample-fields.md services/mlx-worker-python/worker/productization/agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_contract.py services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
git commit -m "test: define agentic multimodal sample fields"
```

Expected result: one focused commit for issue #717.
