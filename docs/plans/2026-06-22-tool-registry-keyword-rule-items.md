# Tool registry keyword rule items fast path

This Python performance slice is limited to the agentic tool registry keyword-routing loop in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

## Registered Probe

The affected file is covered by registered PR-scoped probes in `infra/perf/pr_scoped_probes.json`:

- `tool-registry-select-name-index-cache`
- `tool-registry-schema-bytes-cache`
- `tool-registry-names-snapshot-cache`
- `tool-registry-openai-tools-template-cache`

Each entry includes focused `test_command`, `coverage_command`, and `probe_command` fields. The select probe directly exercises `select_agentic_tools_for_turn()` keyword-planning paths and is the primary local performance signal for this slice.

## Change

Precompute the ordered `(tool_name, rules)` pairs for keyword-matchable tools once at module import time. `_keyword_tool_matches()` can then iterate the compact tuple directly instead of performing a dictionary lookup for every candidate tool on every uncached keyword scan.

The change preserves the existing match order and selection semantics.

## Verification Plan

1. Run the registered select probe on `origin/main` before the change and on `HEAD` after the change.
2. Run the focused tool registry tests, including the new rule-item ordering regression test.
3. Run the registered changed-scope coverage command for `tool-registry-select-name-index-cache` and confirm at least 95% coverage for touched Python scope.
4. Run `git diff --check`.
5. Use the PR-scoped performance workflow as the merge gate for the registered probe report.
