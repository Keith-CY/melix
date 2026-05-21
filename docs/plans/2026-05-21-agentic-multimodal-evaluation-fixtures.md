# Agentic Multimodal Evaluation Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first repository-owned agentic multimodal evaluation fixture packages for issue #716.

**Architecture:** The new fixtures are checked-in `final_result` evaluation packages under `services/mlx-worker-python/fixtures/evaluation/`. Each package carries package-local media or document assets plus deterministic `tool_calls` and `tool_fixture_context` data that can be replayed by the existing agentic tool runtime without changing evaluation execution behavior. The broader field contract remains intentionally narrow here because issue #717 owns formal sample-field taxonomy.

**Tech Stack:** JSON evaluation manifests, JSONL sample rows, repository-local media/document assets, Python pytest, and `worker.runtime.agentic_tools.execute_agentic_tool_calls`.

---

## Scope

This plan covers issue #716, the first executable unit under milestone #715 for direction #714.

In scope:

- Add one small image-grounded multi-hop QA fixture package.
- Add one small visual retrieval QA fixture package.
- Add one small document lookup QA fixture package.
- Add a static pytest contract that proves all package manifests, sample rows, media/document references, allowed tools, evidence ids, and deterministic tool replay data are coherent.
- Update the benchmark/evaluation contract to name the new development fixture packages and describe their non-runtime purpose.

Out of scope:

- Changing the evaluation runner or scorer.
- Defining the full sample field taxonomy for issue #717.
- Adding judge-based scoring or persisted evaluation artifacts for later milestones #718 and #721.
- Adding these development fixtures to the macOS app bundle, whose current bundled evaluation fixture list is release-package scoped.

## Files

- Create: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-multihop-qa.dev.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-multihop-qa.dev.v1/samples.jsonl`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-multihop-qa.dev.v1/media/gallery-map.ppm`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-visual-retrieval-qa.dev.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-visual-retrieval-qa.dev.v1/samples.jsonl`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-visual-retrieval-qa.dev.v1/media/query-card.ppm`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-visual-retrieval-qa.dev.v1/media/catalog-match.ppm`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-document-lookup-qa.dev.v1/manifest.json`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-document-lookup-qa.dev.v1/samples.jsonl`
- Create: `services/mlx-worker-python/fixtures/evaluation/agentic-document-lookup-qa.dev.v1/documents/runtime-brief.txt`
- Modify: `docs/benchmark-evaluation-contract.md`

## Fixture Package Contract

Each new manifest must use:

- `schema_version: melix.evaluation_dataset_package.v2`
- `profile_type: final_result`
- `result_kind: text`
- `extraction_mode: heuristic_final`
- `scoring_mode: normalized_exact_match`
- `threshold: 1.0`
- `agentic_suite_family: melix.agentic_multimodal_evaluation.dev.v1`
- `toolset_version: melix.agentic_tools.builtin.v1`
- `trajectory_schema_version: melix.agentic_tool_trace.v1`

Each new package must contain exactly one sample for this first dev slice. Each sample must include:

- `id`
- `system`
- `input`
- `target`
- `question`
- `expected_answer`
- `media_refs`
- `evidence_ids`
- `allowed_tools`
- `tool_calls`
- `tool_fixture_context`

The deterministic replay smoke test must call:

```python
execute_agentic_tool_calls(
    sample["tool_calls"],
    fixture_context=sample["tool_fixture_context"],
)
```

and assert:

- all calls complete
- all requested tools are listed in `allowed_tools`
- the runtime reports `melix.agentic_tools.builtin.v1`
- every `expected_answer` token appears in the replayed observation evidence

## Tasks

### Task 1: Add the failing fixture contract test

**Files:**

- Create: `services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py`

- [x] **Step 1: Write the failing test**

Create a pytest module that enumerates the three expected fixture package ids:

```python
EXPECTED_PACKAGES = {
    "agentic-multihop-qa.dev.v1": {
        "suite_id": "agentic_multihop_qa",
        "fixture_kind": "image_grounded_multi_hop_qa",
        "modalities": {"text", "image"},
        "required_tools": {"image_crop", "text_search"},
    },
    "agentic-visual-retrieval-qa.dev.v1": {
        "suite_id": "agentic_visual_retrieval_qa",
        "fixture_kind": "visual_retrieval_qa",
        "modalities": {"text", "image"},
        "required_tools": {"image_crop", "image_search", "visit"},
    },
    "agentic-document-lookup-qa.dev.v1": {
        "suite_id": "agentic_document_lookup_qa",
        "fixture_kind": "document_lookup_qa",
        "modalities": {"text", "document"},
        "required_tools": {"visit", "layout_parse", "text_search"},
    },
}
```

Test manifest fields, sample counts, local asset existence, per-sample fields, allowed tool coverage, and deterministic replay via `execute_agentic_tool_calls`.

- [x] **Step 2: Run the test and verify red**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
```

Expected result: failure because the three fixture package directories are absent.

### Task 2: Add the three fixture packages

**Files:**

- Create the three `manifest.json`, `samples.jsonl`, and package-local asset files listed above.

- [x] **Step 1: Add the image-grounded multi-hop QA package**

Create `agentic-multihop-qa.dev.v1` with one sample that uses `image_crop` to read a package-local gallery label and `text_search` to resolve the answer from a package-local text corpus.

- [x] **Step 2: Add the visual retrieval QA package**

Create `agentic-visual-retrieval-qa.dev.v1` with one sample that uses `image_crop`, `image_search`, and `visit` to resolve the answer from a matched visual catalog entry.

- [x] **Step 3: Add the document lookup QA package**

Create `agentic-document-lookup-qa.dev.v1` with one sample that uses `visit`, `layout_parse`, and `text_search` to resolve the answer from a package-local document fixture.

- [x] **Step 4: Run the focused test and verify green**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
```

Expected result: all tests pass.

### Task 3: Update the benchmark/evaluation contract

**Files:**

- Modify: `docs/benchmark-evaluation-contract.md`

- [x] **Step 1: Add a contract subsection**

Add an `Agentic Multimodal Development Fixtures` subsection near the evaluation dataset contract. Name the three fixture package ids, explain that they are small repository-owned development fixtures, and state that their deterministic `tool_fixture_context` data replays through the unified agentic tool runtime.

- [x] **Step 2: Re-run the focused test**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
```

Expected result: all tests still pass.

### Task 4: Verification and PR evidence

**Files:**

- No additional implementation files.

- [ ] **Step 1: Run syntax and diff checks**

Run:

```bash
git diff --check
```

Expected result: no whitespace errors.

- [ ] **Step 2: Run focused pytest with coverage**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json -o .runtime/coverage-agentic-multimodal-fixtures.json
```

Expected result: test passes and coverage JSON is written.

- [ ] **Step 3: Report metrics**

Because this issue adds static fixture packages plus a contract test and does not alter a production execution path, performance metrics are `N/A` for runtime latency. The PR evidence must state that the focused deterministic replay smoke test completed with zero failed tool calls.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/benchmark-evaluation-contract.md docs/plans/2026-05-21-agentic-multimodal-evaluation-fixtures.md services/mlx-worker-python/fixtures/evaluation/agentic-multihop-qa.dev.v1 services/mlx-worker-python/fixtures/evaluation/agentic-visual-retrieval-qa.dev.v1 services/mlx-worker-python/fixtures/evaluation/agentic-document-lookup-qa.dev.v1 services/mlx-worker-python/tests/test_agentic_multimodal_evaluation_fixtures.py
git commit -m "test: add agentic multimodal evaluation fixtures"
```

Expected result: one focused commit for issue #716.
