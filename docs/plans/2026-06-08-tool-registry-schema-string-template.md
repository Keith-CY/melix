# Tool registry schema string template

## Scope

This Python-only performance slice is limited to descriptor schema string
construction in `services/mlx-worker-python/worker/runtime/tool_registry.py`.
It does not change the public tool registry API, protobuf contracts, generated
files, or Swift behavior.

## Probe registration

The affected path is covered by the registered PR-scoped probe
`tool-registry-schema-bytes-cache` in `infra/perf/pr_scoped_probes.json`. This
slice extends the existing focused `test_command`, `coverage_command`, and
`probe_command` coverage by adding `descriptor_build_elapsed_ms_mean`, which
measures repeated `ToolDescriptor` construction while preserving the existing
schema byte-count, schema payload, and worker `ToolConfig` metrics.

## Change

`ToolDescriptor.__post_init__()` now builds the cached compact JSON schema string
from the already-normalized schema components instead of allocating a complete
schema payload dictionary and running the generic sorted JSON encoder over it.
The emitted JSON remains byte-for-byte equivalent to `json.dumps(...,
separators=(",", ":"), sort_keys=True)` and `schema_payload()` still returns a
fresh mutable payload for callers.

## Verification plan

- Focused tool-registry tests, including schema JSON parity with the sorted
  compact JSON contract.
- Focused PR-scoped performance tests for the registered probe script.
- Changed-scope coverage for `tool_registry.py`, `test_tool_registry.py`,
  `test_pr_scoped_performance.py`, and `scripts/tool_registry_schema_bytes_probe.py`.
- Registered local Linux probe comparing `descriptor_build_elapsed_ms_mean` and
  adjacent metrics against the pre-change baseline.

## Boundary

This is a Python worker slice and is fully locally verifiable on Linux. No Swift
runtime effect is claimed.
