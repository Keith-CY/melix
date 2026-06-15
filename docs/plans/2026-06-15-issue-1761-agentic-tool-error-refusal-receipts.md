# Issue 1761 Agentic Tool Error Refusal Receipts Plan

## Goal

Add source-specific refusal receipts to deterministic agentic tool adapter failures so malformed untrusted inputs, owner-scope mismatches, and workspace path refusals are visible in the same `melix.untrusted_context_receipt.v1` stream as admitted source evidence.

## Scope

- Keep the existing failed observation payload fields for backward compatibility.
- Add an `included = false` source receipt when a deterministic adapter raises `AgenticToolRuntimeError` with source metadata.
- Cover invalid untrusted value types, owner-scope mismatches, and workspace path resolver refusals.
- Do not change successful adapter payloads, prompt payload projection, or the generic observation-level receipt.

## Architecture

`DeterministicAgenticToolRuntime.execute` already catches `AgenticToolRuntimeError`, copies its `details` into the failed payload, and normalizes the payload through `normalize_tool_observation`. This slice will derive a source-specific refusal receipt from those details before normalization and pass it through `source_untrusted_context_receipts`.

The mapper will only emit receipts for known refusal reasons that include enough source metadata. Unknown tool runtime failures continue to rely on the existing generic tool-observation receipt.

## Performance Probes

- Measurement point: deterministic agentic tool adapter failure normalization in `services/mlx-worker-python/worker/runtime/agentic_tools.py`.
- Success metric: existing `pr-scoped-performance` selected probe reports `Status: ok`, `Regressions: 0`, `Context regressions: 0`, and `Verification failures: 0`.
- Expected overhead: one small dictionary construction only on failed adapter paths; successful hot paths are unchanged.
- Observability mode: `evidence`.

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py`:
   - invalid skill/memory lookup input emits an `included = false` receipt with `reason = invalid_untrusted_input_type`.
   - skill/memory owner mismatch emits an `included = false` receipt with `reason = owner_scope_mismatch`.
   - workspace path refusal emits an `included = false` receipt with `reason = workspace_path_refused`.
2. Implement a small helper in `services/mlx-worker-python/worker/runtime/agentic_tools.py` that maps `AgenticToolRuntimeError.details` into `refused_prompt_context_receipt`.
3. Pass the derived refusal receipt into `normalize_tool_observation` through `source_untrusted_context_receipts`.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to describe failed deterministic adapter source receipts.
5. Run focused pytest, changed-scope coverage, `git diff --check`, and the full local pre-commit gate before commit.

## Verification

Run:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_agentic_tools.py -q
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_agentic_tools.py --cov=worker.runtime.agentic_tools --cov-report=term-missing
git diff --check
make bootstrap
make proto
make swift-test
make py-test
make integration-test
```
