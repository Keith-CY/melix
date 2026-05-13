# OpenSearch-VL Agentic Trajectory Dataset Contracts

## Goal

Complete the issue #664 planning and contract slice by defining a canonical
Melix trajectory dataset contract and making the existing milestone and
executable child issues auditable.

## Non-Goals

- Do not implement new LoRA optimizer behavior.
- Do not implement new RL rollout behavior.
- Do not add new benchmark or evaluation scoring behavior.
- Do not claim model-quality, benchmark, or evaluation improvements.
- Do not close issue #664 until the child milestone issues land with current
  local verification evidence.

## Context

- Parent issue: `https://github.com/Keith-CY/melix/issues/664`
- Governing spec added by this slice:
  `docs/agentic-trajectory-dataset-contract.md`
- Related runtime spec:
  `docs/unified-agentic-tool-runtime-contract.md`
- Existing data-foundation plan:
  `docs/plans/2026-05-11-opensearch-vl-agentic-foundation.md`
- Current implementation anchors:
  - `services/mlx-worker-python/worker/model_ops/training_dataset.py`
  - `services/mlx-worker-python/fixtures/training/agentic-tool-trace.dev.v1/`
  - `services/mlx-worker-python/worker/runtime/tool_registry.py`
  - `services/mlx-worker-python/worker/runtime/tool_observation.py`
  - `services/mlx-worker-python/worker/runtime/agentic_tools.py`

## Assumptions

- The existing GitHub child issues #665 through #673 are the intended issue
  tree for #664.
- Existing behavior should stay untouched in this slice.
- Documentation-only verification can use metrics `N/A` with an explicit
  reason, per `docs/contributing.md`.

## Work Plan

1. Add `docs/agentic-trajectory-dataset-contract.md` as the canonical
   trajectory package, validation, and provenance contract for issue #664.
2. Link the new contract from `docs/README.md`.
3. Cross-link `docs/unified-agentic-tool-runtime-contract.md` so the runtime
   contract points to the trajectory contract instead of embedding all dataset
   governance in the tool-runtime spec.
4. Audit existing child issues #665 through #673.
5. Edit each child issue body so every milestone and executable unit includes:
   - file scope
   - required tests
   - required metrics
   - known gaps
   - governing spec or plan reference
6. Open a focused PR with documentation-only evidence and metrics N/A.

## Verification

```bash
git diff --check
python3.11 scripts/validate_pr_evidence.py --body-file /tmp/pr-664-body.md
```

Expected evidence:

- `git diff --check` passes.
- PR evidence validation passes with the required headings.
- Coverage and metrics are reported as
  `N/A: documentation-only trajectory contract update; no executable runtime path changed.`

## Acceptance Criteria

- Issue #664 has a canonical Melix plan or spec under `docs/`.
- The child milestone issues #665, #668, and #671 identify executable child
  issues.
- Child issues #666, #667, #669, #670, #672, and #673 each include file scope,
  tests, metrics, and known gaps.
- The PR body keeps the required evidence headings.
- No benchmark or evaluation claim is made without persisted artifacts.

## Rollback or Safe Exit

- Revert the documentation commit if the issue tree needs a different
  hierarchy.
- Restore previous GitHub issue bodies from the PR discussion if maintainers
  prefer a different issue template.
