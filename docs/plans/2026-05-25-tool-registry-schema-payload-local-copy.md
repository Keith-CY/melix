# Tool Registry Schema Payload Local Copy Helpers

## Scope

This Python performance slice targets `ToolDescriptor.schema_payload()` in
`services/mlx-worker-python/worker/runtime/tool_registry.py`. The behavior stays
unchanged: each call still returns an isolated OpenAI-compatible schema payload
with copied property dictionaries and a copied `required` list.

## Registered probe

Existing registered PR-scoped probe: `tool-registry-schema-bytes-cache` in
`infra/perf/pr_scoped_probes.json`.

The probe covers `tool_registry.py`, focused tool-registry tests, and
`scripts/tool_registry_schema_bytes_probe.py`. It includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and records
`schema_payload_elapsed_ms_mean` for this call path.

## Optimization

Bind the module-level `_COPY_DICT` and `_COPY_LIST` helpers once inside
`schema_payload()` and call those local bindings while building the returned
payload. This mirrors the existing `as_openai_tools()` hot-path pattern and
avoids repeated method attribute lookup during the per-tool property/list copy
work.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. CI's PR-scoped performance workflow remains the merge
gate for the registered probe report.
