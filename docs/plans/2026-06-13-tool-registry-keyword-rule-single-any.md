# Tool registry keyword rule literal classification single pass

## Summary

This Python-only performance slice keeps agentic tool selection behavior unchanged
while reducing import-time setup work for the built-in keyword routing rules. The
keyword-rule compiler classified literal hints with `any(...)` twice for hints
that contain literal marker characters. This slice classifies each hint once,
keeps the existing compiled `(hint, literal)` contract, and leaves runtime
selection semantics unchanged.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/tool_registry_select_probe.py`

No probe registry change is required for this slice because the existing probe
imports the built-in registry and measures selector planning through
`selector_planning_elapsed_ms_mean`.

## Optimization slice

Scope is limited to `_compile_keyword_hint_rules(...)` in
`worker.runtime.tool_registry`:

- convert the comprehension into an explicit loop;
- bind the literal marker set and boundary text helper locally;
- compute the literal flag once per non-empty hint;
- preserve casefolding, boundary normalization, literal matching behavior, and
  the compiled rule shape consumed by `_keyword_tool_matches(...)`.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows non-regressing or improved selector planning metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
