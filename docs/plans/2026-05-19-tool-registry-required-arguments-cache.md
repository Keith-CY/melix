# Tool registry required-arguments cache

## Scope

This Python-only performance slice narrows the repeated `ToolDescriptor.required_arguments` hot path in `services/mlx-worker-python/worker/runtime/tool_registry.py`.

The behavior remains unchanged: descriptors still validate duplicate argument names during construction, `schema_payload()` still returns a fresh mutable payload dictionary, and registry metrics continue to report the same required-argument totals.

## Optimization

Cache the required argument-name tuple once during `ToolDescriptor.__post_init__` and have the `required_arguments` property return that immutable snapshot. This removes repeated tuple construction when callers request `required_arguments` or rebuild schema payload dictionaries for already-validated descriptors.

## PR-scoped performance CI

The affected Python path is already covered by the registered PR-scoped probes in `infra/perf/pr_scoped_probes.json`:

- `tool-registry-schema-bytes-cache`
- `tool-registry-select-name-index-cache`
- `tool-registry-names-snapshot-cache`

This slice extends the `tool-registry-schema-bytes-cache` probe with `schema_payload_elapsed_ms_mean` so CI and local Linux runs compare the schema-payload path directly. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the changed code, tests, and probe script.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json probe. No Swift runtime performance claim is made.
