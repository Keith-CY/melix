# Tool registry selection normalized-name fast path

This Python-only performance slice covers `ToolRegistry.select(...)` in
`worker.runtime.tool_registry` when callers pass multiple already-normalized tool
names.

## Scope

The multi-name selection path still preserves the existing semantics:

- empty names are skipped;
- whitespace-only names are skipped;
- names with leading or trailing whitespace are stripped before lookup;
- duplicate normalized names are collapsed in request order;
- unknown normalized names still raise `ToolRegistryError`.

The optimization avoids calling `str.strip()` for names that are already
normalized by first checking the first and last character. This mirrors the
single-name selection fast path and keeps the slower strip path only for inputs
that can actually need normalization.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`tool-registry-select-name-index-cache` in `infra/perf/pr_scoped_probes.json`.
The registered entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries, and this plan is listed in the probe watch globs.

## Verification plan

1. Run the registered focused pytest command for
   `tool-registry-select-name-index-cache`.
2. Run the registered changed-scope coverage command and require at least 95%
   coverage for the touched Python scope.
3. Run the registered local probe on Linux and compare base vs head metrics.
4. Use GitHub Actions PR-scoped performance as the final base-vs-head merge gate
   before merging.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed or claimed.
