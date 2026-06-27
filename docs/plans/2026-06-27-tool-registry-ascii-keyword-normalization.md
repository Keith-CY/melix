# Tool registry ASCII keyword normalization fast path

## Summary

This Python-only performance slice keeps agentic tool keyword selection behavior
unchanged while reducing per-call normalization overhead for the common ASCII
prompt path. `_keyword_tool_matches(...)` and `_keyword_hint_matches(...)` now
use `str.lower()` for ASCII inputs and retain `str.casefold()` for non-ASCII
text, preserving Unicode-aware behavior where it matters.

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
already measures selector planning and keyword matching with ASCII prompt text.

## Optimization slice

Scope is limited to keyword normalization in
`worker.runtime.tool_registry.select_agentic_tools_for_turn(...)`:

- use `str.isascii()` to detect ASCII prompt and hint-match text;
- use `str.lower()` for ASCII normalization;
- retain `str.casefold()` for non-ASCII text;
- preserve keyword matching, literal/boundary hint behavior, always-available
  tool admission, receipt ordering, and fallback semantics.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows non-regressing or improved selector planning metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
