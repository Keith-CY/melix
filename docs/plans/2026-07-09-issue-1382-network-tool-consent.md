# Issue 1382 Network Tool Consent Slice

## Goal

Add an explicit network-tool consent boundary to agentic tool selection so a
session-level web deny wins over prompt-inferred browsing intent before any
network-capable schema reaches the model-visible registry.

## Governing Documents

- `AGENTS.md`
- `docs/unified-agentic-tool-runtime-contract.md`
- `docs/plans/2026-06-23-issue-1382-tool-registry-parity.md`

## Scope

This slice covers:

- a request-local `allow_web` policy input for deterministic agentic tool
  selection;
- a machine-readable tool policy receipt that records explicit web allow/deny,
  disabled tool IDs, and denied requested tool IDs without raw prompt text;
- fail-closed selection behavior for `visit` when `allow_web=false`;
- focused Python tests proving explicit deny beats keyword and vector routing.

This slice does not add live web adapters, outbound HTTP, MCP policy, UI
controls, or general agent framework behavior. The existing deterministic
runtime still executes only the selected registry allowlist.

## Architecture

The best end state is one effective tool policy contract shared by CLI, app,
worker, and future agent sessions. The contract should distinguish a missing
setting from an explicit operator deny, and selection receipts should explain
which model-visible tools were disabled before generation.

This PR implements the first worker-owned slice at the existing selector
boundary:

- `ToolSelectionInput.allow_web` is `None` when no explicit operator choice was
  supplied, `true` for explicit allow, and `false` for explicit deny.
- `visit` is treated as the current network-capable agentic tool because it can
  represent browser/page fetch behavior. Local compute, workspace files, and
  local corpus lookup remain available.
- `select_agentic_tools_for_turn(...)` computes disabled tools once, filters
  keyword and vector-selected tools through the same policy gate, and adds a
  `melix.agentic_tool_policy.v1` receipt only when an explicit web policy is
  present or a disabled tool was requested.
- `DeterministicAgenticToolRuntime` continues to use the selected registry as
  the execution allowlist, so a denied `visit` call remains an unknown-tool
  failure instead of attempting any adapter work.

## Performance Probes And Metrics

Selection cost remains bounded by the existing constant-size tool catalog. The
new policy gate is a set membership check per candidate tool and does not scan
raw prompt text beyond the existing keyword matcher.

Local metrics for this slice:

- explicit deny with keyword browse intent selects only `local_compute`;
- explicit deny with vector-selected `visit` selects only `local_compute`;
- explicit allow keeps existing `visit` selection behavior;
- policy receipts contain tool IDs and policy decisions, not URLs or prompt
  content;
- changed-scope coverage for `tool_registry.py`, `agentic_tools.py`, and their
  focused tests is at least 95 percent before commit.

## TDD Plan

1. Add failing selector tests in
   `services/mlx-worker-python/tests/test_tool_registry.py` for
   `allow_web=false` keyword and vector paths, plus `allow_web=true` receipt
   visibility.
2. Add a failing runtime allowlist test in
   `services/mlx-worker-python/tests/test_agentic_tools.py` proving a denied
   `visit` call is not executable when the selected registry was built under
   `allow_web=false`.
3. Run the focused tests and confirm they fail because `ToolSelectionInput` does
   not yet accept `allow_web`.
4. Implement the minimal selector policy fields and receipt in
   `services/mlx-worker-python/worker/runtime/tool_registry.py`.
5. Update `docs/unified-agentic-tool-runtime-contract.md` with the request-local
   tool policy receipt contract.
6. Run focused tests, changed-scope coverage, `git diff --check`, the relevant
   tool-registry probe, and the full versioned pre-commit hook before commit.

## Verification Commands

Focused red/green:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_registry.py::test_agentic_tool_selection_explicit_web_deny_blocks_keyword_visit_with_policy_receipt services/mlx-worker-python/tests/test_tool_registry.py::test_agentic_tool_selection_explicit_web_deny_blocks_vector_visit_with_policy_receipt services/mlx-worker-python/tests/test_tool_registry.py::test_agentic_tool_selection_explicit_web_allow_records_policy_without_disabling_visit services/mlx-worker-python/tests/test_agentic_tools.py::test_agentic_tool_runtime_web_deny_keeps_visit_out_of_execution_allowlist
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
UV_PYTHON=3.12 uv run python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/tool_registry.py services/mlx-worker-python/worker/runtime/agentic_tools.py services/mlx-worker-python/tests/test_tool_registry.py services/mlx-worker-python/tests/test_agentic_tools.py
```

Metrics and general checks:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python3 scripts/tool_registry_select_probe.py
git diff --check
.githooks/pre-commit
```
