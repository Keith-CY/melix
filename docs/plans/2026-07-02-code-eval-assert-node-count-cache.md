# Code evaluation assert-node count cache slice

This Python-only performance slice is limited to `worker.engine.code_eval_runner._count_assert_nodes(...)`, the valid-test AST assert counting path used by code-evaluation result accounting.

## Scope

The affected path is already covered by the registered PR-scoped probe `code-eval-count-tests-line-scan` in `infra/perf/pr_scoped_probes.json`. This slice keeps that probe registered and adds the new regression test to both the focused `test_command` and `coverage_command` entries before claiming performance evidence.

## Root cause and hypothesis

The registered probe repeatedly counts assertions on the same parsed test AST. The all-top-level-assert fast path avoids stack traversal but still scans every top-level AST node on each repeated call. For generated evaluation tests, the AST object is stable across repeated count calls in the same evaluation loop.

Hypothesis: memoizing the computed assert count on the AST module, guarded by the module body identity and length, preserves count behavior for the stable-AST path while avoiding repeated top-level scans.

## Implementation plan

1. Add a private module-level cache attribute name and default statement-container tuple.
2. Let `_count_assert_nodes(...)` use the cache only for the default production call shape.
3. Store `(id(module.body), len(module.body), count)` after computing the count and reuse it on later calls when the body identity and length still match.
4. Add a focused regression test that verifies the cache tuple is populated and repeated calls return the same count.
5. Keep behavior for custom test injection parameters unchanged by bypassing the cache when defaults are not used.

## Verification plan

- Focused pytest for `_count_assert_nodes(...)` behavior.
- Registered probe focused test command from `infra/perf/pr_scoped_probes.json`.
- Registered changed-scope coverage command from `infra/perf/pr_scoped_probes.json`.
- Registered local probe command before and after the change on Linux.

## Linux validation boundary

This slice changes Python worker code only. Local Linux validation covers tests, changed-scope coverage, and the registered Python probe. No Swift/macOS runtime effect is claimed.
