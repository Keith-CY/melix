# Tool Registry Single-Name Select Fast Path

## Scope

This Python-only performance slice is limited to `ToolRegistry.select()` when the
caller requests exactly one tool name. The behavior remains equivalent for raw
lists, raw tuples, blank names, duplicate filtering on multi-name selections,
missing names, and full-registry selections.

## Registered Probe

The affected path is covered by registered PR-scoped probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The probe already includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches:

- `services/mlx-worker-python/worker/runtime/tool_registry.py`
- `services/mlx-worker-python/tests/test_tool_registry.py`
- `scripts/tool_registry_select_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Plan

1. Preserve the existing exact-full-selection and tuple-cache fast paths.
2. Add a single-name branch after those fast paths and before the general
   dedupe/normalization loop.
3. For non-blank single names, perform one strip, one cache lookup, and one
   registry name-index lookup; cache normalized and raw tuple aliases exactly as
   the general path does.
4. Leave blank single-name requests on the existing general path so empty
   selections keep current semantics.
5. Verify focused tests, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR. GitHub Actions PR-scoped performance remains
   the merge gate.

## Success Criteria

- Focused `test_tool_registry.py` behavior remains green.
- Changed-scope coverage for the touched scope remains at least 95%.
- Registered local probe reports lower `elapsed_ms_mean` and
  `missing_selection_elapsed_ms_mean` versus `origin/main`.
- PR-scoped performance CI completes the registered probe before merge.
