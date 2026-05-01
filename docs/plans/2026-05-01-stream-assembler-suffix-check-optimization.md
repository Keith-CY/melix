# Task Plan

## Title

`stream-assembler suffix check optimization`

## Goal

Reduce hot-path overhead in `services/mlx-worker-python/worker/runtime/stream_assembler.py` by replacing the generator-based structural-tag suffix scan with an equivalent tuple-based `str.endswith(...)` check, and prove the change with focused tests, coverage, and a local performance probe.

## Non-Goals

- Do not refactor unrelated parser logic.
- Do not change Swift or macOS-specific code.
- Do not broaden the optimization slice beyond one coherent change.

## Context

- Relevant specs: N/A for a micro-optimization slice; repository verification and PR evidence rules in `AGENTS.md` apply.
- Relevant code paths:
  - `services/mlx-worker-python/worker/runtime/stream_assembler.py`
  - `services/mlx-worker-python/tests/test_stream_assembler.py`
- Current constraints:
  - Linux host only.
  - Must stay locally verifiable with pytest.
  - Touched executable Python scope must have at least 95% automated changed-scope coverage.
  - Must include concrete performance numbers before commit.

## Assumptions

- `str.endswith(tuple[str, ...])` is semantics-equivalent to iterating over the same suffix set with `any(...)`.
- Existing stream assembler tests cover the relevant partial-tag behavior, and one additional direct regression test can lock the equivalence down.

## Work Plan

1. Add a failing test that directly exercises `_has_partial_structural_tag_suffix()` for both think-only and tool-enabled parser modes.
2. Replace the generator-based suffix scan with tuple-based `str.endswith(...)` and rerun the focused test scope.
3. Measure changed-scope coverage and run a dedicated micro-benchmark / profile probe to capture before-or-after optimization evidence.
4. Validate formatting and git diff hygiene, then prepare a small PR with the required evidence sections.

## Verification

```bash
cd services/mlx-worker-python
PYTHONPATH=. pytest -q tests/test_stream_assembler.py
PYTHONPATH=. coverage erase
PYTHONPATH=. coverage run -m pytest -q tests/test_stream_assembler.py
PYTHONPATH=. coverage json -o coverage.json
python scripts/changed_scope_coverage.py  # equivalent inline script if helper absent
python scripts/perf_probe.py              # equivalent inline probe for stream assembler
git diff --check
```

Record the expected evidence for each command.

## Acceptance Criteria

- Focused stream assembler tests pass.
- Changed executable lines in `worker/runtime/stream_assembler.py` reach at least 95% automated coverage.
- Performance probe shows improved time for the targeted suffix-check-heavy workload.
- Diff stays small and limited to the planned optimization slice and its tests.

## Rollback or Safe Exit

- If the optimization changes behavior, revert the code and keep the branch unpushed.
- If no measurable improvement appears, stop without opening a PR.
