# Engine Parser Metrics Empty Fast Path Slice

## Scope

This Python-only performance slice is limited to the terminal response metrics assembly in `worker.engine.engine_core.EngineCore.generate()`.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and watches `services/mlx-worker-python/worker/engine/engine_core.py` plus focused tests and probe script.

## Implementation plan

1. Preserve Generate response semantics and all existing parser/native-MTP metrics when present.
2. Add a minimal empty-metrics fast path so plain Generate completions do not allocate a parser metrics dict comprehension when the assembler has no metrics.
3. Add a focused empty-completion regression test and include it in the registered probe's `test_command` and `coverage_command` so the empty parser-metrics branch is covered.
4. Verify focused Generate tests, changed-scope coverage, and the registered local probe on Linux.
5. Use the PR-scoped performance workflow as the merge gate for the registered probe report.

## Success criteria

- Focused Generate tests pass.
- Changed-scope coverage for the touched file remains above the repository threshold.
- The registered probe remains green and reports stable/improved local metrics for the no-usage Generate path without regressing fallback metrics.
