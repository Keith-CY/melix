# Issue 1382 Tool Healing Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add worker-owned tool-healing receipts so malformed-but-recoverable local agent tool responses are normalized into canonical tool calls before admission, while invalid arguments, unknown tools, and retry-budget exhaustion remain visible as typed guardrail decisions.

**Architecture:** `worker.runtime.agentic_tools` will expose a small `heal_agentic_tool_calls(...)` boundary that reuses `worker.runtime.tool_call_rescue` parsing helpers for fenced JSON, XML-style tool tags, MiniMax/tool-code blocks, and provider-style fragments. The helper will emit a sanitized `melix.agentic_tool_healing.v1` receipt, then delegate to the existing `admit_agentic_tool_calls(...)` path so executable calls, unknown tools, non-object argument roots, missing required arguments, and prerequisite violations keep the same admission semantics.

**Tech Stack:** Python worker runtime, dataclasses, existing deterministic agentic tool registry, existing `tool_call_rescue` parser helpers, pytest, coverage.

---

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-07-09-issue-1382-tool-guardrail-admission-receipts.md`
- `docs/plans/2026-07-10-issue-1382-tool-prerequisite-admission.md`
- GitHub issue #1382, especially the 2026-07-04 watch update for default-on tool healing receipts.

## Scope

This slice covers:

- a worker-owned `AgenticToolHealingDecision` result;
- a `heal_agentic_tool_calls(...)` helper that accepts raw model response fragments or provider-style tool payloads and returns normalized calls plus sanitized receipts;
- a new `melix.agentic_tool_healing.v1` receipt with `source_format`, `healed`, `nudge_reason`, `attempt_index`, and `terminal_after_budget`;
- delegation to `admit_agentic_tool_calls(...)` after healing so existing guardrail receipts still explain unknown tools, non-object arguments, missing arguments, prerequisites, and retry-budget exhaustion;
- focused tests for fenced JSON, provider fragments, non-dict arguments, unknown tools, pseudo-tool text blobs, malformed native call batches, and terminal retry-budget behavior.

This slice does not implement a full live agent loop, persist completed-step state, alter streaming parser behavior, change Swift request shaping, or add registration/execution policy gates.

## Receipt Contract

`melix.agentic_tool_healing.v1` records the pre-admission response-healing decision. The receipt includes:

- `schema_version`
- `outcome = healed|retry_nudge|terminal_failure`
- `source_format`
- `healed`
- `nudge_reason`
- `attempt_index`
- `max_retry_nudges`
- `terminal_after_budget`
- `tool_call_id`
- `tool_name`
- `call_count`
- `admitted_tool_count`
- `allowed_next_step`
- `corrective_action`

Receipts must not include raw prompts, raw model text, raw tool arguments, URLs, workspace paths, retrieved content, observation payloads, or account identifiers. The helper may inspect raw values in memory, but serialized receipts must expose only tool identifiers, counts, source-format labels, and typed corrective metadata.

## Performance Probes And Metrics

The changed path is Python-only pre-admission parsing. The helper performs bounded local parsing and one pass over recovered candidate calls before reusing existing admission validation. No external I/O is introduced.

Success metrics:

- focused changed-scope coverage for touched Python files remains at least 95 percent;
- focused agentic tool and tool-call rescue tests pass;
- PR-scoped performance report has `Status: ok` and zero in-scope regressions;
- full local pre-commit gate passes before pushing the PR.

## File Structure

- Modify `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
  Add `AGENTIC_TOOL_HEALING_RECEIPT_SCHEMA_VERSION`, `AgenticToolHealingDecision`, `heal_agentic_tool_calls(...)`, receipt construction helpers, and small local normalization helpers that call `tool_call_rescue`.
- Modify `services/mlx-worker-python/tests/test_agentic_tools.py`.
  Add focused TDD tests near the existing guardrail-admission tests.
- Modify `docs/unified-agentic-tool-runtime-contract.md`.
  Document the new healing receipt immediately after the existing tool guardrail admission receipt contract.
- Create this plan file.

## Task 1: Add RED Tests For Healing Receipts

**Files:**

- Modify: `services/mlx-worker-python/tests/test_agentic_tools.py`

- [x] **Step 1: Add failing tests for healing and admission handoff**

Add tests that use the intended public API before it exists:

```python
def test_agentic_tool_healing_accepts_fenced_json_without_raw_arguments() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        '```json\n{"id":"compute-1","name":"local_compute","arguments":{"code":"SECRET + 1"}}\n```',
        attempt_index=1,
        max_retry_nudges=2,
    )

    assert decision.healed is True
    assert decision.terminal is False
    assert decision.normalized_calls == (
        {"id": "compute-1", "name": "local_compute", "arguments": {"code": "SECRET + 1"}},
    )
    healing_receipt = decision.receipts[0]
    assert healing_receipt["schema_version"] == "melix.agentic_tool_healing.v1"
    assert healing_receipt["outcome"] == "healed"
    assert healing_receipt["source_format"] == "fenced_json_tool_call"
    assert healing_receipt["healed"] is True
    assert healing_receipt["nudge_reason"] == ""
    assert healing_receipt["allowed_next_step"] == "execute_tools"
    assert "SECRET + 1" not in json.dumps(decision.receipts, ensure_ascii=False)
```

```python
def test_agentic_tool_healing_normalizes_provider_function_fragments() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        {
            "id": "provider-1",
            "function": {
                "name": "local_compute",
                "arguments": "{\"code\":\"SECRET_PROVIDER + 2\"}",
            },
        },
        attempt_index=1,
        max_retry_nudges=2,
    )

    assert decision.healed is True
    assert decision.normalized_calls == (
        {
            "id": "provider-1",
            "name": "local_compute",
            "arguments": {"code": "SECRET_PROVIDER + 2"},
        },
    )
    assert decision.receipts[0]["source_format"] == "provider_tool_fragment"
    assert "SECRET_PROVIDER" not in json.dumps(decision.receipts, ensure_ascii=False)
```

```python
def test_agentic_tool_healing_preserves_invalid_arguments_for_admission_receipt() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        "<tool_code>local_compute(['SECRET_LIST_ARG'])</tool_code>",
        attempt_index=1,
        max_retry_nudges=2,
    )

    healing_receipt = decision.receipts[0]
    admission_receipt = decision.receipts[1]

    assert decision.healed is False
    assert decision.normalized_calls == ()
    assert healing_receipt["source_format"] == "minimax_tool_code"
    assert healing_receipt["nudge_reason"] == "invalid_arguments"
    assert admission_receipt["schema_version"] == "melix.agentic_tool_guardrail.v1"
    assert admission_receipt["failure_class"] == "invalid_arguments"
    assert "SECRET_LIST_ARG" not in json.dumps(decision.receipts, ensure_ascii=False)
```

```python
def test_agentic_tool_healing_reports_unknown_tool_without_hiding_admission() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        '<invoke name="ghost_tool"><arguments>{"secret":"SECRET_GHOST"}</arguments></invoke>',
        attempt_index=1,
        max_retry_nudges=2,
    )

    assert decision.healed is False
    assert decision.terminal is False
    assert decision.receipts[0]["source_format"] == "xml_invoke_tool_call"
    assert decision.receipts[0]["nudge_reason"] == "unknown_tool"
    assert decision.receipts[1]["failure_class"] == "unknown_tool"
    assert "SECRET_GHOST" not in json.dumps(decision.receipts, ensure_ascii=False)
```

```python
def test_agentic_tool_healing_rejects_pseudo_tool_text_blob_with_budget() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        '{"content":"please run local_compute({\\"code\\":\\"SECRET_TEXT\\"})"}',
        attempt_index=3,
        max_retry_nudges=2,
    )

    receipt = decision.receipts[0]

    assert decision.healed is False
    assert decision.terminal is True
    assert decision.normalized_calls == ()
    assert receipt["outcome"] == "terminal_failure"
    assert receipt["source_format"] == "pseudo_tool_text_blob"
    assert receipt["nudge_reason"] == "tool_call_wire_shape_required"
    assert receipt["terminal_after_budget"] is True
    assert receipt["allowed_next_step"] == "stop_with_guardrail_error"
    assert "SECRET_TEXT" not in json.dumps(decision.receipts, ensure_ascii=False)
```

```python
def test_agentic_tool_healing_does_not_drop_malformed_native_call_batch() -> None:
    decision = agentic_tools_module.heal_agentic_tool_calls(
        [
            "not-a-tool-call",
            {
                "id": "compute-1",
                "name": "local_compute",
                "arguments": {"code": "SECRET_VALID"},
            },
        ],
        attempt_index=1,
        max_retry_nudges=2,
    )

    healing_receipt = decision.receipts[0]
    admission_receipt = decision.receipts[1]

    assert decision.healed is False
    assert decision.normalized_calls == ()
    assert healing_receipt["source_format"] == "native_tool_calls"
    assert healing_receipt["nudge_reason"] == "malformed_tool_call"
    assert admission_receipt["failure_class"] == "malformed_tool_call"
    assert admission_receipt["tool_call_id"] == "call-1"
    assert "SECRET_VALID" not in json.dumps(decision.receipts, ensure_ascii=False)
```

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py -k "healing"
```

Expected: fail because `worker.runtime.agentic_tools` has no `heal_agentic_tool_calls` attribute.

## Task 2: Implement Minimal Healing Boundary

**Files:**

- Modify: `services/mlx-worker-python/worker/runtime/agentic_tools.py`

- [x] **Step 1: Add schema constant and result dataclass**

Add:

```python
AGENTIC_TOOL_HEALING_RECEIPT_SCHEMA_VERSION = "melix.agentic_tool_healing.v1"


@dataclass(frozen=True)
class AgenticToolHealingDecision:
    healed: bool
    terminal: bool
    normalized_calls: tuple[dict[str, Any], ...]
    receipts: tuple[dict[str, Any], ...]
```

- [x] **Step 2: Implement `heal_agentic_tool_calls(...)`**

Add a public helper with this signature:

```python
def heal_agentic_tool_calls(
    response: object,
    *,
    registry: ToolRegistry | None = None,
    prerequisites: list[AgenticToolPrerequisite] | tuple[AgenticToolPrerequisite, ...] = (),
    completed_tool_calls: list[object] | tuple[object, ...] | None = None,
    attempt_index: int = 1,
    max_retry_nudges: int = 1,
) -> AgenticToolHealingDecision:
    ...
```

Behavior:

- parse the response into candidate tool calls plus a `source_format`;
- return a healing-only retry or terminal receipt when no executable tool-call wire shape exists;
- call `admit_agentic_tool_calls(...)` with the recovered candidate calls;
- return admitted calls only from the admission result;
- append the admission receipts after the healing receipt;
- keep raw response text and raw argument values out of all healing receipts.

- [x] **Step 3: Implement local parsing helpers**

Add helpers that:

- use `tool_call_rescue.extract_rescue_envelope(...)` and `tool_call_rescue.parse_tool_body(...)` for fenced JSON, `[TOOL_CALL]`, XML invoke, and `<tool_code>`;
- use `tool_call_rescue.tool_payload_name(...)` and `tool_call_rescue.tool_payload_arguments(...)` for provider-style fragments;
- preserve non-dict argument roots for admission rejection instead of silently coercing them to `{}`;
- classify content-only JSON objects as `pseudo_tool_text_blob`.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py -k "healing"
```

Expected: all healing tests pass.

## Task 3: Document The Receipt Contract

**Files:**

- Modify: `docs/unified-agentic-tool-runtime-contract.md`

- [x] **Step 1: Add the healing receipt section**

Add the `melix.agentic_tool_healing.v1` field list and safety constraints immediately after the tool guardrail admission receipt contract.

- [x] **Step 2: Run documentation diff checks**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Task 4: Verify Coverage, Performance, And Commit

**Files:**

- Modify: `services/mlx-worker-python/worker/runtime/agentic_tools.py`
- Modify: `services/mlx-worker-python/tests/test_agentic_tools.py`
- Modify: `docs/unified-agentic-tool-runtime-contract.md`
- Modify: `docs/plans/2026-07-12-issue-1382-tool-healing-receipts.md`

- [x] **Step 1: Run focused tests**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_tool_call_rescue.py
```

- [x] **Step 2: Run changed-scope coverage**

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_agentic_tools.py services/mlx-worker-python/tests/test_tool_call_rescue.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_agentic_tools.py
```

Expected: at least 95 percent changed-scope coverage.

- [x] **Step 3: Run local gates before commit**

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```

Expected: all commands pass.

- [x] **Step 4: Run pre-commit performance report**

```bash
.githooks/pre-commit
```

Expected: hook passes, performance report status is `ok`, and regressions are `0`.

- [ ] **Step 5: Commit**

```bash
git add docs/plans/2026-07-12-issue-1382-tool-healing-receipts.md docs/unified-agentic-tool-runtime-contract.md services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_agentic_tools.py
git commit -m "Add agentic tool healing receipts"
```

## Self-Review

- Spec coverage: the plan covers tool healing receipts, typed nudges, admission handoff, non-dict arguments, unknown tools, malformed native batches, repeated malformed output, docs, tests, coverage, and performance gates.
- Placeholder scan: no placeholder tasks remain.
- Type consistency: `AgenticToolHealingDecision`, `heal_agentic_tool_calls(...)`, and `melix.agentic_tool_healing.v1` are consistently named throughout the plan.
